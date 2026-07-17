# Design Doc: Seekable Replay API for `VideoIn`


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
│         │  (external pkg)  │◄──────────────────────────────── │◄── browser / curl
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

**Separation of concerns:** HTTP control + `/player` + `/video` live in
`filter_subject_data_in.video_controller.VideoController` (optional dependency).
`VideoIn` only wires it when `control_port` is set and keeps seek/freeze inside
`VideoReader` because those decisions must gate which frames enter the deque
(frame production, not browser viewing). Webvis remains the dedicated filter for
live pipeline visualization; the VideoController player is a replay-control UI.

Three threads cooperate:

| Thread | Role |
|---|---|
| **HTTP thread** (VideoController) | Receives operator commands, writes `is_paused` / `seek_target` under a mutex |
| **VideoReader thread** | Reads frames from disk, checks controller state each iteration, writes `(image, tframe, extras)` to a `Deque(maxlen=1)` |
| **Main thread** (VideoIn.process) | Reads from deque, builds `Frame` objects with replay metadata, sends downstream |

---

## 3. What Changed

### 3.1 New configuration fields

| Field | Type | Default | Env vars (legacy `VIDEO_IN_*` takes precedence) |
|---|---|---|---|
| `control_port` | `int \| None` | `None` (disabled) | `VIDEO_IN_CONTROL_PORT` / `FILTER_CONTROL_PORT` |
| `sdi_url` | `str` | `http://localhost:8090` | `VIDEO_IN_SDI_URL` / `FILTER_SDI_URL` |
| `webvis_url` | `str` | `http://localhost:8000` | `VIDEO_IN_WEBVIS_URL` / `FILTER_WEBVIS_URL` |
| `webvis_topic` | `str` | `viz` | `VIDEO_IN_WEBVIS_TOPIC` / `FILTER_WEBVIS_TOPIC` |

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
frame_n = int(cap.get(CAP_PROP_POS_FRAMES)) - 1
self._frame_n         = frame_n
self._last_replay_img = image                   # stored for future freeze

extras = {'frame_n': frame_n}
if _just_seeked:
    # Always emit seek_frame_index == frame_n so downstream sync cannot desync
    # if OpenCV undershoots the requested target after I-frame compensation.
    if frame_n != _seek_target_frame:
        logger.warning(...)
    extras['seek_reset']       = True
    extras['seek_frame_index'] = frame_n
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
`read(with_tframe=False)` return type is backward-compatible (returns image only).

### 3.3 Sync metadata on every Frame

`VideoIn.process()` maps `extras` to standard `meta` keys on the outgoing `Frame`.

#### Always-present keys (unchanged semantics)

| `meta` key | Meaning |
|---|---|
| `id` | Monotonic **emit** counter (pipeline order). Advances on every emit including freeze re-emits. **Not** file position. |
| `ts` | Wall-clock emit time in seconds (`time_ns()`). **Not** video-relative. |
| `src` / `src_fps` | Source URI and FPS |

#### Replay Sync Meta Spec v1 (only when `control_port` is active)

| `meta` key | Present when | Meaning |
|---|---|---|
| `frame_index` | every frame | 0-based position in the video file — **trust this for sync** |
| `total_frames` | every frame | total frames in the file |
| `frame_repeat` | paused | re-emitted frame; do not advance data cursor |
| `seek_reset` | first frame after a seek | a seek just occurred |
| `seek_frame_index` | seek | actual decoded frame index (= `frame_index` on that frame) |
| `seek_ts` | seek | `seek_frame_index / src_fps` |

**Downstream consumers:**

| Consumer | Behavior |
|---|---|
| `FilterSubjectDataIn` `sync_key='sequential'` | Honors `frame_repeat` / `seek_reset` / `seek_frame_index` |
| `FilterSubjectDataIn` `sync_key='ts'` (and others) | **Ignores** these signals — do not use interactive seek/pause if sync must hold |
| Third-party filters | May rely on Replay Sync Meta Spec v1 keys above |

`FilterSubjectDataIn` sequential mode:

