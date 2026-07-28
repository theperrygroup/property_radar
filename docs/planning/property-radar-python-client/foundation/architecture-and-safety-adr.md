# Architecture And Safety ADR

Status: `ACCEPTED`

Effective date: `2026-07-28`

## Context

The repository starts without runtime or release infrastructure. The requested
library should be PyPI-ready, should use WFRMLS as a structural and automation
reference, and should cover the official PropertyRadar API without copying
WFRMLS defects or credentials.

The official API exposes read operations, POST-based searches, personal-data
lookups, pay-per-record requests, and persistent mutations to lists, imports,
automations, and webhooks. Those operations need different safety treatment.

## Decisions

### Package And Public API

- Distribution name: `property-radar`.
- Import package: `property_radar`.
- Initial version: `0.1.0`, with runtime `__version__` derived from installed
  package metadata rather than duplicated source constants.
- Python support: maintained CPython 3.10 through 3.14 at the 2026-07-28
  baseline.
- Initial API is synchronous. Async support is deferred until it can share
  request construction rather than duplicate all endpoint behavior.
- Use a `src/` layout and ship `py.typed`.
- Expose one `PropertyRadarClient` facade with lazy resource properties.
- Resource clients share one context-managed, injectable HTTP transport.
- Return a typed response-envelope contract while preserving raw vendor fields
  in dictionaries so schema evolution does not discard data.

### Transport

- Use explicit timeout values and connection pooling.
- Read the API key from an explicit constructor argument first, then
  `PROPERTY_RADAR_API_KEY`; accept `PROPERTYRADAR_API_KEY` as a compatibility
  fallback and never load `.env` files at import time.
- Never include bearer tokens, webhook secrets, personal records, or raw
  response bodies in exception text or logs.
- Accept all successful 2xx responses and map documented HTTP failures,
  timeouts, network failures, and malformed JSON to typed exceptions.
- Retry only explicitly safe/idempotent calls and retryable statuses. Never
  automatically retry persistent mutations or paid purchases.
- Honor `Retry-After` when present.
- Encode vendor query names exactly while exposing Pythonic snake_case method
  parameters.

### Spend And Mutation Safety

- Every documented `Purchase` parameter defaults to preview mode
  (`Purchase=0`).
- `Purchase=1` requires both an explicit method argument and a client-level
  `allow_charges=True` opt-in.
- Persistent list, import, automation, and webhook changes require an explicit
  `allow_mutations=True` client opt-in.
- Automation payloads that purchase phone or email data also require
  `allow_charges=True`.
- Read-like POST endpoints such as property searches and suggestions are not
  classified as persistent mutations.
- Unit tests assert that blocked operations make no HTTP request.

### Data, Privacy, And Tests

- Tests and examples use synthetic IDs, addresses, people, and response data.
- No PropertyRadar credential is required by CI.
- Live integration tests are excluded from the default package and CI until an
  explicit, non-billable, licensed test contract exists.
- The library does not cache or persist vendor response data.
- The library documents that callers own retention, suppression, consent,
  access, and licensing compliance for data they obtain.

### Documentation And Contract Drift

- Document each resource family and every public method.
- Maintain a checked-in endpoint manifest derived from the official contract,
  not a bundled copy of the full vendor specification.
- A read-only drift check compares the manifest with the official OpenAPI
  document and reports additions/removals; it does not call live endpoints.
- Criteria values remain a generic typed structure because the vendor exposes
  more than 250 evolving criteria. The docs link to the official criteria
  catalog rather than freezing a stale generated enumeration.

### CI, Docs, And Release

- CI is secretless and uses hard Ruff, mypy, pytest/coverage, strict docs,
  package build, Twine, artifact-content, and installed-wheel smoke gates.
- GitHub workflow permissions default to read-only and expand only on the job
  that needs Pages, PyPI OIDC, or release write access.
- Release tags must match `vX.Y.Z` and the built package version.
- Build the wheel and sdist once, pass the exact artifacts to PyPI and GitHub
  release jobs, and use PyPI Trusted Publishing without a long-lived token.
- PyPI publication remains blocked until the project/environment/trusted
  publisher are authoritatively configured.

## Rejected Alternatives

- Flat package layout: tests could accidentally import the checkout rather than
  the installed artifact.
- One HTTP session per resource: duplicates lifecycle and pooling state.
- Import-time dotenv loading: mutates application configuration unexpectedly.
- Raw `dict[str, Any]` everywhere: insufficient guidance for stable envelope
  fields.
- Full generated vendor models: the inline schema is broad and fast-moving,
  while callers still need forward-compatible raw fields.
- Automatic paid calls or retries: could create non-refundable charges.
- Secret-backed unit CI: blocks Dependabot and risks credential exposure.
- Token-based PyPI upload: unnecessary long-lived secret when OIDC is
  available.

## Consequences

- Callers must opt into mutations and charges, which adds deliberate friction.
- The first release is sync-only but has one clear transport seam for future
  async support.
- Complete wrapper coverage can be proven without a live PropertyRadar account;
  live behavior remains a separate evidence level.
- PyPI and GitHub publication require external configuration and authoritative
  post-action verification.
