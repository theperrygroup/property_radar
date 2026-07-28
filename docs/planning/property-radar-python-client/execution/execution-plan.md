# Property Radar Python Client Execution Plan

This file is the evidence-backed ledger. It records what has landed, what has
been verified, what is blocked, and what remains open.

## 1. Ledger Scope

- Use `roadmap.md` for baseline dependency order.
- Use `api-library-implementation-plan.md` for the canonical active sequence.
- Use focused trackers for endpoint and release readiness.
- Update this ledger after each verified implementation slice.

## 2. Current Evidence Snapshot

Snapshot date: `2026-07-28`

| Evidence level | Current answer | Source and freshness |
| --- | --- | --- |
| Planned | Full package-layout and 37-operation implementation plans are checked in | Planning tree, 2026-07-28 |
| Implemented | Full 37-operation client, tests, docs, examples, contract tooling, and automation | Release-source revision `ad7aebd450d2dbe3607a7ec875027e0cae573cfe`, 2026-07-28 |
| Checked in | Local `main`, `origin/main`, remote HEAD, and GitHub branch readback matched the release-source SHA before this planning-only refresh | Local/GitHub readback, 2026-07-28 |
| Locally verified | Ruff, strict mypy, 155 tests at 99.11% coverage, strict docs, actionlint, 37-operation drift, secret scan, Python 3.10/3.14 tests, artifacts, and clean-wheel smoke pass | Local commands after final code edit, 2026-07-28 |
| CI verified | CI `30339288539` and CodeQL `30339288568` succeeded on `ad7aebd`; the current CodeQL analysis has zero results and repository readback has zero open alerts | GitHub Actions/security readback, 2026-07-28 |
| Deployed or operationally active | Pages deployment `5635871048` succeeded from `e278799`; the HTTPS site returns HTTP 200 and identifies version 0.1.0/37 operations | GitHub Pages and content readback, 2026-07-28 |
| External-service outcome | Official JSON contract matches 37 operations; one authorized `Layout=menu` account-status GET authenticated and returned a list of 10 without printing data | Vendor readback, 2026-07-28 |

## 3. Current Blockers

- The exact pending Trusted Publisher is not configured in an authenticated
  PyPI account. Public JSON and Simple endpoints still return 404.
- Public distribution remains gated by confirmation that it fits the
  PropertyRadar account agreement and intended end-user use.

## 4. Completed Planning Proof

### 2026-07-28 - Project And Reference Discovery

- Local target: empty `main`, no commits, no remote; preserve `.codex/`.
- GitHub target: public and empty.
- WFRMLS reference: local and GitHub `main` at
  `d23464a96fdc01bc883d943290186be269caceda`.
- Official PropertyRadar contract: OpenAPI 3.1 version 5.1.1.0, 29 paths,
  37 operations, 9 tags.
- Tool baseline: Python 3.14.3, uv 0.9.17, Ruff 0.14.2, mypy 2.1.0,
  pytest 9.0.3, Git 2.50.1, GitHub CLI 2.96.0.
- Result: full planning scaffold, architecture decision, package layout plan,
  canonical API implementation plan, and focused trackers created locally.
- Evidence level: `implemented locally (uncommitted)` for docs only.

### 2026-07-28 - P0-001 Package And Verification Bootstrap

- Working-tree proof:
  - `pyproject.toml`, `uv.lock`, root governance files, `src/property_radar/`,
    bootstrap tests, MkDocs configuration, and initial user docs.
- Verification:
  - `uv sync --all-extras` - passed.
  - `uv run ruff format --check .` - passed.
  - `uv run ruff check .` - passed.
  - `uv run mypy src tests scripts` - passed.
  - `uv run pytest` - 2 passed, 100% measured coverage.
  - `uv run mkdocs build --strict` - passed.
  - `uv run python -m build` - wheel and sdist built.
  - `uv run twine check dist/*` - both artifacts passed.
  - `git diff --check` - passed.
- Result: `P0-001` is verified locally and uncommitted.

### 2026-07-28 - P1-001 Shared Transport And Safety Core

- Working-tree proof:
  - `src/property_radar/_transport.py`
  - `src/property_radar/client.py`
  - `src/property_radar/exceptions.py`
  - `src/property_radar/types.py`
  - `src/property_radar/resources/`
  - `tests/unit/test_transport.py`
  - `tests/unit/test_client.py`
- Behavior proved:
  - explicit/environment/token-provider authentication without import-time
    environment mutation
  - one shared context-managed transport and lazy resource facade
  - comma-delimited and repeated query serialization
  - all 2xx handling, sanitized status/request/retry metadata, malformed JSON,
    network, and timeout errors
  - safe GET/read-like POST retries with `Retry-After`
  - no automatic retry for mutations or paid calls
  - mutation and charge denial before network I/O
- Verification:
  - `uv run ruff format --check src tests` - passed.
  - `uv run ruff check src tests` - passed.
  - `uv run mypy src tests scripts` - passed for 20 source files.
  - focused `uv run pytest` command - 36 passed, 99.52% coverage.
  - `git diff --check` - passed.
- Result: `P1-001` is verified locally and uncommitted.

### 2026-07-28 - P2/P3 Complete API Resources

- Implemented all 37 official operations across accounts, documents,
  properties, persons, suggestions, lists, imports, automations, and
  integrations.
- Added typed request arguments, truthful status-layout response typing,
  bounded property iteration, safe path-segment encoding, and exact vendor
  casing/array serialization.
- All 17 `Purchase` operations default to `Purchase=0`; automation purchase
  settings form an eighteenth charge-capable operation.
