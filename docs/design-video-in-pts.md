# Design Note: Decoder pts_s / src_frame in `VideoIn` Frame Meta

Status: proposed with PR #128. Prior art: the CPD hybrid-RAG specs (internal-chicagopd PR 2,
spec 01) establish that jump-to-frame requires a decoder-derived video offset; this note records
how that need lands on openfilter core's public surface.

## 1. The frame-meta contract

For **file sources** (`file://`, `s3://`) every emitted frame's `meta` gains:

| Key | Type | Semantics |
|---|---|---|
| `src_frame` | `int` | 0-based source frame index of the delivered frame: `CAP_PROP_POS_FRAMES` sampled immediately **before** the successful `cap.read()`. Exact on every backend. |
| `pts_s` | `float` | Presentation timestamp in seconds. Primary: `src_frame / container_fps` (nominal CFR timeline). Fallback: `CAP_PROP_POS_MSEC / 1000` only when the container reports no frame rate at all. Omitted when neither is trustworthy (`src_frame` remains present and exact). |

Stream (`rtsp://` etc.) and webcam sources have no meaningful decoder position: both keys are
**absent** and the rest of `meta` (`id`, `ts`, `src`, `src_fps`) is byte-for-byte unchanged.

## 2. Core vs. companion filter

This belongs in `VideoIn`, not a companion filter: the decoder position at read time exists only
inside `VideoReader`'s reader thread, in the same iteration as the `cap.read()` that consumes it.
Once the frame leaves the reader, `id` advances at the consuming chain's rate and `ts` is
wall-clock, so no downstream filter can reconstruct the offset. Recorded decision, per review.

## 3. Reader tuple shape and coordination with Seekable Replay (#118)

`VideoReader.read(with_tframe=True)` / `MultiVideoReader.read(with_tframe=True)` return
`(image, tframe, extras)` — the **same extensible extras-dict shape PR #118 introduces** — where
`extras` is `{}` for non-file sources and `{'frame_n': int, 'pts_s': float}` (pts optional) for
files. This is an accepted, release-noted break of the old 2-tuple (see §5); the dict absorbs
future keys without another arity break.

Merge plan with `feat/video-in-seekable-replay`:

- **Tuple shape**: identical on both branches — the deque/`read()` conflict resolves to the same
  code, and `extras` merges by key union (`frame_n` is the same key, computed to the same value:
  #118 reads `POS_FRAMES - 1` after the read, this PR reads `POS_FRAMES` before it).
- **Single choke point**: `VideoReader._cap_read()` is the only place this branch reads
  `self.cap`, and its docstring marks it as such. #118's post-seek path currently calls raw
  `cap.read()` for forward-read compensation; whichever PR merges second must route that read
  through `_cap_read()` (compensation frames are discarded, so the cost is nil, and the first
  *delivered* post-seek frame then carries correct `pts_s`/`src_frame`).
- **Meta naming**: `src_frame` (this PR) and `frame_index` (#118) are the same value at meta
  level. One name must survive; this PR has no attachment to `src_frame` — if #118 lands first we
  adopt `frame_index` and keep `pts_s`; if this lands first, #118 rebases its `frame_index` onto
  `src_frame` or renames ours. Either way the second-to-merge PR emits a single key.

## 4. VFR position (stated intent)

The primary path deliberately treats **every fps-reporting source as CFR**. A true-VFR file that
reports an average rate gets a nominal timeline (`frame_n / avg_fps`) which can drift from the
container's real pts — but it is deterministic and exact under the inverse mapping
(`offset * avg_fps`) that consumers use to seek by frame, so jump-to-frame round-trips to the
same frame, which is the contract's purpose. Switching such files to `POS_MSEC` is not a safe
upgrade: `POS_MSEC` exhibits B-frame presentation reordering and reports 0 on several
container/backend combos (both reproduced by the repo's own test clip), with no way to tell a
true pts from a lie at runtime. `POS_MSEC` is therefore used only for containers reporting no
frame rate at all, and only while it looks sane (nonzero past frame 0); otherwise `pts_s` is
omitted rather than emitted wrong. Consumers needing true per-frame VFR timestamps should demux
container pts out-of-band (e.g. PyAV); that is out of scope for `VideoIn`.

## 5. Back-compat position

`VideoReader` / `MultiVideoReader` are exported in `__all__` of the published package: the
2-tuple → 3-tuple change under `with_tframe=True` is an **accepted break with a RELEASE.md
"Breaking Changes" callout**, identical in shape and wording to the one #118 already declares —
after both merge, external callers see one break, not two. `with_tframe=False` (the default) and
all `VideoIn`-level behavior for non-file sources are unaffected.
