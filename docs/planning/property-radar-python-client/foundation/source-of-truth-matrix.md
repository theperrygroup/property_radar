# Source Of Truth Matrix

Snapshot date: `2026-07-28`

| Question | Authoritative source | Current answer | Refresh rule |
| --- | --- | --- | --- |
| What code is implemented? | Current Property Radar working tree or exact Git revision | Version 0.1.0 implements all 37 documented operations; release-source revision `ad7aebd450d2dbe3607a7ec875027e0cae573cfe` | Inspect after every implementation slice |
| What is the intended package shape? | `architecture-and-safety-adr.md` and package-layout plan | `src/` package, facade plus resource modules, shared transport | Update only after an explicit architecture change |
| What API operations exist? | `https://developers.propertyradar.com/_spec/api.yaml` | OpenAPI 3.1, version 5.1.1.0, 29 paths, 37 operations, 9 tags | Refresh before coverage completion and each release |
| How do criteria work? | Official Understanding Criteria and Criteria Reference pages | Named criteria objects with multiple value/range/date/geospatial forms | Do not duplicate the full vendor catalog; link and test generic encoding |
| What library patterns are being reused? | Local `wfrmls` checkout and current GitHub `main` | Facade/resource split, central errors, typed package marker, docs and release shape | Re-open before major consistency work |
| What WFRMLS patterns are rejected? | Current WFRMLS code/workflows plus audit findings | Hard-coded credentials, per-resource sessions, import-time dotenv, weak/soft gates, skip pagination, token-based PyPI publish | Never copy; regression-test the chosen replacements |
| Is the GitHub target current? | `theperrygroup/property_radar` GitHub repository and exact workflow readback | Public `main`; release-source SHA `ad7aebd`; CI and CodeQL succeeded, zero alerts remain, and Pages is live | Re-read before push/settings changes or release |
| Is the PyPI distribution available/current? | PyPI JSON/Simple endpoints plus publisher readback | Both public endpoints return 404; GitHub `pypi` environment permits only `v*` tags, but the matching PyPI publisher is not configured | Re-read before registration or publication |
| Is a live API behavior proven? | Authorized PropertyRadar account response with sanitized evidence | One non-billable account-status GET authenticated and returned a list of 10; no payload was persisted | Never infer other endpoint/account behavior from this smoke |
| Is a release public? | Exact GitHub release, workflow run, and PyPI file hashes | No GitHub Release or PyPI version exists | Verify exact version and artifacts after publication |
| Is CI current? | Exact GitHub Actions SHA and terminal job conclusions | CI `30339288539` and CodeQL `30339288568` succeeded on `ad7aebd`; current analysis has zero results and repository readback has zero open alerts | Re-read after every pushed source/config revision |
| Are docs deployed? | GitHub Pages deployment plus HTTPS content readback | Deployment `5635871048` from `e278799` succeeded; `https://theperrygroup.github.io/property_radar/` returns HTTP 200 | Re-read after docs deployment |

## Evidence Boundaries

- The vendor specification proves a documented contract, not service
  availability for a particular account.
- Mocked contract tests prove request construction and response handling, not
  entitlement, balance, data freshness, or permitted use.
- A GitHub push proves only a remote revision until CI reaches a terminal state.
- A successful build does not prove PyPI publication.
- A PyPI project page does not prove GitHub release, docs deployment, or live
  PropertyRadar behavior.
