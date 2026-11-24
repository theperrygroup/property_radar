# Changelog

All notable changes to this project will be documented here.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.2] - 2026-11-23

Live PropertyRadar responses showed four mismatches in `0.4.1`. This release
fixes them. Paid buyer-transfer calls keep the `0.4.1` criteria and
classification, a buyer-transfer record rejected after billing keeps its
billing evidence, and transaction history reports withheld and partial
evidence. The tests use synthetic values only and make no provider request.

### Fixed

- `totalCost` type. Live previews send `totalCost` as a JSON integer (`0`),
  and paid calls can send an integer, a float, or a decimal string.
  `parse_buyer_transfer_match`, `parse_historical_buyer_transfer_match`,
  `parse_historical_transaction_quote`, `parse_historical_transaction_result`,
  `HistoricalTransactionResponseError.billing_evidence`, and
  `parse_transaction_history` (main and `property_persons` envelopes) now
  accept a nonnegative JSON integer of at most 64 digits, a finite nonnegative
  JSON number whose plain decimal form has at most 64 characters, or an ASCII
  decimal string of at most 64 characters, and give a `Decimal`. An integer
  and a decimal string convert exactly. A JSON number with a fraction or an
  exponent reaches the parser as a float and converts as
  `Decimal(repr(value))`: the `Decimal` equals the number as written when it
  has at most 15 significant digits, and a longer number can already be
  rounded by JSON decoding before the library sees it. Booleans, `null`, NaN,
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
  A preview, recent or historical, also adds the official residential
  criterion
  `{"name": "PropertyType", "value": [{"name": "PType", "value": ["SFR", "CND",
  "MFR", "APT", "RES"]}]}` just before the RadarID criterion, which stays last.
  A paid call sends exactly the `0.4.1` criteria, without that criterion, so
  the provider still returns a non-residential or `Unknown` transfer to it.
- `parse_transaction_history`, and so `properties.transaction_history()`,
  accepts the live preview envelope: the optional `totalResultCount` key,
  which must not be less than `resultCount`, and, when `purchase_requested`
  is `False`, an empty `results` list with a positive `resultCount` or
  `totalResultCount`. Such a preview has no records and
  `records_withheld=True`. The `property_persons` envelope may carry
  `totalResultCount` too, under the same rule; `0.4.1` rejected it as an
  undocumented field.
- `BuyerTransferResponseError` and `HistoricalTransactionResponseError` now
  survive `pickle`, `copy.copy` and `copy.deepcopy` with their
  `billing_evidence`, `status_code`, `request_id`, `retry_after` and
  `__notes__`; the default exception reduce dropped the required keyword-only
  `billing_evidence` and raised `TypeError`.

### Added

- `BUYER_TRANSFER_PREVIEW_FIELDS` (`("RadarID",)`),
  `BUYER_TRANSFER_RESIDENTIAL_PTYPE_CODES`
  (`("SFR", "CND", "MFR", "APT", "RES")`), `BuyerTransferResidentialBasis`
  (`"property_type"` or `"property_type_criterion"`), and
  `BuyerTransferResponseError`, exported from `property_radar`.
- `build_buyer_transfer_match_criteria(criteria, *, preview=False)`. The new
  keyword-only `preview` must be exactly a boolean, else the builder raises
  `TypeError`. The default returns exactly the `0.4.1` criteria list.
  `preview=True` returns the preview list, with the `PropertyType` criterion
  just before `RadarID`. The resource methods pass `preview=not purchase`.
- `BuyerTransferResponseError`, a subclass of `InvalidResponseError` whose
  `billing_evidence` is a `BuyerTransferBillingEvidence`. Both buyer-transfer
  parsers, and so both buyer-transfer resource methods, now validate the
  envelope, the counts, the preview metadata and `totalCost` before the
  record. A record rejected after that point raises this error with the cost
  and counts, for example for `radar_id_mismatch`, `fips_mismatch`,
  `missing_radar_id`, `undocumented_property_fields`, a field-validation
  reason or `property_type_outside_criterion`; `0.4.1` raised a plain
  `InvalidResponseError` without them. The message keeps the reason-code
  format, and the error has no chained context. A rejection before that
  point stays a plain `InvalidResponseError` with the same reason.
