# Changelog
OpenFilter Library release notes

## [Unreleased]

## v0.1.4 - 2025-07-07
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
