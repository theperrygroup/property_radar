# Changelog

All notable changes to this project will be documented here.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-28

### Added

- Typed synchronous client covering all 37 operations in PropertyRadar API
  contract `5.1.1.0`.
- Shared HTTPX transport with explicit timeouts, sanitized errors, safe retry
  policy, token refresh callbacks, and context-managed lifecycle.
- Deny-by-default controls for persistent mutations and charge-capable
  requests, including automation purchase settings.
- Property-search pagination, criteria typing, vendor-compatible query
  serialization, and typed response envelopes.
- Secretless unit and contract tests, OpenAPI drift checking, user/API
  documentation, and synthetic examples.
- Python 3.10 through 3.14 CI, CodeQL, GitHub Pages, Dependabot, and
  trusted-publishing release workflows.

[Unreleased]: https://github.com/theperrygroup/property_radar/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/theperrygroup/property_radar/releases/tag/v0.1.0
