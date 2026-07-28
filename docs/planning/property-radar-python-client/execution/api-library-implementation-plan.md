# Property Radar API Library Implementation Plan

Status: `ACTIVE`

Effective date: `2026-07-28`

This is the canonical execution sequence. It uses the package-layout plan and
the official PropertyRadar OpenAPI 3.1 contract, version `5.1.1.0`, inspected
2026-07-28.

## 1. Outcome And Scope

Target outcome: a locally verified, GitHub-hosted, PyPI-ready synchronous Python
client with one public method for each of the 37 documented API operations.

Included:

- Package/runtime bootstrap and repository governance.
- Shared transport, typed envelopes, criteria helpers, safe retries, and error
  mapping.
- Accounts, documents, properties, persons, suggestions, lists, imports,
  automations, and integrations resources.
- Secretless tests, endpoint-manifest drift checking, user/API docs, examples,
  CI, docs deployment, release automation, and distribution validation.
- GitHub push and CI monitoring when the exact verified revision is ready.

Excluded from repository-complete status:

- Live vendor calls, credential provisioning, licensed payload capture, or
  proof of a particular subscription/entitlement.
- Automatic `Purchase=1`, non-refundable charges, or unrequested external
  mutations.
- Async API.
- Reproducing the full vendor criteria catalog or inline OpenAPI schema.

Public acceptance:

- All 37 documented operations have tested wrapper methods.
- Preview/read behavior is usable without enabling mutations or charges.
- Persistent changes and paid requests are denied before network I/O unless
  explicitly enabled.
- Full local quality, type, test, docs, build, artifact, and wheel-install gates
  pass after the final edit.
- The exact GitHub revision reaches terminal CI success if push remains
  authorized and accessible.
- PyPI publication is claimed only after authoritative package readback.

## 2. Current Baseline

| Surface | Current evidence | Confidence or freshness |
| --- | --- | --- |
| Property Radar working tree | No runtime files or commits at planning baseline; `.codex/` skills are unrelated untracked inputs to preserve | High, 2026-07-28 |
| GitHub target | Public and empty, no default branch | High, 2026-07-28 |
| WFRMLS reference | Local and remote `main` match `d23464a`; useful facade/resource and release patterns plus documented defects | High, 2026-07-28 |
| Vendor contract | Official OpenAPI 3.1 version 5.1.1.0; 29 paths, 37 operations, 9 resource tags | High, 2026-07-28 |
| PyPI distribution | `property-radar` JSON/project endpoint returned 404 | Time-sensitive, 2026-07-28 |
| Verification path | Must be bootstrapped in Phase 0 | High |
| External system | User supplied a local ignored credential and authorized one bounded non-billable account-status smoke; it returned 10 status objects without payload disclosure | High, 2026-07-28 |

## 3. Sequencing Rules

- Bootstrap verification before endpoint implementation.
- Land transport and safety behavior before resource methods.
- Implement read/preview families before persistent mutation families.
- Advance only after the focused checks pass after the last relevant edit.
- Refresh coverage and release trackers after each phase.
- Do not let mocked proof become live API, CI, docs deployment, or PyPI proof.
- Stop before a paid/live call or irreversible publication when required access,
  exact target configuration, or authoritative safeguards are missing.

## 4. Ordered Task Sequence

| Order | Task ID | Slice | Dependencies | Status | Required evidence |
| --- | --- | --- | --- | --- | --- |
| 1 | `P0-001` | Package, governance, docs, and verification bootstrap | Planning complete | `COMPLETE` | Local formatting, typing, smoke test, strict docs, and build tools run |
| 2 | `P1-001` | Shared transport, exceptions, types, lifecycle, and safety gates | P0 | `COMPLETE` | Focused unit tests and strict type/lint proof |
| 3 | `P2-001` | Accounts and documents wrappers | P1 | `COMPLETE` | Endpoint request/response/error tests |
| 4 | `P2-002` | Properties read/search/comps/parcels/transactions/evictions | P1 | `COMPLETE` | Eight operation mappings and pagination tests |
| 5 | `P2-003` | Persons and suggestions wrappers | P1 | `COMPLETE` | Nine operation mappings, charge guard, read-like POST tests |
| 6 | `P3-001` | Lists and list-item wrappers | P1 | `COMPLETE` | Eight operation mappings and mutation guard tests |
| 7 | `P3-002` | Imports, automations, and integrations wrappers | P1, P3-001 | `COMPLETE` | Nine operation mappings, nested charge/mutation tests |
| 8 | `P4-001` | Complete docs, examples, endpoint manifest, and drift check | P2-P3 | `COMPLETE` | 37/37 manifest mapping and strict docs build |
| 9 | `P5-001` | CI, docs deployment, Dependabot, and OIDC release workflows | P0, P4 | `COMPLETE` | Workflow validation and least-privilege review |
| 10 | `P6-001` | Full local release-candidate verification | P1-P5 | `COMPLETE` | All gates green, clean installed-wheel smoke |
| 11 | `P6-002` | Commit, push, and monitor exact GitHub revision | P6-001 | `NEXT` | Checked-in revision and terminal GitHub CI readback |
| 12 | `P6-003` | Configure and publish PyPI/GitHub release | P6-001, P6-002, external setup | `BLOCKED` | Trusted publisher, exact tag, PyPI hashes, GitHub release |
| 13 | `P6-004` | Optional non-billable live smoke | Licensed credential and explicit authorization | `COMPLETE` | Sanitized authoritative response with zero mutation/charge |

