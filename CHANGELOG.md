# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-09-06

### Added

- Framework-neutral `validate`, `text2fhir`, `voice2fhir`, and `deidentify` APIs.
- Eight-layer validation reports with honest local and adapter-backed modes.
- Deterministic de-identification, reviewed extraction prompts, and strict entity parsing.
- Optional policy-enforcing LiteLLM text and speech adapters.
- PHI-safe public errors, invocation policies, provenance, and evidence models.

## [0.1.0] - 2026-09-06

### Added

- Deterministic FHIR assembly and PHI-free evidence.
- Exact-match terminology binding through an async adapter protocol.
- Subject-context preflight and reference rebinding.
- Generic target descriptors and idempotent write-plan compilation.

[Unreleased]: https://github.com/Safwanmahmoud/fhirbridge/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Safwanmahmoud/fhirbridge/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Safwanmahmoud/fhirbridge/releases/tag/v0.1.0
