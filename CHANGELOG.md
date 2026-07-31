# Changelog

All notable changes to this project will be documented here.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-07-31

### Added

- Deeply immutable `BUYER_TRANSFER_MATCH_CONTRACT` provenance and strict
  `parse_buyer_transfer_match` parsing for an exact-target property search
  using PropertyRadar's documented Buyer Name (Grantee) criterion.
- `BuyerTransferMatchCriteria`, typed property identity/location and broad
  property type, redacted linkage, exact scope fingerprint, and billing
  evidence models.
- `PropertiesResource.buyer_transfer_match()` as a dual-opt-in, single-request
  convenience that requests one exact RadarID, rejects non-boolean purchase
  flags before network I/O, and never retries a paid call.

### Security

- Buyer names, property identifiers, addresses, parcels, and fingerprints are
  omitted from public representations and bounded error messages.
- Client charge/mutation opt-ins and both typed property purchase flags reject
  non-boolean values before any request, so truthy configuration strings and
  malformed input cannot bypass the safety boundary.
- Transport request classifications and automation boolean controls now apply
  the same exact-boolean rule before network I/O.

### Clarified

- A buyer-criterion property match does not expose the matching document,
  structured grantees, or exact/fuzzy provider name-match semantics. It can
  support geographic attribution and caller review, but cannot by itself
  confirm a recorded grantee or verified purchase.
- The optional most-recent filter means the most recent change of ownership,
  which PropertyRadar documents may be either Market or Non-Market.

## [0.2.0] - 2026-07-31

### Added

- Deeply immutable `TRANSACTION_HISTORY_CONTRACT` metadata and a strict
  `parse_transaction_history` public parser for preview or purchased
  `properties.transactions` response envelopes.
- Immutable party and billing types with preview, charged, and unknown request
  states; exact decimal cost, optional free quantity, result count, and
  explicit unavailable currency/alias/request-ID evidence.
- A bounded property-person composition that preserves provider order,
  `PersonKey`, `PersonType`, name components, suffix, `EntityName`, and
  ownership role while keeping current-owner evidence separate from
  undocumented transaction-party linkage.
- `PropertiesResource.transaction_history()` as an additive typed convenience;
  the existing raw `transactions()` return type is unchanged.

### Changed

- Grantor and Grantee scalar values are preserved as whole provider display
  groups with unknown party boundaries rather than being mislabeled as one
  party. No name splitting or component synthesis is performed.
- Transaction, party, and billing representations now omit names, identifiers,
  and licensed record values.
- Refreshed the endpoint-manifest source metadata to official API `5.2.0.0`;
  all 37 operation identities remain unchanged, and drift checks now bind the
  stored API version and source SHA-256 as well as method/path pairs.

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

[Unreleased]: https://github.com/theperrygroup/property_radar/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/theperrygroup/property_radar/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/theperrygroup/property_radar/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/theperrygroup/property_radar/releases/tag/v0.1.0