### P0-001 - Bootstrap Package And Verification

- Outcome: establish the smallest complete `src/` package, test, docs, build,
  and governance baseline.
- Slice type: `CODE`, `CONFIG`, `DOCS`
- Exact surfaces: `pyproject.toml`, `uv.lock`, root governance/docs,
  `src/property_radar/`, minimal tests, `mkdocs.yml`, docs landing pages.
- Acceptance criteria:
  - Distribution/import names and version source are singular and correct.
  - Package imports from an editable install and ships `py.typed`.
  - Ruff, mypy, pytest, strict docs, build, and Twine commands exist and run.
  - `.gitignore` excludes credentials, environments, builds, caches, coverage,
    and local docs output without excluding source/planning artifacts.
  - No pre-existing `.codex/` file is modified.
- Required evidence level: `local`
- External state change: `NONE`

### P1-001 - Implement Transport And Safety Core

- Outcome: one shared, injectable, context-managed transport with typed errors
  and deny-by-default spend/mutation controls.
- Slice type: `CODE`
- Exact surfaces: `_transport.py`, `exceptions.py`, `types.py`, `client.py`,
  `resources/_base.py`, focused unit tests.
- Acceptance criteria:
  - Explicit argument then environment authentication; missing keys fail without
    exposing secret values.
  - All 2xx responses, empty responses, malformed JSON, documented statuses,
    network failures, and timeouts have deterministic behavior.
  - Retry only safe calls; honor `Retry-After`; do not retry mutations or paid
    calls automatically.
  - List/query encoding follows the official parameter contract.
  - Blocked charges/mutations make zero HTTP requests.
  - Facade resources share and close one transport.
- Required evidence level: `local`
- External state change: `NONE`

### P2-001 - Accounts And Documents

- Operations:
  - `GET /v1/accounts/members`
  - `GET /v1/accounts/preferences/statuses`
  - `GET /v1/documents/{DocumentID}`
- Safety: documents always send preview `Purchase=0` unless charges are enabled
  and requested.
- Required evidence level: `local`
- External state change: `NONE` in tests

### P2-002 - Properties

- Operations:
  - `GET /v1/properties/{RadarID}`
  - `POST /v1/properties`
  - `GET /v1/properties/{RadarID}/persons`
  - `GET /v1/properties/{RadarID}/evictions`
  - `GET /v1/properties/{RadarID}/comps/sales`
  - `GET /v1/properties/{RadarID}/comps/forsale`
  - `GET /v1/properties/{RadarID}/parcels`
  - `GET /v1/properties/{RadarID}/transactions`
- Acceptance criteria:
  - Criteria body, fields, pagination, comparison filters, transaction filter,
    and preview purchase flags are encoded exactly.
  - Iteration advances `Start`, stops deterministically, and never suppresses a
    later-page error as partial success.
- Required evidence level: `local`
- External state change: `NONE` in tests

### P2-003 - Persons And Suggestions

- Operations:
  - `GET /v1/persons/{PersonKey}/bankruptcies`
  - `GET /v1/persons/{PersonKey}/divorces`
  - `GET /v1/persons/{PersonKey}/liens`
  - `GET /v1/persons/{PersonKey}/probates`
  - `GET /v1/persons/{PersonKey}/relatives`
  - `POST /v1/persons/{PersonKey}/Phone`
  - `POST /v1/persons/{PersonKey}/Email`
  - `POST /v1/suggestions/SiteAddress`
  - `POST /v1/suggestions/County`
- Acceptance criteria:
  - Personal-data purchase methods default to quote/preview and require the
    charge opt-in for `Purchase=1`.
  - Suggestions are classified as retryable read-like POSTs, not mutations.
  - Criteria and pagination inputs are encoded and tested with synthetic data.
- Required evidence level: `local`
- External state change: `NONE` in tests

### P3-001 - Lists And List Items

- Operations:
  - `GET /v1/lists`
  - `POST /v1/lists`
  - `GET /v1/lists/{ListID}`
  - `PATCH /v1/lists/{ListID}`
  - `DELETE /v1/lists/{ListID}`
  - `GET /v1/lists/{ListID}/items`
  - `PUT /v1/lists/{ListID}/items`
  - `DELETE /v1/lists/{ListID}/items/{RadarID}`