- Persistent writes require mutation opt-in. Paid calls require charge opt-in
  and are never retried.
- Automation replacement requires explicit full-replacement acknowledgment and
  non-empty content. Webhook URLs require credential-free HTTPS.
- Result: `P2-001` through `P3-002` are verified locally and uncommitted.

### 2026-07-28 - P4/P5 Documentation, Contract, And Automation

- Packaged a 37-operation endpoint manifest and a dependency-free JSON OpenAPI
  drift command.
- Added authentication, request/response, pagination, error/retry, safety,
  resource API, development/release docs, and synthetic examples.
- Added SHA-pinned CI, CodeQL, Pages, scheduled drift, Dependabot, and
  build-once OIDC Trusted Publishing workflows with least-privilege jobs.
- `actionlint` and strict MkDocs both pass after the final workflow/doc edits.
- Live contract readback: 29 paths and 37 operations match the manifest.
- Result: `P4-001` and `P5-001` are verified locally and uncommitted.

### 2026-07-28 - P6-001 Local Release Candidate

- Final repository gates:
  - Ruff format/check passed.
  - strict mypy passed for 33 source files.
  - 155 tests passed at 99.11% branch coverage on Python 3.13.
  - the same 155 tests passed in isolated Python 3.10 and 3.14 environments.
  - strict MkDocs, actionlint, Git diff whitespace, and official contract drift
    checks passed.
  - detect-secrets reported zero non-allowlisted findings; high-risk credential
    prefixes reported zero; `.env` is ignored.
- Artifact proof:
  - wheel and sdist built from source and passed Twine.
  - wheel contains `py.typed` and the endpoint manifest; artifacts omit tests,
    `.env`, and `.codex/`.
  - base wheel installed into a clean Python 3.14 environment, reported version
    `0.1.0`, loaded all 37 manifest operations, passed `pip check`, and ran the
    packaged live drift command.
- Result: `P6-001` is verified locally and uncommitted.

### 2026-07-28 - P6-004 Authorized Non-Billable Smoke

- Loaded the ignored `.env` only for one explicit live command.
- Called `GET /v1/accounts/preferences/statuses?Layout=menu` with no mutation,
  purchase, or retry.
- Sanitized output: authenticated, result type list, result count 10.
- No key, label, response body, or licensed record was printed or persisted.
- Result: `P6-004` is externally verified.

### 2026-07-28 - P6-002 Checked-In GitHub Revision

- Repository proof:
  - initial implementation commit:
    `f826bf351879add9463106d65bec0de13ee8126f`
  - workflow lock-mode repair:
    `e278799bc09de5ebe7e647474e85b8cf5c3c69c5`
  - final release-source/test assertion revision:
    `ad7aebd450d2dbe3607a7ec875027e0cae573cfe`
  - local `main`, `origin/main`, remote HEAD, and GitHub branch API matched that
    release-source revision; only the preserved untracked `.codex/` tree
    remained locally.
- CI proof:
  - CI run `30339288539` succeeded on `ad7aebd` with quality, strict docs,
    Python 3.10-3.14 Linux, Python 3.13 macOS/Windows, distribution, Twine, and
    clean-wheel jobs green.
  - CodeQL run `30339288568` succeeded on `ad7aebd` with zero current results.
    The one prior high-severity finding was confined to a substring assertion
    in a test, changed to exact equality, and marked fixed by the current
    analysis. Its obsolete disabled-default-setup instance was dismissed as
    `used in tests`; repository readback then reported zero open alerts.
- Documentation proof:
  - documentation run `30338811225` and Pages deployment `5635871048`
    succeeded from `e278799`.
  - `https://theperrygroup.github.io/property_radar/` returned HTTP 200 and
    displayed the Property Radar Python Client documentation, version 0.1.0,
    contract 5.1.1.0, and all 37 operations.
- Release-boundary setup:
  - GitHub environment `pypi` now exists with a custom deployment policy that
    permits only `v*` tags.
  - no tag or public version was created.
- Result: `P6-002` is verified at checked-in, CI, CodeQL, and deployed-docs
  evidence levels.

## 5. Current Work Queue

| Task | Status | Current evidence or blocker |
| --- | --- | --- |
| `P0-001` Package bootstrap | `COMPLETE` | Verified locally and checked in |
| `P1-001` Transport and safety core | `COMPLETE` | Verified locally and checked in |
| `P2-001` through `P3-002` resource families | `COMPLETE` | 37 wrappers and safety tests pass locally and in CI |
| `P4-001` docs and contract coverage | `COMPLETE` | 37/37 mapping, strict docs, and Pages pass |
| `P5-001` workflows | `COMPLETE` | CI, CodeQL, Pages, and exact release workflow are operational |
| `P6-001` full local release proof | `COMPLETE` | Final source/artifact gates pass |
| `P6-002` GitHub push and CI | `COMPLETE` | Exact source revision has terminal CI/CodeQL and Pages proof |
| `P6-003` PyPI/GitHub release | `BLOCKED` | Matching PyPI publisher and vendor-use confirmation are absent |
| `P6-004` live vendor smoke | `COMPLETE` | One authorized non-billable status readback passed |

## 6. Current Conclusion

The repository-local candidate, checked-in GitHub source, CI, CodeQL,
deployed documentation, and bounded live smoke are verified. No safe
repository-local slice remains. Public release is blocked until the matching
PyPI pending Trusted Publisher and the PropertyRadar public-SDK/account-use
confirmation are authoritatively satisfied; no tag or publication is implied
by the prepared GitHub environment.
