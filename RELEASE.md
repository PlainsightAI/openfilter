# Changelog
OpenFilter Library release notes

## [Unreleased]

## v0.1.8 - 2025-07-2

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
