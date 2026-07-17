# Design Doc: Seekable Replay API for `VideoIn`

**Branch:** `feat/video-in-seekable-replay`  
**Status:** Implemented  
**Author:** Tales Rodrigues  
**Date:** 2026-07-07

---

## 1. Motivation

Replay pipelines re-process a recorded video alongside its stored subject-data
(detections, tracks, classifications) so operators can review, audit, or debug
pipeline output frame by frame:

```
VideoIn ──► FilterSubjectDataIn ──► Webvis
             (recorded data)         (browser viewer)
```

Before this change, `VideoIn` had no way to pause, seek, or step through a video at
runtime. Every emitted frame carried only a wall-clock timestamp (`ts`), which made
it impossible for downstream filters such as `FilterSubjectDataIn` to stay synchronized
after any interactive operation:

- **After a seek** — `FilterSubjectDataIn`'s sequential cursor kept advancing from the
  old position, overlaying data from the wrong point in time.
- **While paused** — the same image was re-emitted but the cursor still advanced, so
  bounding boxes kept moving on a frozen frame.

The goal is to add full interactive replay controls directly to `VideoIn`, activated
only when the operator sets the new `control_port` field, with no impact on existing
users.

---

## 2. Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  VideoIn process                                               │
│                                                                │
│  ┌──────────────────────────────────┐                         │
│  │  VideoReader (background thread) │                         │
│  │                                  │   (image, tframe,       │
│  │  loop:                           │    extras)              │
│  │    1. consume_seek()  ──────────►│──────────────────►      │
│  │       seek accurate              │   Deque(maxlen=1)       │
│  │    2. should_freeze()            │        │                │
│  │       re-emit last image         │        │                │
│  │    3. read_one() → frame         │        │                │
│  │       inject extras              │        ▼                │
│  └──────────────┬───────────────────┘  VideoIn.process()      │
│                 │                        reads deque           │
│                 │                        builds Frame{meta}   │
│         ┌───────▼──────────┐                                  │
│         │  VideoController │  HTTP :control_port              │
│         │  (state machine) │◄──────────────────────────────── │◄── browser / curl
│         │                  │                                  │
│         │  is_paused       │  POST /pause                     │
│         │  seek_target     │  POST /play                      │
│         │  current_frame   │  POST /step?frames=N             │
│         │                  │  POST /seek?frame=N              │
│         │                  │  POST /seek?ts=12.3              │
│         │                  │  GET  /status                    │
│         │                  │  GET  /video  (MP4 stream)       │
│         │                  │  GET  /player (browser UI)       │
│         └──────────────────┘                                  │
└────────────────────────────────────────────────────────────────┘
                │
                │  Frame { meta: { frame_index, total_frames,
                │                  seek_reset, seek_frame_index,
                │                  seek_ts, frame_repeat } }
                ▼
┌──────────────────────────────────────────────────────┐
│  FilterSubjectDataIn  (sync_key='sequential')        │
│                                                      │
│  frame_repeat = True  →  cursor unchanged            │
│  seek_reset   = True  →  cursor = seek_frame_index   │
│  (normal)             →  cursor += 1                 │
└──────────────────────────────────────────────────────┘
```

Three threads cooperate:

| Thread | Role |
|---|---|
| **HTTP thread** (VideoController) | Receives operator commands, writes `is_paused` / `seek_target` under a mutex |
| **VideoReader thread** | Reads frames from disk, checks controller state each iteration, writes `(image, tframe, extras)` to a `Deque(maxlen=1)` |
| **Main thread** (VideoIn.process) | Reads from deque, builds `Frame` objects with replay metadata, sends downstream |

---

## 3. What Changed

### 3.1 New configuration fields

| Field | Type | Default | Env var |
|---|---|---|---|
| `control_port` | `int \| None` | `None` (disabled) | `VIDEO_IN_CONTROL_PORT` |
| `sdi_url` | `str` | `http://localhost:8090` | `VIDEO_IN_SDI_URL` |
| `webvis_url` | `str` | `http://localhost:8000` | `VIDEO_IN_WEBVIS_URL` |
| `webvis_topic` | `str` | `viz` | `VIDEO_IN_WEBVIS_TOPIC` |

Setting `control_port` is the only opt-in required. Existing configurations without it
are completely unaffected.

### 3.2 `VideoReader` — seek, freeze, and extras

The `thread_reader` loop gains two new phases that execute **before** the normal
`read_one()` call on every iteration.

#### Phase 1 — Seek (highest priority)

```python
seek_target = ctrl.consume_seek()   # atomic read-and-clear
if seek_target is not None:
    cap.set(cv2.CAP_PROP_POS_FRAMES, seek_target)   # jump to nearest I-frame
    actual = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
    while actual < seek_target:                      # forward-read compensation
        cap.read()
        actual += 1
    self._frame_n      = seek_target
    _just_seeked       = True
    _seek_target_frame = seek_target
```

`cv2.VideoCapture` can only seek to I-frames (keyframes). For H.264/HEVC files the
nearest I-frame may be several frames before the target. The forward-read loop
compensates by decoding and discarding intermediate frames until the exact target
position is reached.

