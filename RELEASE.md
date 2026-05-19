# Changelog

OpenFilter Library release notes

## v1.0.0 - 2026-05-18

**A new foundation for production Vision AI.** OpenFilter 1.0 transitions the runtime from an evolving framework into a stable, production-grade platform. The new typed configuration surface is purely additive — the legacy `dict`-based `FilterConfig` coexists alongside it, so unmigrated filters keep working through the runtime fallback. Behavioral changes that *do* require filter-side updates are scoped to the items called out under `### Breaking Changes` below.

### Declarative Configuration Foundations

Each filter can now publish a build-time JSON Schema artifact alongside the runtime validation OpenFilter has always done — consumers can validate, document, and render configuration UIs against a filter without ever running it.

- **Typed `FilterConfigBase` with `emit_schema()`** ([FILTER-441](https://plainsight-ai.atlassian.net/browse/FILTER-441), #86): filters can declare their config surface as a pydantic model and emit it as JSON Schema (draft 2020-12) for build-time consumption. `Managed` / `Resolve` helpers mark fields as orchestrator-controlled or platform-resolved.
- **`FilterOutputSchema` + `frame.data` shape catalog** ([FILTER-444](https://plainsight-ai.atlassian.net/browse/FILTER-444), #88): declarative `frame.data` shape declaration. The catalog at `openfilter.filter_runtime.shapes` ships canonical types — `BoundingBox`, `Polygon`, `Mask`, `Keypoint`, `Detection`, `DetectionSet`, `Track`, `TrackSet`, `Pose`, `PoseSet`, `KeypointSet`, `OCRSpan`, `OCRSpanSet`, `ClassificationResult` — with stable `$id`s under `https://schemas.plainsight.ai/shapes/<kebab>/v1`. Filters reference shapes via `$ref` instead of negotiating dialects out-of-band.
- **`openfilter emit-schema` CLI** ([FILTER-442](https://plainsight-ai.atlassian.net/browse/FILTER-442), #87): emits a filter's JSON Schema to stdout or `-o <path>`. Auto-detects the canonical class in a module or accepts `module:Class` to disambiguate.

Reference migrations ship in `filter-template` and `filter-sam3-detector`; every other filter in the library keeps working unchanged through the runtime fallback.

### Backward-Compatible Runtime Improvements

Two runtime improvements teams have been asking for, landed underneath the compatibility surface:

- **Zero-copy shared-memory transport** between co-located filters (#82) — eliminates inter-stage serialization on the same host.
- **Batched inference** via `process_batch()` and `batch_size > 1` (#61, v0.1.29) — meaningful throughput gains for SAM3, YOLO, and transformer-OCR filters that benefit from batched forward passes.

### Production-Grade Engineering

- **First-class observability**: per-filter OpenTelemetry distributed tracing (#79), OpenLineage events (v0.1.5), per-frame timing metrics, and a turn-key Grafana stack (v0.1.21–22). Wall-clock latency dashboards separate `process()` time from ZMQ and queue overhead.
- **Supply-chain hygiene**: SLSA provenance and SBOM attestations on every Docker image; token auth and CORS for HTTP-exposed filters (v0.1.30).
- **GPU and deployment ergonomics**: framework-agnostic GPU detection via `ctypes` (v0.1.28); GKE-compatible `LD_LIBRARY_PATH` injection (v0.1.26), so CUDA-dependent images deploy without per-cluster fixups.
- **Filter library refresh**: new `ImageIn` / `ImageOut` filters for still-image pipelines (#21, #29); `VideoIn` moved off `vidgear` to `cv2` / PyAV (#66, #67) for stability against odd-codec sources.

### Breaking Changes

- **OTLP gRPC `insecure` flag now inferred from endpoint scheme** (#90): the exporter factory and tracing builder use `urllib.parse.urlparse` on the configured endpoint — `http://` infers plaintext, `https://` infers TLS, and bare `host:port` infers TLS (secure default, matches the OTel SDK). Deployments configuring bare-host endpoints against plaintext collectors must prefix `http://` to maintain prior behavior. Explicit `insecure=` in `exporter_config` / kwargs always wins.
- **Received `Frame.image` arrays are read-only** (v0.1.28, re-surfaced for the SemVer-stable cut): `topicmsgs2frames` sets `image.flags.writeable = False` on both the zero-copy ZMQ and SHM transport paths — this prevents corruption of shared ring slots and re-enables the `Frame.copy()` share-buffer fast path and `Frame.jpg` encode caching, both of which gate on read-only status. Filters that mutate `frame.image` in place (e.g. `cv2.rectangle(frame.image, ...)`, `frame.image[y, x] = ...`) must take a local copy first — `image = frame.image.copy()` — or construct a new frame via `Frame(new_image, frame, frame.format)`. **Symptom if not migrated:** `ValueError: assignment destination is read-only` raised from the mutating call.

### Stability commitments

Surfaces committed under 1.0 — breaking changes will require a 2.0 bump:

- `openfilter.filter_runtime.FilterConfigBase` and its `Managed` / `Resolve` field shorthands, including the `ResolveHint` literal that parameterizes them
- `openfilter.filter_runtime.FilterOutputSchema` and the shape catalog in `openfilter.filter_runtime.shapes`
- The `openfilter emit-schema` CLI

The legacy `dict`-based `FilterConfig` continues to coexist with `FilterConfigBase` — unmigrated filters keep working unchanged.

### Removed

- **`OTLP_GRPC_ENDPOINT_SECURITY` environment variable** (#90): was previously a no-op — `os.getenv(name, True)` returned the literal `True` only when unset; any *set* value came back as a truthy string, so `insecure=True` regardless of operator intent.

### Fixed

- **Silent `$id` inheritance on `FilterOutputSchema` subclasses** ([FILTER-452](https://plainsight-ai.atlassian.net/browse/FILTER-452), #88): subclasses no longer silently inherit a parent's `$id`. `__init_subclass__` refuses ambiguous construction at class-definition time.
- **`test_topo_balance_step` shutdown race on Python 3.10** ([FILTER-461](https://plainsight-ai.atlassian.net/browse/FILTER-461), #94): the `TestFilterOld` topology tests poll for runner termination instead of asserting on a single `step()` call after the shutdown sentinel. Test-only change; no runtime impact.

### Infrastructure

- **`gh release create` uses `secrets.GH_BOT_USER_PAT`** ([FILTER-462](https://plainsight-ai.atlassian.net/browse/FILTER-462), #97) so the release-tag push triggers `cascade-on-tag.yaml` automatically. Workflow `permissions:` tightened to `contents: read`.
- **Tag-triggered bump-PR cascade** ([DT-145](https://plainsight-ai.atlassian.net/browse/DT-145), #85): `cascade-on-tag.yaml` workflow + `scripts/cascade/*` replace the previous `cloudbuild-cascade.yaml` mechanism. Fires on release-semver tag push, discovers eligible `filter-*` consumers, opens mechanical bump PRs through `gh-actions-public/open-mechanical-pr`.
- **Cascade widens consumer pyproject upper bounds when target excludes them** (#93): 1.0+ targets widen to next-major (`<2.0.0`).

## v0.2.1 - 2026-05-16

This release rolls up the `v0.2.0` declarative-configuration work (FILTER-441 / FILTER-442 / FILTER-444 / FILTER-452) and the `v0.2.1` OTLP TLS inference change ([#90](https://github.com/PlainsightAI/openfilter/pull/90)) under a single tag. `v0.2.0` was never tagged — its contents ship here under `v0.2.1`. Also folded in: the DT-145 cascade infrastructure (#85 / #93) and the FILTER-461 test-fragility fix (#94), all merged after the original `v0.2.0` changelog window.

### Added

- **Typed `FilterConfigBase` with `emit_schema()` ([FILTER-441](https://plainsight-ai.atlassian.net/browse/FILTER-441))**: New `openfilter.filter_runtime.FilterConfigBase` lets filters declare their config surface as a pydantic model and emit it as JSON Schema (draft 2020-12) for build-time consumption. Includes `Managed` / `Resolve` helpers for marking fields as orchestrator-controlled or platform-resolved, plus `MANAGED_KEY` / `RESOLVE_KEY` / `PREFLIGHT_KEY` extensions stamped onto the emitted schema. Fully opt-in — existing `dict`-based `FilterConfig` continues to work unchanged. (#86)
- **`openfilter emit-schema` CLI ([FILTER-442](https://plainsight-ai.atlassian.net/browse/FILTER-442))**: New CLI subcommand writes a filter's JSON Schema to stdout or `-o <path>`. Auto-detects the canonical class in a module or accepts an explicit `module:Class` qualifier. Default `--kind config` emits a `FilterConfigBase` schema; `--kind output` emits a `FilterOutputSchema` (FILTER-444). `--include-managed` surfaces orchestrator-controlled fields for platform inspection; default is operator-facing surface only. (#87)
- **`FilterOutputSchema` + `frame.data` shape catalog ([FILTER-444](https://plainsight-ai.atlassian.net/browse/FILTER-444))**: New `openfilter.filter_runtime.FilterOutputSchema` lets filters declare what they place on `frame.data` as a build-time JSON Schema. The catalog at `openfilter.filter_runtime.shapes` ships canonical shapes — `BoundingBox`, `Polygon`, `Mask`, `Keypoint`, `Detection`, `DetectionSet`, `Track`, `TrackSet`, `Pose`, `PoseSet`, `KeypointSet`, `OCRSpan`, `OCRSpanSet`, `ClassificationResult` — with stable `$id`s under `https://schemas.plainsight.ai/shapes/<kebab>/v1`. Filters reference catalog shapes via `$ref` instead of negotiating dialects out-of-band. Coordinate conventions (pixel-space for bbox/polygon/mask; normalized `[0, 1]` for keypoints) are documented per shape with the production filter that motivated each choice. Catalog shapes carry runtime-only invariants enforced by pydantic validators: `BoundingBox` xyxy ordering (zero-area allowed, inverted rejected), `ClassificationResult` parallel-array length equality, and `Pose` 17-keypoint arity when `skeleton="coco-17"`. The whole FILTER-444 surface is re-exported from `openfilter.filter_runtime` so `from openfilter.filter_runtime import FilterOutputSchema, Detection` works the same way the FILTER-441 import idiom does. (#88)

### Changed

- **OTLP gRPC `insecure` flag now inferred from endpoint scheme**: The exporter factory and tracing builder now use `urllib.parse.urlparse` on the configured endpoint — `http://` infers plaintext, `https://` infers TLS, and bare `host:port` infers TLS (secure default, matches the OTel SDK). Explicit `insecure=` in `exporter_config` / kwargs always wins. The default `http://localhost:4317` endpoint still infers `insecure=True`, so local collectors keep working with no config change. The metrics factory's missing localhost fallback was also fixed in this change — an unset endpoint no longer falls through to the SDK's TLS default against a plaintext local collector. (#90)

### Fixed

- **Silent `$id` inheritance on `FilterOutputSchema` subclasses ([FILTER-452](https://plainsight-ai.atlassian.net/browse/FILTER-452))**: A subclass of any `$id`-bearing `FilterOutputSchema` (catalog shape or filter-author output) that did not explicitly override `__schema_id__` silently inherited the parent's `$id` on the wire, causing two distinct classes to claim the same JSON Schema identity for `$ref` resolution. `__init_subclass__` now refuses to construct such subclasses at class-definition time; authors must override `__schema_id__` with their own URI or set it to `None` as an explicit opt-out. (#88)
- **`test_topo_balance_step` shutdown race on Python 3.10 ([FILTER-461](https://plainsight-ai.atlassian.net/browse/FILTER-461))**: After PR #82's zero-copy IPC tightened pipeline timing, four `TestFilterOld` topology tests' shutdown assertions started failing on 3.10 — a single `runner.step()` immediately after `qout.put(None)` was racing the filters' drain-and-report path. New `wait_for_runner_exit` helper polls `step()` up to 5 s for the exit-codes list. Test-only change, no runtime impact. (#94)

### Removed

- **`OTLP_GRPC_ENDPOINT_SECURITY` environment variable**: removed from the metrics exporter factory. This variable was previously a full no-op — `os.getenv(name, True)` returned the literal `True` only when unset; any *set* value came back as a string, and every non-empty string is truthy, so `insecure=True` regardless of what an operator wrote. No deployment was getting TLS through this var. The actual behavior change for operators is narrow: those running with a bare `host:port` endpoint now get TLS, where they used to get plaintext. Set `insecure=True` in `exporter_config` (or use an `http://` URL) to keep plaintext. (#90)

### Infrastructure

- **Tag-triggered bump-PR cascade ([DT-145](https://plainsight-ai.atlassian.net/browse/DT-145))**: New `cascade-on-tag.yaml` workflow and `scripts/cascade/{discover.sh,bump-and-pr.sh,bump-strategy.sh,check_constraint.py}` replace the previous `cloudbuild-cascade.yaml` mechanism (`scripts/build-filters.sh` removed in the same change). Fires on release-semver tag push, discovers eligible `filter-*` consumers via the GitHub Contents API + PEP 621 specifier intersection, opens mechanical bump PRs through `PlainsightAI/gh-actions-public/open-mechanical-pr`. Auto-merge enabled by default on bot PRs; `workflow_dispatch` inputs (`dry_run`, `single_filter`, `filter_subset`, `auto_merge_override`) support staged rollouts. (#85)
- **Cascade widens consumer pyproject upper bounds when target excludes them**: `bump-strategy.sh` now rewrites `<X` / `<=X` upper bounds in consumer pyproject pins when the target openfilter version would otherwise be excluded. Rule: 0.X targets widen to next-minor; 1.0+ targets widen to next-major. Without this, every consumer pinning `>=0.1.30,<0.2.0` (the org-canonical pattern) would skip the cascade for any minor/major openfilter bump — 30 of 55 `filter-*` repos in the current sweep. Lower-bound exclusions (`>=X`) and `!=X` exclusions still skip per the prior behavior. (#93)

## v0.1.30 - 2026-04-21

### Added

- **Token authentication and configurable CORS for HTTP filters**: Webvis and REST filters now support opt-in token-based auth (`auth_token` / `FILTER_AUTH_TOKEN`) and configurable CORS origins (`cors_origins` / `FILTER_CORS_ORIGINS`). Auth accepts `?token=` query params (for `<img>` MJPEG embeds) or `Authorization: Bearer` headers. CORS preflight bypasses auth. Both are fully backwards compatible — unset means no auth and `Access-Control-Allow-Origin: *`.

### Changed

- **Shared security scan workflow**: Replaced standalone Grype security scan with the shared `PlainsightAI/gh-actions-public` reusable workflow.
- **GitHub Actions bumped to latest versions**: `actions/checkout` v4→v6, `actions/setup-python` v5→v6, `actions/upload-artifact` v4→v7, `actions/download-artifact` v4.1.3→v8, `docker/setup-buildx-action` v3→v4, `docker/login-action` v3→v4, `docker/build-push-action` v5→v6, `dorny/paths-filter` v3→v4, `mukunku/tag-exists-action` v1.6.0→v1.7.0. Resolves Node.js <24 deprecation warnings.
- **Docker images now include SLSA provenance and SBOM attestations** via `docker/build-push-action` v6 defaults.

### Fixed

- **CVE-2026-25645**: Bumped `requests` from ~=2.32.5 to ~=2.33.0.
- **GHSA-8rrh-rw8j-w5fx**: Bumped `wheel` from ~=0.45.1 to ~=0.46.2.
- **GHSA-cxww-7g56-2vh6**: Bumped `actions/download-artifact` from v4.1.3 to v8.
- **Docker image build race condition**: Added a `wait-for-pypi` step to the release workflow that polls PyPI until the newly published package is indexed before starting Docker image builds. Previously, some images could fail with `No matching distribution found` if PyPI index propagation hadn't completed.

## v0.1.29 - 2026-04-14

### Added

- **Frame accumulation support for batched processing**: Filters can now set `batch_size > 1` to accumulate frames and process them in batches via `process_batch()`. Includes timeout-based flushing, proper locking, and backward compatibility with single-frame `process()`.
- **Single batch watcher thread**: Replaced per-timeout `threading.Timer` with a single long-lived daemon thread for batch flush monitoring, reducing thread churn in high-throughput filters.

## v0.1.28 - 2026-04-13

### Breaking Changes

- **Received `Frame.image` arrays are now read-only**: `topicmsgs2frames` sets `image.flags.writeable = False` on both the zero-copy ZMQ path and the SHM path, so `frame.image` received from upstream can no longer be mutated in place.
- **Motivation**: prevents corruption of live SHM ring slots (reused round-robin by the sender) and re-enables the `Frame.copy()` share-buffer fast path and `Frame.jpg` encode caching, both of which gate on read-only status.
- **Migration**: filters that mutate `frame.image` in place (e.g. `cv2.rectangle(frame.image, ...)`, `frame.image[y, x] = ...`) must take a local copy first — `image = frame.image.copy()` — or construct a new frame via `Frame(new_image, frame, frame.format)`.
- **Symptom if not migrated**: `ValueError: assignment destination is read-only` raised from the mutating call.

### Added

- **OpenTelemetry distributed tracing for per-filter execution spans**: Filter runtime now emits OTel spans around each filter's processing step and propagates trace context through the observability client. A new `openfilter/observability/tracing.py` module wires up the SDK; `filter_runtime/filter.py` and `observability/client.py` were updated to start/stop spans and attach trace context. Trace context is consumed from standard OTel environment variables, allowing upstream controllers to stitch filter spans into a pipeline-wide trace.

### Changed

- **Framework-agnostic GPU detection via ctypes**: Replaced `torch.cuda` and `nvidia-smi` subprocess calls with direct `ctypes.CDLL` probing of CUDA/NVML shared libraries. Filters no longer need PyTorch installed just for GPU detection.

## v0.1.27 - 2026-04-03

### Fixed

- **Remove eager imports from `filters/__init__.py`**: The package-level `__init__.py` eagerly imported `VideoOut`, `ImageOut`, and `ImageIn`, which pulled in optional dependencies like PyAV (`av`). This crashed containers that only needed a subset of filters (e.g., `video-in` containers that don't have `av` installed). Since no code uses package-level imports (all consumers import directly from submodules), the re-exports were removed entirely.

## v0.1.26 - 2026-04-02

### Added

- **`OPENFILTER_APPEND_LD_LIBRARY_PATH` and `OPENFILTER_APPEND_PATH` env vars**: Read at filter startup (before torch import) and appended to the existing `LD_LIBRARY_PATH` / `PATH` values. Allows Kubernetes controllers to inject GPU driver paths without overriding container-image-baked paths. On GKE, the NVIDIA device plugin mounts drivers but does not set `LD_LIBRARY_PATH`; the pipelines controller can now inject the paths automatically via these variables.

## v0.1.25 - 2026-03-30

### Fixed

- **Cascade build repaired**: Fixed credential timing, docker secrets mount, and template skip logic in `cloudbuild-cascade.yaml`. Cascade builds now correctly authenticate to GAR and skip repos with their own `cloudbuild.yaml`.
- **Test diagnostics improved**: `test_run` now captures stdout/stderr from subprocess and reports exit codes for easier debugging of CI failures.

## v0.1.24 - 2026-03-27

### Added

- **CUDA/GPU validation at filter runtime startup**: Filters with `device=cuda` or `device=auto` now validate GPU availability before processing begins. Explicit CUDA requests fail immediately with a clear error if CUDA is unavailable or `torch.cuda.is_available()` raises an exception. Auto mode falls back to CPU gracefully. Includes device index validation for multi-GPU setups. (22 test scenarios)

## v0.1.23 - 2026-03-18

### Fixed

- **ImageIn Docker image exits immediately with code 0**: Added missing `if __name__ == '__main__'` entry point block to `image_in.py`. Without this, running `python -m openfilter.filter_runtime.filters.image_in` (the Docker CMD) would import the module but never start the filter.
- **ImageIn never exits after processing all images**: When all images are processed and all topics use a finite loop count (e.g. `loop=2`), the filter now calls `self.exit('all images processed')` instead of spinning indefinitely. Topics with no loop or infinite loop (`loop=True`, `loop=0`) stay alive for polling.
- **ImageIn not exported from filters package**: Added `ImageIn` and `ImageInConfig` to `openfilter/filter_runtime/filters/__init__.py` exports.

### Added

- **ImageIn Docker example**: Added `examples/image_in/docker-compose.yaml` for Docker testing of ImageIn -> Webvis pipelines (uses `docker/image_in.Dockerfile` and `docker/webvis.Dockerfile`).

## v0.1.22 - 2026-03-16

### Added

- **Standardized `FILTER_*` environment variable support** for core I/O filters (VideoIn, VideoOut, ImageIn, ImageOut)
  - All filter-specific parameters now accept the `FILTER_` prefix used by the Plainsight platform (API, controller, portal)
  - Legacy prefixes (`VIDEO_IN_*`, `VIDEO_OUT_*`, `IMAGE_IN_*`, `IMAGE_OUT_*`) remain supported and take precedence for backward compatibility
  - New env var mappings:
    - VideoIn: `FILTER_BGR`, `FILTER_SYNC`, `FILTER_LOOP`, `FILTER_MAXFPS`, `FILTER_MAXSIZE`, `FILTER_RESIZE`
    - VideoOut: `FILTER_BGR`, `FILTER_FPS`, `FILTER_SEGTIME`, `FILTER_PARAMS`
    - ImageIn: `FILTER_POLL_INTERVAL`, `FILTER_LOOP`, `FILTER_RECURSIVE`, `FILTER_MAXFPS`
    - ImageOut: `FILTER_BGR`, `FILTER_QUALITY`, `FILTER_COMPRESSION`
- **101 new unit tests** covering `FILTER_*` env var support, legacy prefix backward compatibility, precedence behavior, case insensitivity, cross-filter propagation, and `FilterConfig` interaction
- **Wall-Clock Latency dashboard row**: 4 new Grafana panels showing real-world pipeline latency including ZMQ transport and queue delays
  - Wall-Clock End-to-End Latency (frame age at sink vs total process time)
  - Per-Filter Frame Age (lat_in) with staircase visualization for linear pipelines
  - Per-Filter Departure Age (lat_out) for identifying per-filter contribution
  - ZMQ + Queue Transit Overhead (transport cost isolated from process time)
- **Cumulative Counters dashboard row**: 3 stat panels (Frames Processed, Megapixels Processed, System Uptime)
- **Latency stat boxes** in Throughput row: End-to-End Latency, Max Frame Age, Avg Frame Age, Total process() Time with color thresholds
- **Monitoring documentation** (`docs/monitoring.md`): comprehensive panel-by-panel guide with timing concept explanations and mermaid diagrams

### Changed

- **Dashboard queries**: replaced hardcoded per-filter-class metric targets with auto-discovery queries (`{__name__=~".+_fps"}`, etc.) — dashboard now works with any filter class without modification
- **Pipeline FPS stat**: now shows source frame rate only (`filter_id=video_in`) instead of sum across all filters
- **GPU Accessible stat**: changed from `min()` to `max()` so any available GPU is detected
- **End-to-End Timing right panel**: renamed to "Total Processing Time (sum of process(), EMA)" to clarify it measures CPU/GPU work only
- **Firing Alerts**: expanded to full-width panel
- Renamed `docs/monitoring-demo.md` to `docs/monitoring.md` with Docusaurus frontmatter

### Fixed

- Documentation in `video-in-filter.md`: corrected `FILTER_FPS` to `FILTER_MAXFPS`
- Documentation in `video-out-filter.md`: standardized env var examples to use `FILTER_*` prefix
- Documentation in `image-in-filter.md`: standardized env var examples and API reference to use `FILTER_*` prefix
- Documentation in `image-out-filter.md`: standardized env var examples to use `FILTER_*` prefix
- `VIDEO_OUT_PARAMS` / `FILTER_PARAMS`: removed `.lower()` that corrupted case-sensitive JSON string values
- Inline docstring references updated to show both `FILTER_*` and legacy env var names
- Fixed `VIDEO_MAXFPS` typo in VideoIn docstring (should be `VIDEO_IN_MAXFPS`)

### Removed

- Input/Output Latency panel (replaced by Wall-Clock Latency row)
- Uptime timeseries panel (replaced by System Uptime stat in Cumulative Counters)
- `docs/observability.md` and `docs/observability-summary.md` (consolidated into monitoring.md)

## v0.1.21 - 2026-02-25

### Added

- **Per-frame, per-filter timing metrics**: 6 new metrics for pipeline performance observability
  - `filter_time_in` / `filter_time_out`: timestamps when each filter starts and finishes processing
  - `process_time_ms`: per-filter processing duration (EMA-smoothed)
  - `frame_total_time_ms` / `frame_avg_time_ms` / `frame_std_time_ms`: aggregate timing across all filters in the pipeline (computed by the last filter)
  - Timing metadata injected into `frame.data['meta']['filter_timings']` for downstream inspection
  - All 6 metrics exported as `openfilter_`-prefixed observable gauges in OpenTelemetry/Prometheus
- **Monitoring infrastructure**: Docker Compose stack with Prometheus, Grafana, Alertmanager, and OTel Collector
- **Monitoring demo**: example pipeline with metric verification script
- **Unit tests**: 27 new tests covering EMA math, timing injection, sink/dict/callable process paths, metric sets, and prefix logic

### Fixed

- Sink filters (returning `None` from `process()`) now correctly record timing metrics. Previously, the timing update code ran after the `None` check, so sink filters never got timing recorded.
- Updated existing test assertions to account for timing metadata injection in frame data

## v0.1.20 - 2026-01-28

### Fixed

- Replace deprecated `distutils.util.strtobool` with local implementation for Python 3.12+ compatibility
  - Fixes `ModuleNotFoundError: No module named 'distutils'` in webvis and other filters

## v0.1.19 - 2026-01-28

### Fixed

- Fix `UnboundLocalError` in filter error handling when filter initialization fails
  - The `filter` variable is now properly initialized before the try block
  - Exception handlers and finally blocks now check if `filter is not None`
- Add missing X11/OpenCV runtime libraries to all Dockerfiles
  - Fixes `ImportError: libxcb.so.1: cannot open shared object file` error
  - Added `libxcb1`, `libxcb-shm0`, `libxcb-render0`, `libx11-6`, `libgl1`, `libglib2.0-0` to all filter images

## v0.1.18 - 2026-01-21

### Fixed

- CVE: update `opencv-python-headless` to 4.13.0 (fixes ffmpeg security vulnerability)

### Changed

- Relax version pins from exact (`==`) to compatible release (`~=`) specifiers
  - Allows downstream filters to receive patch-level updates without dependency conflicts
  - Applies to all core and optional dependencies

## v0.1.17 - 2026-01-15

### Added

- default filters docker images

### Fixed

- dependencies updated to fix CVEs
- tests: prevent flaky failures
- add missing filter dependencies

## v0.1.16 - 2025-12-09

### Added

- feat: add security-scan GH workflow

### Fixed

- dependencies updated to fix CVEs
- CVE: update GitHub actions/download-artifact
- tests: prevent flaky failures
- tests: prevent file descriptor leaks
- tests: Python 3.12 Multiprocessing Pickling Issues

## v0.1.15 - 2025-12-01

### Added

- **Scarf Analytics Opt-Out**: Added support for disabling Scarf usage metrics
  - Set `DO_NOT_TRACK=true` environment variable to opt out
  - CI workflows now disable Scarf analytics by default

- Created the webvis example showing how to run in python, cli and docker.

## v0.1.14 - 2025-09-29

### Updated

- **Documentation**: Updated documentation

## v0.1.13 - 2025-09-24

### Added

- **Complete Filter Documentation**: Comprehensive documentation for all OpenFilter filters
  - `image-out-filter.md` - Image output with filename generation and quality options
  - `webvis-filter.md` - Web Viewer with FastAPI endpoints
  - `mqtt-out-filter.md` - MQTT Bridge output with ephemeral source support
  - `video-out-filter.md` - Video Streamer output with segmentation and encoding
  - `video-in-filter.md` - Video Source input with webcam/RTSP/file support
  - `util-filter.md` - Utility filter with xforms-based transformations
  - `rest-filter.md` - REST Connect API filter for HTTP data ingestion
  - `recorder-filter.md` - Data Capture recording capabilities

- **ImageOut Filter**: New output filter for writing images to files
  - Filename generation with timestamp and frame numbering
  - Multiple image format support (JPEG, PNG, etc.)
  - Quality and compression options
  - Topic-based image selection

- **Comprehensive Test Suite**: Added tests for ImageOut filter
  - Unit tests for ImageWriter class functionality
  - Integration tests for filter pipeline scenarios
  - 619 lines of test coverage

- **Example Demos**: Created demonstration examples
  - Image output demo with various configuration options
  - Video pipeline demo with face enhancement and RTSP support
  - GCS integration examples for cloud storage
  - Makefile automation for demo scenarios

### Fixed

- Corrected documentation inaccuracies to match actual filter implementations
- Updated parameter names and configuration options
- Fixed webcam URL format specification (`webcam://` prefix)
- Updated examples to use proper syntax and formats

### Changed

- Enhanced documentation structure with consistent API references
- Added `# ... other filters above` comments to pipeline examples
- Updated Util filter documentation to reflect xforms-based configuration
- Corrected VideoOut filter documentation for segmentation parameters

## v0.1.12 - 2025-07-25

### Added

- ImageIn filter to support reading images and creating Frame streams

## v0.1.11 - 2025-08-05

### Added

- **Observability System**: Comprehensive telemetry and monitoring capabilities
  - `MetricSpec` class for defining custom metrics with flexible value functions
  - `TelemetryRegistry` for managing OpenTelemetry instruments and recording metrics
  - Support for counters, histograms, and other OpenTelemetry instrument types
  - Configurable metric allowlist via `OF_SAFE_METRICS` environment variable
  - Automatic metric recording from frame data with customizable value extraction

### Fixed

- **Telemetry Tests**: Updated test expectations to match current OpenTelemetry API
  - Fixed histogram parameter name from `boundaries` to `explicit_bucket_boundaries_advisory`
  - All telemetry tests now pass successfully (8/8 tests passing)

### Technical Details

- **Metric Specification**: Flexible metric definition with instrument type, name, and value extraction functions
- **Registry Management**: Centralized telemetry instrument creation and metric recording
- **Configuration**: Environment-based metric allowlist for security and performance control
- **Testing**: Comprehensive test coverage for metric specs, registry operations, and configuration handling

### Modified

- For consistency across all versions, need to emit openfilter_version with v.
- Modified VERSION file for examples.
- Updated pyproject of all examples.
- Updated the `producer` and `schemaURL` for lineage.

## v0.1.10 - 2025-08-05

### Modified

- Lineage `Start` events now emit filter context with the regular info.
- renamed `model_version` to `resource_bundle_version` for clarity as it the version for the full bundle rather than any one model.
- modified FilterContext to emit `openfilter_version` as well.
- added getters for FilterContext: `FilterContext.get_filter_version()`, `FilterContext.get_resource_bundle_version`, `FilterContext.get_openfilter_version()`, `FilterContext.get_version_sha()` and `FilterContext.get_model_info()`.
- modified `git_sha` to `version_sha`

## v0.1.9 - 2025-07-30

### Modified

- `Running` events now include the filter's own meta data as well.

## v0.1.8 - 2025-07-25

### Added

- **FilterContext**: Added a static context class to provide build and model metadata at runtime. This includes:
  - `filter_version` (from VERSION)
  - `model_version` (from VERSION.MODEL)
  - `git_sha` (from GITHUB_SHA, set by CI/CD or manually)
  - `models` (from models.toml, with model name, version, and path)
- The context is accessible via `FilterContext.get(key)`, `FilterContext.as_dict()`, and `FilterContext.log()` for logging/debugging purposes.

## v0.1.7 - 2025-07-17

### Updated

- Support for Python 3.13 (Publishing and CI)
  - Note we do not support for Python 3.13t, i.e. threaded see here: <https://docs.python.org/3/howto/free-threading-python.html>.

### Modified

- Updated latest versions for all examples using `pyproject.toml` and `requirements.txt`

## v0.1.6 - 2025-07-16

### Added

- `OpenTelemetry` support to the `OpenFilter`.
  - For `OpenTelemetry` usage:
    - `TELEMETRY_EXPORTER_TYPE`- OpenTelemetry exporter (eg:console,gcm,OTLP_GRPC,OTLP_HTTP)
    - `OTEL_EXPORTER_OTLP_GRPC_ENDPOINT` - If the client is OTLP_GRPC
    - `OTEL_EXPORTER_OTLP_HTTP_ENDPOINT` - If the client is OTLP_HTTP
    - `TELEMETRY_EXPORTER_ENABLED` - Enable/disable OpenTelemetry
    - `EXPORT_INTERVAL` - OpenTelemetry metrics Export interval
    - `PROJECT_ID` - GCP project

## v0.1.5 - 2025-07-14

### Added

- `OpenLineage` support to the `OpenFilter`.
  - For `OpenLineage` usage:
    - `OPENLINEAGE_URL`- OpenLineage client URL
    - `OPENLINEAGE_API_KEY` - OpenLineage client API key if needed
    - `OPENLINEAGE_VERIFY_CLIENT_URL` - False by default
    - `OPENLINEAGE_ENDPOINT` - OpenLineage client endpoint
    - `OPENLINEAGE_PRODUCER` - OpenLineage producer
    - `OPENLINEAGE__HEART__BEAT__INTERVAL` - OpenLineage RUNNING event period

### Updated

- `OpenLineage` support to the `OpenFilter`.
  - `run_id` updated the code so that events have the same run_id

## v0.1.4 - 2025-07-07

### Added

- `OpenLineage` support to the `OpenFilter`.
  - For `OpenLineage` usage:
    - `OPENLINEAGE_URL`- OpenLineage client URL
    - `OPENLINEAGE_API_KEY` - OpenLineage client API key if needed
    - `OPENLINEAGE_VERIFY_CLIENT_URL` - False by default
    - `OPENLINEAGE_ENDPOINT` - OpenLineage client endpoint
    - `OPENLINEAGE_PRODUCER` - OpenLineage producer
    - `OPENLINEAGE__HEART__BEAT__INTERVAL` - OpenLineage RUNNING event period

## v0.1.3 - 2025-06-19

### Added

- `s3://` support to the `VideoIn` base filter (Thanks to @Ninad-Bhangui)
  - For `s3://` sources, AWS credentials are required. Set these environment variables:
    - `AWS_ACCESS_KEY_ID` - Your AWS access key ID
    - `AWS_SECRET_ACCESS_KEY` - Your AWS secret access key
    - `AWS_DEFAULT_REGION` - Default AWS region (optional, can be overridden per source)
    - `AWS_PROFILE` - AWS credentials profile to use (alternative to access keys)
- `examples/hello-ocr` example demonstrating an OCR filter use case on a simple hello world video (Thanks to @kitmerker)
- `examples/openfilter-heroku-demo` example demonstrating filter deployment on Heroku Fir (Thanks to @navarmn, @afawcett and the Heroku team)

### Updated

- `requests` dependency from 2.32.3 to 2.32.4
  - Addresses `CVE-2024-47081`, fixing an issue where a maliciously crafted URL and
trusted

## v0.1.2 - 2025-05-22

### Updated

- Demo dependencies

### Fixed

- Log messages

## v0.1.1 - 2025-05-22

### Added

- Initial release of `openfilter` base library

- **Filter Base Class**
  - Lifecycle hooks (`setup`, `process`, `shutdown`)
  - ZeroMQ input/output routing
  - Config parsing and normalization

- **Multi-filter Runner**
  - `run_multi()` to coordinate multiple filters
  - Supports coordinated exit via `PROP_EXIT`, `OBEY_EXIT`, `STOP_EXIT`

- **Telemetry and Metrics** (coming soon)
  - Structured logs and telemetry output
  - Auto-tagging with filter ID, runtime version, and more

- **Utility Functions**
  - Parse URI options and topic mappings (`tcp://...;a>main`, etc.)

- **Highly Configurable**
  - Supports runtime tuning via environment variables
  - Extensible `FilterConfig` for custom filters
