# Changelog

All notable changes to this project will be documented here.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.2] - 2026-11-23

Live PropertyRadar responses showed four mismatches in `0.4.1`. This release
fixes them. The tests use synthetic values only and make no provider request.

### Fixed

- `totalCost` type. Live previews send `totalCost` as a JSON integer (`0`),
  and paid calls can send an integer, a float, or a decimal string.
  `parse_buyer_transfer_match`, `parse_historical_buyer_transfer_match`,
  `parse_historical_transaction_quote`, `parse_historical_transaction_result`,
  `HistoricalTransactionResponseError.billing_evidence`, and
  `parse_transaction_history` (main and `property_persons` envelopes) now
  accept a nonnegative JSON integer of at most 64 digits, a finite nonnegative
  JSON number (converted exactly as `Decimal(repr(value))`, with a plain
  decimal form of at most 64 characters), or an ASCII decimal string of at most
  64 characters, and give an exact `Decimal`. Booleans, `null`, NaN,
  infinities, negative values, `-0.0`, over-long values, and all other types
  still fail with `total_cost`.
- Bare zero-hit preview. A zero-hit `POST /v1/properties?Purchase=0` returns
  only `{"results": []}`. With `purchase_requested=False` only, both
  buyer-transfer parsers accept it as no match: status `preview`, cost
  `Decimal("0")`, currency `None`, `quantity_free_remaining=None`, zero counts,
  and `billing.provider_metadata_omitted=True`. With `purchase_requested=True`
  or `None` it still fails with `required_envelope_fields`, and every other
  partial envelope still fails closed.
- Preview counts. In a `Purchase=0` preview, `resultCount` counts purchased
  rows and `totalResultCount` counts matches. For `purchase_requested=False`,
  the buyer-transfer parsers accept at most one record, a `totalResultCount` of
  `0` or `1` that equals the number of records, and a `resultCount` of `0` or
  the number of records. A match without its record fails closed with the new
  reason `preview_record_withheld`. Paid and detached responses keep the
  `0.4.1` rule `resultCount == len(results) == totalResultCount`. For previews,
  linkage presence now follows the returned record instead of `result_count`.
- Free preview fields. A `Purchase=0` request that asks for any paid field
  returns no record. `buyer_transfer_match(purchase=False)` and
  `historical_buyer_transfer_match(purchase=False)` now request
  `Fields=RadarID` only; paid calls keep `BUYER_TRANSFER_PROPERTY_FIELDS`.
  Every buyer-transfer request, preview or paid, recent or historical, adds the
  official residential criterion
  `{"name": "PropertyType", "value": [{"name": "PType", "value": ["SFR", "CND",
  "MFR", "APT", "RES"]}]}` just before the RadarID criterion, which stays last.
- `parse_transaction_history`, and so `properties.transaction_history()`,
  accepts the live preview envelope: the optional `totalResultCount` key, and
  an empty `results` list with a positive `resultCount` when
  `purchase_requested` is `False`. The `property_persons` envelope keeps its
  `0.4.1` keys.

### Added

- `BUYER_TRANSFER_PREVIEW_FIELDS` (`("RadarID",)`),
  `BUYER_TRANSFER_RESIDENTIAL_PTYPE_CODES`
  (`("SFR", "CND", "MFR", "APT", "RES")`), and `BuyerTransferResidentialBasis`
  (`"property_type"` or `"property_type_criterion"`), exported from
  `property_radar`.
- `BuyerTransferProperty.residential_basis` and
  `HistoricalBuyerTransferProperty.residential_basis` (keyword-only, default
  `None`).
- `BuyerTransferBillingEvidence.provider_metadata_omitted` (keyword-only,
  default `False`; `True` only for an empty, zero-cost preview).
- `TransactionBillingEvidence.total_result_count: int | None = None` and
  `TransactionHistory.records_withheld: bool = False` (new last fields).
- Invalid-response reasons `preview_record_withheld` and
  `property_type_outside_criterion` for buyer-transfer matches, and
  `total_result_count` and `total_result_count_mismatch` for transaction
  history.

### Changed

- A buyer-transfer record matched under the residential criterion without a
  returned `PType` (every preview) has `is_residential=True` and
  `residential_basis="property_type_criterion"`. A returned `PType` gives
  `residential_basis="property_type"` and must be one of the five residential
  display names (Single Family, Condominium, Multi-Family 2-4, Multi-Family 5+,
  Other Res.). Any other documented type, including `Unknown`, now fails closed
  with `property_type_outside_criterion` instead of parsing as non-residential
  or unknown; an undocumented type still fails with `property_type`. Directly
  constructed properties keep `residential_basis=None` and the `0.4.1`
  classification.
- `build_buyer_transfer_match_criteria()` returns the `PropertyType` criterion
  just before `RadarID`. `buyer_transfer_scope_fingerprint()` keeps its
  signature and now also hashes `BUYER_TRANSFER_PREVIEW_FIELDS`, so scope
  fingerprint values change. The preview and the paid parse of the same
  criteria still share one value.
