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
| CI and docs automation | `Implemented locally` | SHA-pinned CI, CodeQL, Pages, drift, and Dependabot files pass actionlint; remote proof remains |
| Release automation | `Implemented locally` | Build-once OIDC workflow is least-privilege; external PyPI configuration remains |
| GitHub revision | `None` | Local and remote repositories have no commits/default branch |
| PyPI package | `Blocked` | Name endpoint returned 404; ownership and trusted publisher are not configured |
| Live PropertyRadar behavior | `Bounded smoke passed` | Authorized account-status GET authenticated and returned 10 status objects; no payload, mutation, or purchase |

## Broad Blockers Before Public Release

- Push and receive terminal CI proof for the exact revision.
- Resolve vendor/legal suitability of a public SDK under the API's end-user and
  redistribution terms.
- Confirm the exact distribution name and configure PyPI Trusted Publishing.
- Choose and authorize the exact release tag/version.

## Focused Tracker Snapshot

| Focused tracker | Current state | Why it matters |
| --- | --- | --- |
| `api-coverage-readiness.md` | 37/37 verified locally | Prevents missed or invented endpoint wrappers |
| `release-readiness.md` | Local release candidate verified | Keeps local build, GitHub, docs, PyPI, and live proof separate |

## Current Conclusion

The full local release candidate and one bounded live smoke are complete. The
next safe slice is the exact commit/push and GitHub proof. No CI, deployment,
GitHub release, or PyPI publication is claimed yet.