- `BuyerTransferProperty.residential_basis` and
  `HistoricalBuyerTransferProperty.residential_basis` (keyword-only, default
  `None`).
- `BuyerTransferBillingEvidence.provider_metadata_omitted` (keyword-only,
  default `False`; `True` only for an empty, zero-cost preview).
- `TransactionBillingEvidence.total_result_count: int | None = None`, and
  `TransactionHistory.records_withheld: bool = False` and
  `TransactionHistory.current_owners_withheld: bool = False` (new last
  fields).
- `TransactionHistory.truncated`, a computed property and not a stored field.
  It is `True` when the rows were not withheld and `total_result_count` is
  greater than the number of records, for example when the provider's
  documented default limit of 500 rows applied. Treat such a history as
  partial evidence.
- `property_persons_purchase_requested: bool | None = None`, keyword-only and
  last, on `parse_transaction_history()` and
  `properties.transaction_history()`. Pass the `purchase` choice of the
  `persons()` call that returned `property_persons`, and set it only together
  with `property_persons`.
- Invalid-response reasons `preview_record_withheld` and
  `property_type_outside_criterion` for buyer-transfer matches, and
  `total_result_count`, `total_result_count_mismatch`,
  `property_persons_total_result_count`,
  `property_persons_total_result_count_mismatch`,
  `property_persons_preview_count_missing` and
  `property_persons_purchase_requested` for transaction history.

### Changed

- Residential classification depends on the request mode.
  - A preview (`purchase_requested=False`) is made under the residential
    criterion. A record without `PType`, as every live preview returns, has
    `is_residential=True` and `residential_basis="property_type_criterion"`.
    A returned `PType` that is one of the five residential display names
    (Single Family, Condominium, Multi-Family 2-4, Multi-Family 5+, Other
    Res.) gives `residential_basis="property_type"` and `True`. Any other
    documented type, `Unknown` included, fails closed with
    `property_type_outside_criterion` as a `BuyerTransferResponseError`.
  - A paid or detached parse (`purchase_requested=True` or `None`) classifies
    a returned `PType` exactly as `0.4.1` did and never fails because of the
    type: `True` for the five residential names, `False` for the other
    documented types and `None` for `Unknown`, with
    `residential_basis="property_type"`. A record without `PType` has
    `residential_basis=None` and `is_residential=None`.
  - An undocumented type still fails with `property_type`. Directly
    constructed properties keep `residential_basis=None` and the `0.4.1`
    classification.
- `buyer_transfer_scope_fingerprint()` keeps its signature. It now hashes the
  paid criteria, the preview `PropertyType` criterion under a key of its own,
  and both field sets, so scope fingerprint values change from `0.4.1`. The
  preview and the paid parse of the same criteria still share one value.
- `TransactionHistory.total_result_count` returns the provider
  `totalResultCount` when present, else `result_count` (unchanged for every
  envelope that `0.4.1` accepted).
- Withheld persons preview. With `property_persons_purchase_requested=False`
  and no returned people, a positive persons `resultCount` or
  `totalResultCount` means that the preview withheld the owners:
  `current_owners=None` and `current_owners_withheld=True`. Counts that are
  all `0` give `current_owners=()`, and no count at all fails closed with
  `property_persons_preview_count_missing`. In every other case, `True` and
  the default `None` included, a persons `resultCount` that is present must
  equal the number of people, as in `0.4.1`, and so must a persons
  `totalResultCount`.
