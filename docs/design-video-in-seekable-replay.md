# Design Doc: Seekable Replay API for `VideoIn`

**Branch:** `feat/video-in-seekable-replay`  
**Status:** Implemented  
**Author:** Tales Rodrigues  
**Date:** 2026-07-07

---

## 1. Summary

This document describes the motivation, design, and implementation of seekable replay
controls added to the existing `VideoIn` filter.  The goal is to allow `VideoIn` to
serve as the input stage of an **interactive replay pipeline** — supporting real-time
pause, play, step, and frame-accurate seek — without creating a separate filter class.

The changes are **fully backward-compatible**: all existing `VideoIn` users are
unaffected unless they opt in by setting the new `control_port` configuration field.

---

## 2. Background and Motivation

### 2.1 The Replay Use Case

A common operational workflow is to re-process a previously recorded video alongside its
stored subject-data (detections, tracks, classifications) in order to review, audit, or
debug pipeline output.  The replay pipeline looks like this:

```
VideoIn ──► FilterSubjectDataIn ──► Webvis
             (recorded data)         (browser viewer)
```

In a pure streaming setup this works fine — frames flow at video FPS and
`FilterSubjectDataIn` advances its internal cursor in lock-step.  The problem arises
when a human operator wants to **interact** with the replay: pause it, jump to a
specific moment, or step through frame by frame.

### 2.2 Why `VideoIn` and Not a New Filter

A prototype filter called `SeekableVideoIn` was created to explore this space.  It
proved the concept but introduced a maintenance burden:

| Concern | Detail |
|---|---|
| Code duplication | All video-reading logic from `VideoIn` was re-implemented |
| Two filters to document | Users had to choose between `VideoIn` and `SeekableVideoIn` |
| Divergence risk | Bug fixes in `VideoIn` would not propagate to `SeekableVideoIn` |
| Deployment friction | Replay pipelines required a different filter class name |

The correct long-term home for these features is inside `VideoIn` itself, activated only
when the operator explicitly configures a `control_port`.  `SeekableVideoIn` is
preserved unchanged so existing deployments are not broken.

### 2.3 Synchronization Problem

The core technical challenge is **keeping `FilterSubjectDataIn`'s data cursor in
perfect sync with the video position at all times**, including after seeks and during
pauses.

Without replay metadata in the frame, `FilterSubjectDataIn` has no way to know that:

1. The video jumped backwards (seek) — its sequential cursor keeps marching forward,
   showing data from the wrong point in time.
2. The video is frozen (pause) — it still advances one stored frame per emitted frame,
   so bounding boxes keep moving even though the image is static.

The only reliable solution is for `VideoIn` to inject explicit sync signals into every
frame's metadata.

---

## 3. Design

### 3.1 Activation

Replay mode is **opt-in**.  Nothing changes for existing `VideoIn` users.

```yaml
# Normal mode (no change)
- VideoIn:
    sources: file://video.mp4

# Replay mode (new)
- VideoIn:
    sources: file://video.mp4
    control_port: 8091
    sdi_url: http://localhost:8092
```

When `control_port` is set and the `filter_subject_data_in` package is installed,
`VideoIn` starts an embedded HTTP server and injects replay metadata into every frame.
If the package is not installed a warning is logged and the filter continues normally
without replay features.

### 3.2 Architecture

```
┌─────────────────────────────────────────────────────────┐
│  VideoIn process                                         │
│                                                          │
│  ┌──────────────┐   (image, tframe, extras)             │
│  │ VideoReader  │──────────────────────────────►        │
│  │ thread       │   deque                                │
│  │              │◄──────── consume_seek()                │
│  │              │◄──────── should_freeze()               │
│  └──────────────┘                                        │
│         ▲                   │                            │
│         │            ┌──────▼──────┐                    │
│         │            │ VideoCtrl   │  HTTP :8091         │
│         │            │ (state machine)◄──────────────── │◄── browser / curl
│         │            └─────────────┘                    │
│  VideoIn.process()                                       │
│    reads deque → builds Frame with replay meta           │
└─────────────────────────────────────────────────────────┘
           │
           ▼  Frame{meta: {frame_index, seek_reset, frame_repeat, ...}}
┌──────────────────────────┐
│ FilterSubjectDataIn      │
│  seek_reset  → reset cursor to seek_frame_index          │
│  frame_repeat → hold cursor, return same stored frame    │
│  normal      → advance cursor by 1                       │
└──────────────────────────┘
```

