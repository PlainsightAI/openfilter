# Changelog
OpenFilter Library release notes

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
  - Note we do not support for Python 3.13t, i.e. threaded see here: https://docs.python.org/3/howto/free-threading-python.html.

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