- `properties.transaction_history()` checks the
  `property_persons_purchase_requested` flag and the caller's
  `property_persons` data before any request. A flag that is neither `None`
  nor a boolean raises `TypeError`, and a flag without `property_persons`
  raises `ValueError`. Invalid persons data raises `InvalidResponseError` and
  sends no transactions request, billable or not; `0.4.1` sent the request
  first. So for a paid call on a client without `allow_charges=True`, invalid
  persons data now raises `InvalidResponseError` instead of
  `ChargeNotAllowedError`.
- `ResponseEnvelope.totalCost` is typed `str | int | float` instead of `str`,
  as the provider sends it and the parsers accept it.
- Reprs add only flags and counts: `residential_basis` on buyer-transfer
  properties, `provider_metadata_omitted` on buyer-transfer billing evidence,
  `records_withheld`, `truncated` and `current_owners_withheld` on
  `TransactionHistory`, and `total_result_count` on
  `TransactionBillingEvidence`.
- All four typed contracts record the new rules, so their contract
  fingerprints change from `0.4.1` to `0.4.2`:
  - `BUYER_TRANSFER_MATCH_CONTRACT`:
    `299cfaba5ddfc8337a290352433969f1f1363fa1a545080773761c2c99d2c8be` to
    `580b955265f3f7928ea1bddba03e7244ceaff8f27fd6844343e05d6ae81bc01c`.
  - `BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT` (version `1`):
    `5fae2c3bd113264a7fbed5bdd7c80278787acd279f567e0f629c09f0ef58ee52` to
    `61ab6cc9e609ad3082124e1bc520c9578760a75ddff0ba989c714c72dcbfc906`.
  - `HISTORICAL_TRANSACTION_CONTRACT` (version `1.1`):
    `15a7a18afd30f8085644c5c374c8dffae24096088620fc8f482d179b3fe258aa` to
    `33a65caa400236c89f19a8cabd6e36132ee86dc2224b44cbb6af2b0fec71f183`.
    `HistoricalTransactionQuery.scope_fingerprint` values change with it.
  - `TRANSACTION_HISTORY_CONTRACT`:
    `d750039019a93bbfc0449b6eecdb47ea8f064e18a7dcfcbd01c3ec30c4e057a8` to
    `a9bed508d5f9210dc37f5ce3e1d61061cb87fe0a3dd19e4c991266d6fb1fb635`.

  Callers that pin a contract fingerprint must update it.
- Development: `uv.lock` now locks `cryptography` 50.0.2, `certifi`
  2026.11.20 and `urllib3` 2.8.0. The package's declared dependencies are
  unchanged.

### Clarified

- The `PropertyType` criterion on `Purchase=0` follows the official API
  reference (criterion shape and PType codes) and has not been probed live.
  So a preview's `matched=False` can also mean a non-residential or `Unknown`
  transfer that the provider dropped under the criterion. The withheld
  persons preview mirrors the transactions preview and has not been probed
  live either. The RadarID-only free field, the bare zero-hit envelope, the
  preview counts, and the integer `totalCost` come from live responses.
- A preview remains non-billable evidence and never authorizes a purchase. A
  paid call still requires `purchase=True` and the client opt-in
  `allow_charges=True`, and is never retried. Buyer matches remain
  property-level evidence without automatic purchase verification. After a
  `BuyerTransferResponseError` on a paid call, persist its billing evidence
  and treat the outcome as unknown; the error is not permission to retry.
- Compatibility. No existing public name, parameter, dataclass field or
  invalid-response reason is removed or renamed, and existing defaults are
  unchanged. New parameters are keyword-only with defaults, and new dataclass
  fields come last with defaults. The new fields take part in equality,
  hashing and `repr`, so a parsed object can differ from a hand-built one
  that leaves them at their defaults, and a `dataclasses.replace()` that sets
  a `property_type` its `residential_basis` does not allow raises
  `ValueError`. Objects built or pickled under `0.4.1` are not supported.

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
