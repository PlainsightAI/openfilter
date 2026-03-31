# Changelog

OpenFilter Library release notes

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
    - `OTLP_GRPC_ENDPOINT_SECURITY` - Sets OpenTelemtry GRPC client endpoint security
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