- `TransactionHistory.total_result_count` returns the provider
  `totalResultCount` when present, else `result_count` (unchanged for every
  envelope that `0.4.1` accepted). A preview with withheld rows has no records
  and `records_withheld=True`.
- Reprs add only flags and counts: `residential_basis` on buyer-transfer
  properties, `provider_metadata_omitted` on buyer-transfer billing evidence,
  `records_withheld` on `TransactionHistory`, and `total_result_count` on
  `TransactionBillingEvidence`.
- All four typed contracts record the new rules, so their contract
  fingerprints change:
  - `BUYER_TRANSFER_MATCH_CONTRACT`:
    `299cfaba5ddfc8337a290352433969f1f1363fa1a545080773761c2c99d2c8be` to
    `0406f8ca5636c36eb834b273a4bc401293d52a91d34854874ad790a6edb12eeb`.
  - `BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT` (version `1`):
    `5fae2c3bd113264a7fbed5bdd7c80278787acd279f567e0f629c09f0ef58ee52` to
    `ba879d4c9cf0e6c6ce662cd7bb04c7bf6d794435c5e0e98285ac14732bd47bb2`.
  - `HISTORICAL_TRANSACTION_CONTRACT` (version `1.1`):
    `15a7a18afd30f8085644c5c374c8dffae24096088620fc8f482d179b3fe258aa` to
    `33a65caa400236c89f19a8cabd6e36132ee86dc2224b44cbb6af2b0fec71f183`.
    `HistoricalTransactionQuery.scope_fingerprint` values change with it.
  - `TRANSACTION_HISTORY_CONTRACT`:
    `d750039019a93bbfc0449b6eecdb47ea8f064e18a7dcfcbd01c3ec30c4e057a8` to
    `db0dd03413f298367f79749e522bd3e454e295cafcc68e7dd6d077085254e707`.

  Callers that pin a contract fingerprint must update it.

### Clarified

- The `PropertyType` criterion on `Purchase=0` follows the official API
  reference (criterion shape and PType codes) and has not been probed live.
  The RadarID-only free field, the bare zero-hit envelope, the preview counts,
  and the integer `totalCost` come from live responses.
- A preview remains non-billable evidence and never authorizes a purchase. A
  paid call still requires `purchase=True` and the client opt-in
  `allow_charges=True`, and is never retried. Buyer matches remain
  property-level evidence without automatic purchase verification. Method
  signatures and existing attributes are unchanged.

## [0.4.1] - 2026-11-03

### Fixed

- Update the pinned PyPI publisher to v1.14.3, which supports package metadata
  2.5 and includes upstream security fixes. Metadata verification and trusted
  publishing remain enabled, and the historical APIs are unchanged.

## [0.4.0] - 2026-11-03

The tag and artifacts were created, but the older publisher rejected metadata
2.5 before upload. This version was not published to PyPI; use 0.4.1.

### Added

- `BuyerTransferRecordingDateRange(start, end)` for exact, inclusive historical
  recording dates in `BuyerTransferMatchCriteria` with
  `publication_window=None`. Ordered, finite date ranges may span multiple
  years and cannot include a relative `recording_window`; narrower bounds
  belong to caller authorization policy.
- `BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT` version 1 and historical scope
  fingerprints, binding separate official API `5.3.1.0` provenance and sealing
  the mode, contract, and exact date range. Parsed historical results report
  the historical contract fingerprint.
- `PropertiesResource.historical_buyer_transfer_match()` and
  `parse_historical_buyer_transfer_match()` with dedicated
  `HistoricalBuyerTransferMatchResult`, `HistoricalBuyerTransferLinkage`, and
  `HistoricalBuyerTransferProperty` types. Historical `zip_five` preserves an
  exact five-digit string, including leading zeros. Known optional envelope
  metadata is validated and discarded, with no raw response retained. Calls
  accept at most one result and do not paginate.
- A versioned historical transaction quote/result contract and
  `historical_transaction_history()` convenience. Explicit recording dates,
  document filters, and a caller-selected row limit bound the request before
  billing. Quotes distinguish selected and total counts without requiring
  response rows; paid results retain all selected rows and report truncation.
  Ambiguous recording-date arrays stay unverified and are never converted.
- Historical transaction parsing failures retain independently validated
  billing fields in a typed exception without retaining rows or raw payloads.

### Clarified

- Historical Buyer matches remain property-level evidence without a matching
  document, structured grantees, or automatic purchase verification. Recording
  dates are distinct from closing dates, and existing no-charge controls are
  unchanged.
- The historical interface is additive. The existing API `5.2.0.0` recent-query
  method, parser, contract fingerprint, and types remain unchanged.

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

[Unreleased]: https://github.com/theperrygroup/property_radar/compare/v0.4.2...HEAD
[0.4.2]: https://github.com/theperrygroup/property_radar/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/theperrygroup/property_radar/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/theperrygroup/property_radar/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/theperrygroup/property_radar/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/theperrygroup/property_radar/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/theperrygroup/property_radar/releases/tag/v0.1.0
