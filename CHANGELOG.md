# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-04-11

### Added
- Docker Compose configuration for containerized deployment
- CI pipeline for automated testing and linting
- `min_length` validation on `NLQueryRequest` to reject empty or trivially short inputs

### Changed
- Test suite expanded to 418 tests covering audit trail, SARIF output, OTEL spans, and API surface
- README overhauled to be pitchable for enterprise and OSS audiences

### Fixed
- Various edge cases surfaced during test suite expansion

## [0.2.0] - 2026-03-15

### Added
- Monte Carlo simulation layer for migration planning and cost projection
- FOCUS 1.3 billing normalization for cloud cost data
- CloudQuery backend integration for infrastructure data ingestion

### Changed
- SARIF 2.1.0 audit trail output improved for richer rule metadata
- OTEL span instrumentation extended across additional code paths

## [0.1.0] - 2026-02-01

### Added
- `AIAuditTrail` core class with SARIF 2.1.0 and OpenTelemetry output
- Streamlit UI for audit trail visualization and querying
- Python SDK usage examples
- Benchmark suite for `AIAuditTrail` performance characterization
- Initial test suite (35+ tests)

[0.3.0]: https://github.com/HunterSpence/enterprise-ai-accelerator/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/HunterSpence/enterprise-ai-accelerator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/HunterSpence/enterprise-ai-accelerator/releases/tag/v0.1.0