- Acceptance criteria:
  - All persistent methods require `allow_mutations=True`.
  - Create/update payloads retain vendor field casing and omit unset values.
  - Mutation denial and successful request construction are both tested.
- Required evidence level: `local`
- External state change: `NONE` in tests

### P3-002 - Imports, Automations, And Integrations

- Operations:
  - `GET /v1/lists/{ListID}/import/items`
  - `POST /v1/lists/{ListID}/import/items`
  - `PATCH /v1/lists/{ListID}/import/items/{ListImportItemID}`
  - `DELETE /v1/lists/{ListID}/import/items/{ListImportItemID}`
  - `GET /v1/lists/{ListID}/automations`
  - `PUT /v1/lists/{ListID}/automations`
  - `GET /v1/integrations/webhooks`
  - `POST /v1/integrations/webhooks`
  - `DELETE /v1/integrations/webhooks/{WebhookID}`
- Acceptance criteria:
  - Persistent operations require mutation opt-in.
  - Import `Purchase=1` and automation `PurchasePhone/PurchaseEmail=1` also
    require charge opt-in.
  - Webhook secrets are sent only in bodies and never appear in errors/repr.
- Required evidence level: `local`
- External state change: `NONE` in tests

### P4-001 - Documentation And Contract Coverage

- Outcome: every facade/resource/method is documented and mapped to the official
  37-operation contract.
- Acceptance criteria:
  - Manifest contains method, path, resource, public method, mutation, and
    billable classification for all operations.
  - Contract tests fail for missing/duplicate mappings.
  - Read-only drift command reports exact additions/removals against the official
    spec.
  - Quickstart, criteria, pagination, errors, safety, resources, release, and
    synthetic examples build with `mkdocs --strict`.
- Required evidence level: `local`
- External state change: official spec download only (`READ-ONLY`)

### P5-001 - Automation

- Outcome: model the useful WFRMLS workflow stages with hard gates, secretless
  tests, least privilege, and OIDC.
- Acceptance criteria:
  - CI covers supported Python versions, platform smoke, quality, typing,
    tests/coverage, secret scan, strict docs, build, Twine, artifact contents,
    and installed-wheel smoke.
  - Docs deployment grants write permissions only to deploy.
  - Release validates strict tag/version/main ancestry, builds once, and uses
    PyPI Trusted Publishing with no password.
  - Dependabot covers Python and Actions without ignored security patches.
- Required evidence level: `local`; becomes `CI` after push
- External state change: `NONE` while authoring

### P6-001 - Local Release Candidate

- Run every documented gate after the final relevant edit.
- Inspect source, built artifacts, tracked files, and Git diff for credentials,
  personal data, unwanted tests/caches, and scope creep.
- Required evidence level: `local`

### P6-002 - GitHub Revision

- Add the user-specified `origin`, commit only the project implementation and
  planning refresh, push `main`, and monitor the exact SHA through terminal CI.
- Do not stage unrelated local-only skill inputs unless they are intentionally
  part of the repository.
- Required evidence level: `checked-in` and `CI`
- External state change: push to `theperrygroup/property_radar`

### P6-003 - Public Release

- Preconditions:
  - Exact PyPI project name and ownership confirmed.
  - `pypi` environment and trusted publisher configured for the exact GitHub
    owner/repository/workflow/environment tuple.
  - Release version/tag approved and current main CI green.
- Perform only when those external preconditions are authoritatively satisfied.
- Required evidence level: `external outcome`
- External state change: irreversible PyPI version publication and GitHub
  release/tag.

### P6-004 - Optional Live Smoke

- Requires a licensed account, explicit credential handling, a known
  non-billable request, synthetic/minimized target, and approval for that exact
  live call.
- Never use `Purchase=1` or a persistent method for this smoke.
- Required evidence level: `external outcome`

## 5. Current Next Slice

- Task: `P6-002`.
- Why it is next: all repository-local implementation, review, contract,
  documentation, workflow, release-artifact, and safe live-smoke gates are
  complete.
- Finish condition: only intended files are committed, `main` is pushed to the
  user-specified repository, Pages is enabled for the workflow, and the exact
  pushed SHA reaches terminal CI/docs/CodeQL proof.

## 6. Known Stop Conditions

- PyPI project/trusted publisher is not configured or authenticated.
- A release would claim an ambiguous distribution name or version.
- Any further live check would consume credits, mutate state, expose licensed
  payloads, or exceed the single authorized account-status smoke.
- GitHub permissions, branch target, or remote ownership no longer match the
  user's specified repository.
- The official contract changes in a way that requires a product decision.

## 7. Update Rule

- Update this file when sequence, dependencies, acceptance criteria, or the
  next-slice designation changes.
- Record completed proof in `execution-plan.md`.
- Do not mark a task complete until its required evidence appears in the ledger
  and relevant tracker.
