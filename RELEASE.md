# Changelog
OpenFilter Library release notes

## [Unreleased]

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