```
frame_repeat = True  →  return stored_frames[cursor - 1]   (cursor unchanged)
seek_reset   = True  →  cursor = seek_frame_index           (jump)
(normal)             →  return stored_frames[cursor]; cursor += 1
```

### 3.4 `VideoController` wiring in `VideoIn.setup()`

```python
if config.control_port:
    if not _HAS_VIDEO_CONTROLLER:
        raise RuntimeError(...)   # fail loud — operator explicitly requested controls
    ctrl = VideoController(...)
    ctrl.start_server(config.control_port, ...)
    for vid in self.mvreader.videos:
        vid._replay_ctrl = ctrl
```

---

## 4. Synchronization Guarantee

The table below shows the exact state machine for `FilterSubjectDataIn`
`sync_key='sequential'` — the recommended (and currently only supported) mode for
interactive replay:

| Event | VideoIn emits | FilterSubjectDataIn action |
|---|---|---|
| Normal frame | `frame_index=N` | `stored_frames[cursor]; cursor += 1` |
| Paused frame | `frame_repeat=True` | `stored_frames[cursor-1]` — cursor frozen |
| First frame after seek | `seek_reset=True`, `seek_frame_index=K` (= `frame_index`) | `cursor = K` then `stored_frames[K]` |

Because the control happens **inside the thread that reads the video** — before any frame
is placed in the deque — there is no window where a frame can be emitted without the
correct metadata. The seek and freeze decisions are made atomically with the cap read.

On the first post-seek frame, `frame_index` and `seek_frame_index` are forced equal to
the **actual** decoded position (not the requested target) so an OpenCV undershoot cannot
desync the SDI cursor from the displayed frame.

---

## 5. Backward Compatibility

| Scenario | Behavior |
|---|---|
| `control_port` not set | Identical to previous `VideoIn` — zero overhead |
| `control_port` set, package missing | **`RuntimeError` in `setup()`** — pipeline does not start |
| Multi-source `VideoIn` with `control_port` | All `VideoReader`s share one controller — all cameras pause/seek together |

---

## 6. Files Changed

| File | Change |
|---|---|
| `openfilter/filter_runtime/filters/video_in.py` | Seek/freeze in VideoReader; Replay Sync Meta Spec v1; dual-prefix env vars; fail-loud setup; `seek_frame_index == frame_index` post-seek |
| `tests/test_filter_video_in.py` | Unit tests for env aliases, missing package, seek compensation, freeze re-emit, deque 3-tuple, multi-source shared controller, post-seek index equality |
| `docs/design-video-in-seekable-replay.md` | This document |

---

## 7. Review comment resolutions

| # | Comment | Resolution |
|---|---|---|
| 1 | HTTP/player should not live in VideoIn | **Done.** `VideoController` (HTTP + `/player` + `/video`) lives in `filter_subject_data_in`. VideoIn only wires it. Seek/freeze stay in `VideoReader` as frame-production concerns. Documented in §2. |
| 2 | Env-var dual-prefix | **Done.** `VIDEO_IN_*` / `FILTER_*` for `CONTROL_PORT`, `SDI_URL`, `WEBVIS_URL`, `WEBVIS_TOPIC` (legacy takes precedence). Transitional `FILTER_VIDEO_*` still accepted. |
| 3 | `id` vs `frame_index` ambiguity | **Done.** Documented in §3.3 and class docstring: `id` = emit counter, `ts` = wall-clock, `frame_index` = file position (trust for sync). |
| 4 | Hidden cross-filter contract | **Done.** Published as **Replay Sync Meta Spec v1** with consumer table; sequential-only; `ts` mode explicitly ignores signals. |
| 5 | Silent failure when package missing | **Done.** `setup()` raises `RuntimeError` when `control_port` is set but the package is missing. |
| 6 | `frame_index` ≠ `seek_frame_index` after seek | **Done.** Post-seek frame always sets `seek_frame_index = frame_n` (actual decoded position); WARNING if request undershot. Covered by unit test. |
| 7 | Test coverage | **Done.** Added unit tests listed in §6. |
