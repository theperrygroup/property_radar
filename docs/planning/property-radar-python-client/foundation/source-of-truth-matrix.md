# Source Of Truth Matrix

Snapshot date: `2026-07-28`

| Question | Authoritative source | Current answer | Refresh rule |
| --- | --- | --- | --- |
| What code is implemented? | Current Property Radar working tree or exact Git revision | No runtime code at baseline | Inspect after every implementation slice |
| What is the intended package shape? | `architecture-and-safety-adr.md` and package-layout plan | `src/` package, facade plus resource modules, shared transport | Update only after an explicit architecture change |
| What API operations exist? | `https://developers.propertyradar.com/_spec/api.yaml` | OpenAPI 3.1, version 5.1.1.0, 29 paths, 37 operations, 9 tags | Refresh before coverage completion and each release |
| How do criteria work? | Official Understanding Criteria and Criteria Reference pages | Named criteria objects with multiple value/range/date/geospatial forms | Do not duplicate the full vendor catalog; link and test generic encoding |
| What library patterns are being reused? | Local `wfrmls` checkout and current GitHub `main` | Facade/resource split, central errors, typed package marker, docs and release shape | Re-open before major consistency work |
| What WFRMLS patterns are rejected? | Current WFRMLS code/workflows plus audit findings | Hard-coded credentials, per-resource sessions, import-time dotenv, weak/soft gates, skip pagination, token-based PyPI publish | Never copy; regression-test the chosen replacements |
| Is the GitHub target current? | `theperrygroup/property_radar` GitHub repository | Public and empty at baseline | Re-read before push/settings changes |
| Is the PyPI distribution available/current? | PyPI JSON/project endpoint for `property-radar` | HTTP 404 at baseline; ownership not established | Re-read before registration or publication |
| Is a live API behavior proven? | Authorized PropertyRadar account response with sanitized evidence | No live calls or credentials in scope | Never infer from mocked tests |
| Is a release public? | Exact GitHub release, workflow run, and PyPI file hashes | No release at baseline | Verify exact version and artifacts after publication |

## Evidence Boundaries

- The vendor specification proves a documented contract, not service
  availability for a particular account.
- Mocked contract tests prove request construction and response handling, not
  entitlement, balance, data freshness, or permitted use.
- A GitHub push proves only a remote revision until CI reaches a terminal state.
- A successful build does not prove PyPI publication.
- A PyPI project page does not prove GitHub release, docs deployment, or live
  PropertyRadar behavior.