`_just_seeked` survives into Phase 2. It forces one normal read even when the player
is paused so that the frozen image is updated to the seek-target frame before the
freeze loop resumes.

#### Phase 2 — Freeze (pause)

```python
if ctrl.should_freeze() and not _just_seeked:
    if self._last_replay_img is not None:
        freeze_extras = {'frame_n': self._frame_n, 'frame_repeat': True}
        self.deque.append((self._last_replay_img, time_ns(), freeze_extras))
        notify_cond()
        # throttle: respect sync_evt in sync mode, sleep ns_per_fps otherwise
        if sync_evt:
            sync_evt.wait(); sync_evt.clear()
        else:
            sleep((ns_per_fps or ns_per_maxfps or 40_000_000) / 1e9)
    else:
        sleep(0.04)
    continue   # skip Phase 3
```

Re-emitting the last image at the natural frame rate keeps pipeline throughput stable —
`FilterSubjectDataIn` continues to receive frames and can serve API queries while the
operator is paused. The throttle prevents the thread from spinning at CPU speed.

#### Phase 3 — Normal read

```python
image = self.read_one()                         # existing timing / loop logic
frame_n = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
self._frame_n         = frame_n
self._last_replay_img = image                   # stored for future freeze

extras = {'frame_n': frame_n}
if _just_seeked:
    extras['seek_reset']       = True
    extras['seek_frame_index'] = _seek_target_frame
    _just_seeked = False

ctrl.on_frame_emitted(frame_n)
self.deque.append((image, tframe, extras))
```

#### Deque format

| Before | After |
|---|---|
| `(image, tframe)` | `(image, tframe, extras)` |

`extras` is always a dict (empty `{}` when replay mode is not active). `VideoReader.read()`
and `MultiVideoReader.read()` are updated to handle the three-tuple. The public
`read(with_tframe=False)` return type is backward-compatible.

### 3.3 Sync metadata on every Frame

`VideoIn.process()` maps `extras` to standard `meta` keys on the outgoing `Frame`:

| `meta` key | Present when | Meaning |
|---|---|---|
| `frame_index` | replay mode, every frame | 0-based position in the video file |
| `total_frames` | replay mode, every frame | total frames in the file |
| `frame_repeat` | paused | re-emitted frame; do not advance data cursor |
| `seek_reset` | first frame after a seek | a seek just occurred |
| `seek_frame_index` | seek | exact target frame index |
| `seek_ts` | seek | target timestamp in seconds |

`FilterSubjectDataIn` already handles all three signals for `sync_key='sequential'`:

```
frame_repeat = True  →  return stored_frames[cursor - 1]   (cursor unchanged)
seek_reset   = True  →  cursor = seek_frame_index           (jump)
(normal)             →  return stored_frames[cursor]; cursor += 1
```

No changes to `FilterSubjectDataIn` were required.

### 3.4 `VideoController` wiring in `VideoIn.setup()`

```python
if config.control_port:
    ctrl = VideoController(
        total_frames = primary_vid._total_frames,
        fps          = primary_vid.fps or 30.0,
        source       = primary_src,
        local_path   = local_path,          # for /video streaming
    )
    ctrl.start_server(
        config.control_port,
        sdi_url      = config.sdi_url,
        webvis_url   = config.webvis_url,
        webvis_topic = config.webvis_topic,
    )
    # wire into every VideoReader so all cameras pause/seek together
    for vid in self.mvreader.videos:
        vid._replay_ctrl = ctrl
```

If the `filter_subject_data_in` package is not installed the warning is logged and
`control_port` is silently ignored — the filter runs in normal streaming mode.

---

## 4. Synchronization Guarantee

The table below shows the exact state machine for `FilterSubjectDataIn`
`sync_key='sequential'` — the recommended mode for replay:

| Event | VideoIn emits | FilterSubjectDataIn action |
|---|---|---|
| Normal frame | `frame_index=N` | `stored_frames[cursor]; cursor += 1` |
| Paused frame | `frame_repeat=True` | `stored_frames[cursor-1]` — cursor frozen |
| First frame after seek | `seek_reset=True`, `seek_frame_index=K` | `cursor = K` then `stored_frames[K]` |

Because the control happens **inside the thread that reads the video** — before any frame
is placed in the deque — there is no window where a frame can be emitted without the
correct metadata. The seek and freeze decisions are made atomically with the cap read.

---

## 5. Backward Compatibility

| Scenario | Behavior |
|---|---|
| `control_port` not set | Identical to previous `VideoIn` — zero overhead |
| `control_port` set, package missing | Warning logged, replay disabled, pipeline continues |
| Multi-source `VideoIn` with `control_port` | All `VideoReader`s share one controller — all cameras pause/seek together |

---

## 6. Files Changed

| File | Change |
|---|---|
| `openfilter/filter_runtime/filters/video_in.py` | Core implementation (+237 lines) |
| `tests/test_filter_video_in.py` | Update `test_normalize_config` for new default config keys |