### 3.3 `VideoReader` Thread Changes

The `thread_reader` loop is extended with two new phases that execute **before** the
normal `read_one()` call on every iteration:

#### Phase 1 — Seek

```python
seek_target = ctrl.consume_seek()   # atomically read and clear pending seek
if seek_target is not None:
    cap.set(CAP_PROP_POS_FRAMES, seek_target)   # jump to nearest I-frame
    # read forward to exact target (I-frame compensation)
    while cap.get(CAP_PROP_POS_FRAMES) < seek_target:
        cap.read()
    _just_seeked = True
    _seek_target_frame = seek_target
```

`_just_seeked` is a local flag that survives into Phase 2, forcing one normal read even
if the player is currently paused.  This ensures the frozen image is updated to the
seek-target frame before re-entering the freeze loop.

#### Phase 2 — Freeze (pause)

```python
if ctrl.should_freeze() and not _just_seeked:
    if last_image is not None:
        extras = {'frame_n': current_frame_n, 'frame_repeat': True}
        deque.append((last_image, time_ns(), extras))
        # throttle to natural FPS — respect sync_evt backpressure in sync mode
        wait_one_frame_period()
    continue   # skip normal read
```

Re-emitting the same image at the natural frame rate is important: it keeps the pipeline
throughput stable so `FilterSubjectDataIn` continues to receive frames and can serve
API queries while paused.

#### Phase 3 — Normal read

After the seek and freeze phases the normal `read_one()` executes.  The only addition is
populating the `extras` dict:

```python
frame_n = cap.get(CAP_PROP_POS_FRAMES) - 1
extras  = {'frame_n': frame_n}
if _just_seeked:
    extras['seek_reset']       = True
    extras['seek_frame_index'] = _seek_target_frame
    _just_seeked = False
ctrl.on_frame_emitted(frame_n)
deque.append((image, tframe, extras))
```

#### Deque format change

| Before | After |
|---|---|
| `(image, tframe)` | `(image, tframe, extras)` |

`extras` is always present (empty dict `{}` when no replay controller is attached).
`VideoReader.read()` and `MultiVideoReader.read()` are updated to handle the new
three-tuple.  The public `read(with_tframe=False)` return type is backward-compatible:
`read()` still returns `image`, `read(with_tframe=True)` now returns
`(image, tframe, extras)`.

### 3.4 Metadata Injected into Every Frame

`VideoIn.process()` maps `extras` to standard `meta` keys:

| `meta` key | Type | When present | Meaning |
|---|---|---|---|
| `frame_index` | `int` | replay mode | 0-based position in the video file |
| `total_frames` | `int` | replay mode | total frames in the file |
| `frame_repeat` | `bool` | paused | this frame is a re-emission; do not advance data cursor |
| `seek_reset` | `bool` | first frame after seek | a seek just occurred |
| `seek_frame_index` | `int` | seek | exact target frame index |
| `seek_ts` | `float` | seek | target timestamp in seconds |

### 3.5 `FilterSubjectDataIn` Sync Contract

`FilterSubjectDataIn._lookup()` already handles all three signals for
`sync_key='sequential'` (the recommended mode for replay):

```
frame_repeat=True  →  return stored_frames[cursor - 1]  (no advance)
seek_reset=True    →  cursor = seek_frame_index          (jump)
(normal)           →  return stored_frames[cursor]; cursor += 1
```

No changes to `FilterSubjectDataIn` were required.

### 3.6 New Config Fields

