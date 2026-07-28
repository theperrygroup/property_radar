# Property Radar Python Client Readiness

## Purpose

This tracker records current readiness under a strict "planning is not
implementation, publication, or live API outcome" interpretation.

## Current Snapshot

Snapshot date: `2026-07-28`

| Slice | Status | Current answer |
| --- | --- | --- |
| Planning foundation | `Complete` | Full scaffold, source matrix, architecture ADR, package-layout plan, API implementation plan, and trackers exist locally |
| Package bootstrap | `Verified locally` | Installable `src/` package, governance, uv lock, tests, strict docs, wheel, and sdist pass P0 gates |
| Transport and safety | `Verified locally` | Final suite proves auth precedence, HTTPS boundaries, lifecycle, encoding, sanitized errors, capped safe retries, and pre-network safety denial |
| Documented API coverage | `37/37 verified locally` | Every operation has a public wrapper, manifest mapping, and synthetic contract/request tests |
| User/API documentation | `Verified locally` | Strict MkDocs covers auth, usage, pagination, errors, safety, resources, and release |
| CI and docs automation | `CI/deployment verified` | CI `30339288539`, CodeQL `30339288568`, zero-open-alert readback, and Pages deployment `5635871048` pass |
| Release automation | `Prepared` | Build-once OIDC workflow is least-privilege; GitHub `pypi` environment permits only `v*`, while the PyPI publisher remains external |
| GitHub revision | `Checked in` | Release-source SHA `ad7aebd450d2dbe3607a7ec875027e0cae573cfe` is on public default branch `main` with terminal CI/CodeQL success |
| PyPI package | `Blocked` | JSON and Simple endpoints return 404; matching pending Trusted Publisher is not configured |
| Live PropertyRadar behavior | `Bounded smoke passed` | Authorized account-status GET authenticated and returned 10 status objects; no payload, mutation, or purchase |

## Broad Blockers Before Public Release

- Resolve vendor/legal suitability of a public SDK under the API's end-user and
  redistribution terms.
- Configure the exact `property-radar` pending Trusted Publisher through the
  authenticated PyPI account.
- After both gates clear, create the exact `v0.1.0` tag and verify the one-time
  OIDC publication and GitHub Release.

## Focused Tracker Snapshot

| Focused tracker | Current state | Why it matters |
| --- | --- | --- |
| `api-coverage-readiness.md` | 37/37 verified locally | Prevents missed or invented endpoint wrappers |
| `release-readiness.md` | GitHub candidate and docs verified; public release blocked | Keeps local build, GitHub, docs, PyPI, and live proof separate |

## Current Conclusion

The local and checked-in release candidate, terminal CI/CodeQL, published
documentation, and one bounded live smoke are complete. No PyPI version or
GitHub Release is claimed. The only remaining slice is externally blocked by
the matching PyPI publisher and PropertyRadar public-SDK/account-use
confirmation.
