# Design Doc: Seekable Replay API for `VideoIn`

**Branch:** `feat/video-in-seekable-replay`  
**Status:** Implemented  
**Author:** Tales Rodrigues  
**Date:** 2026-07-07

---

## Motivation

Replay pipelines re-process a recorded video alongside its stored subject-data
(detections, tracks, classifications) so operators can review, audit, or debug
pipeline output frame by frame.

Before this change, `VideoIn` had no way to pause, seek, or step through a video
at runtime. Every emitted frame carried only a wall-clock timestamp (`ts`), which
made it impossible for downstream filters such as `FilterSubjectDataIn` to stay
synchronized after any interactive operation:

- **After a seek** — `FilterSubjectDataIn`'s sequential cursor kept advancing from
  the old position, overlaying data from the wrong point in time.
- **While paused** — the same image was re-emitted but the cursor still advanced,
  so bounding boxes kept moving on a frozen frame.

A prototype filter (`SeekableVideoIn`) proved the concept but duplicated all of
`VideoIn`'s video-reading logic and forced every replay pipeline to use a different
filter class name. The correct fix is to add these capabilities directly to `VideoIn`,
activated only when the operator sets the new `control_port` field.

---

## What Changed in `VideoIn`

### 1. New configuration fields

| Field | Type | Default | Env var |
|---|---|---|---|
| `control_port` | `int \| None` | `None` (disabled) | `VIDEO_IN_CONTROL_PORT` |
| `sdi_url` | `str` | `http://localhost:8090` | `VIDEO_IN_SDI_URL` |
| `webvis_url` | `str` | `http://localhost:8000` | `VIDEO_IN_WEBVIS_URL` |
| `webvis_topic` | `str` | `viz` | `VIDEO_IN_WEBVIS_TOPIC` |

Setting `control_port` is the only opt-in required. All other fields have sensible
defaults. Existing `VideoIn` configurations without `control_port` are completely
unaffected.

### 2. Embedded HTTP replay API

When `control_port` is set, `VideoIn.setup()` creates a `VideoController` (from the
`filter_subject_data_in` package) and starts its HTTP server. The server exposes:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/pause` | Pause playback |
| `POST` | `/play` | Resume playback |
| `POST` | `/step?frames=N` | Advance N frames while paused |
| `POST` | `/seek?frame=N` | Seek to frame index N |
| `POST` | `/seek?ts=12.3` | Seek to timestamp in seconds |
| `GET` | `/status` | JSON: frame index, ts, fps, total frames |
| `GET` | `/video` | Stream the local MP4 (Range request support) |
| `GET` | `/player` | HTML5 browser player with scrubber and overlay |

The controller is wired into every `VideoReader` in the filter so multi-camera sources
pause and seek together. If the `filter_subject_data_in` package is not installed, a
warning is logged and the filter continues in normal streaming mode.

### 3. Frame-accurate seek in `VideoReader.thread_reader`

A seek command sets a target frame index in the controller. At the top of the next
`thread_reader` loop iteration, the thread:

1. Reads and clears the pending seek target atomically.
2. Calls `cv2.CAP_PROP_POS_FRAMES` to jump to the nearest I-frame.
3. Reads forward frame by frame until the exact target index is reached
   (I-frame compensation).
4. Sets an internal `_just_seeked` flag so the resulting frame is read and
   stored before the freeze loop resumes.

### 4. Freeze-frame (pause) in `VideoReader.thread_reader`

While paused, instead of reading the next frame from the video file the thread
re-emits the last captured image at the natural frame rate. The re-emitted frame
carries `frame_repeat: True` in its extras dict. This keeps pipeline throughput
stable — downstream filters continue to receive frames and can serve API queries
— while preventing the data cursor from advancing.

The freeze loop respects the existing timing mechanisms: in `sync` mode it waits
for `sync_evt` backpressure from the consumer; in async mode it sleeps one frame
period (`ns_per_fps`).

### 5. Sync metadata injected into every Frame

`VideoIn.process()` maps the extras produced by `thread_reader` into standard
`meta` keys on the outgoing `Frame`:

| `meta` key | Present when | Meaning |
|---|---|---|
| `frame_index` | replay mode, every frame | 0-based position in the video file |
| `total_frames` | replay mode, every frame | total frames in the file |
| `frame_repeat` | paused | this frame is a re-emission; do not advance data cursor |
| `seek_reset` | first frame after a seek | a seek just occurred |
| `seek_frame_index` | seek | exact target frame index |
| `seek_ts` | seek | target timestamp in seconds |

`FilterSubjectDataIn` already consumes all three signals for `sync_key='sequential'`:

```
frame_repeat = True  →  return stored_frames[cursor - 1]   (cursor unchanged)
seek_reset   = True  →  cursor = seek_frame_index           (jump to exact position)
(normal)             →  return stored_frames[cursor]; cursor += 1
```

No changes to `FilterSubjectDataIn` were required.

### 6. Internal deque format

The `VideoReader` deque item format was extended from `(image, tframe)` to
`(image, tframe, extras)` where `extras` is always present (empty dict `{}`
when replay mode is not active). `VideoReader.read()` and `MultiVideoReader.read()`
were updated accordingly. The change is entirely internal; the public `Frame` API
and all downstream filters are unaffected.

---

## Backward Compatibility

| Scenario | Behavior |
|---|---|
| `control_port` not set | Identical to the previous `VideoIn` — zero overhead |
| `control_port` set, package missing | Warning logged, replay disabled, pipeline continues |
| `SeekableVideoIn` users | No change — filter is preserved and still works |

---

## Files Changed

| File | Change |
|---|---|
| `openfilter/filter_runtime/filters/video_in.py` | Core implementation (+237 lines) |
| `tests/test_filter_video_in.py` | Update `test_normalize_config` for new default config keys |