| Field | Type | Default | Env var |
|---|---|---|---|
| `control_port` | `int \| None` | `None` | `VIDEO_IN_CONTROL_PORT` |
| `sdi_url` | `str` | `http://localhost:8090` | `VIDEO_IN_SDI_URL` |
| `webvis_url` | `str` | `http://localhost:8000` | `VIDEO_IN_WEBVIS_URL` |
| `webvis_topic` | `str` | `viz` | `VIDEO_IN_WEBVIS_TOPIC` |

### 3.7 HTTP API (served on `control_port`)

Identical to the `SeekableVideoIn` / `VideoController` API:

| Method | Path | Description |
|---|---|---|
| `POST` | `/pause` | Pause playback |
| `POST` | `/play` | Resume playback |
| `POST` | `/step?frames=N` | Advance N frames while paused |
| `POST` | `/seek?frame=N` | Seek to frame N |
| `POST` | `/seek?ts=12.3` | Seek to timestamp (seconds) |
| `GET` | `/status` | JSON status (frame, ts, fps, total_frames, …) |
| `GET` | `/video` | Stream the local MP4 with Range support |
| `GET` | `/player` | HTML5 browser player with scrubber and overlay |

---

## 4. Alternatives Considered

### 4.1 Keep `SeekableVideoIn` as the Canonical Replay Filter

**Rejected.** Requires users to change filter class names in all replay pipelines, and
creates an ongoing maintenance split between two implementations of the same
video-reading logic.

### 4.2 Subclass `VideoIn` into `SeekableVideoIn`

**Rejected.** The seek and freeze logic lives deep inside `VideoReader.thread_reader`,
which is not designed for inheritance.  Subclassing would require making private methods
public and would still result in two filter classes.

### 4.3 External Sidecar Process

An external process could intercept the ZMQ stream and inject replay metadata.
**Rejected** because it adds a network hop and cannot inject frame-accurate metadata
without reading the video itself.

---

## 5. Backward Compatibility

| Scenario | Behavior |
|---|---|
| `control_port` not set | Identical to previous `VideoIn` — zero overhead |
| `control_port` set, package missing | Warning logged, replay disabled, pipeline continues |
| Multi-source VideoIn with `control_port` | All `VideoReader`s share one controller — all cameras pause/seek together |
| `SeekableVideoIn` users | No change — filter is preserved |

The only breaking change is the internal deque format `(image, tframe)` →
`(image, tframe, extras)`.  This is entirely internal to `VideoReader` / `MultiVideoReader`
and does not affect the public `Frame` API or any downstream filter.

---

## 6. Testing

All 10 existing `VideoIn` unit tests pass without modification (except updating one
`test_normalize_config` assertion to include the three new default config keys).

Integration testing is performed via:

```bash
cd filter-subject-data-in
VIDEO_FILE="./video.mp4" \
RECORDING_FILE="file://./recordings/session.jsonl" \
SYNC_KEY="sequential" \
CONTROL_PORT=8092 VIDEO_CONTROL_PORT=8091 FILTER_LOOP=true \
./examples/seekable_replay_pipeline.sh
# open http://localhost:8091/player?sdi=http://localhost:8092
```

Manual verification checklist:
- [ ] Play/pause toggles video and bounding boxes simultaneously
- [ ] Bounding boxes do not move while paused
- [ ] Seek repositions video and bounding boxes to the correct frame
- [ ] Step +1 / −1 advances/rewinds exactly one frame
- [ ] Scrubber drag commits seek and re-aligns overlay
- [ ] Keyboard shortcuts work (`Space`, `←`, `→`, `J`, `L`)
- [ ] Pipeline view (MJPEG) shows annotated frames matching the scrubber position

---

## 7. Files Changed

| File | Change |
|---|---|
| `openfilter/filter_runtime/filters/video_in.py` | Core implementation (+237 lines) |
| `tests/test_filter_video_in.py` | Update `test_normalize_config` expected config |
