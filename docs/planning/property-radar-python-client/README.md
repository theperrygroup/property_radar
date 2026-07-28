# Property Radar Python Client Planning

This directory is the canonical operating guide for the Property Radar Python
client planning set.

## Role

- This tree is docs-only.
- Implementation truth comes from the current working tree or checked-in code,
  labeled honestly, plus project-native verification rather than roadmap items
  alone.
- External-service truth comes from an authoritative readback or observable
  outcome, not local code alone.

## Interpretation Rules

- Planning complete is not the same as shipped.
- Working-tree implementation is not checked-in, CI-verified, published, or
  externally verified.
- The API coverage tracker measures wrapper coverage, not successful live calls.
- The canonical active plan outranks the historical roadmap for the current
  implementation sequence.

## Initial Project Baseline

| Surface | Evidence-backed answer |
| --- | --- |
| Repository and branch state | The project began with no commits or runtime files. Pre-existing untracked repo-local skills under `.codex/` were preserved. |
| GitHub target | `theperrygroup/property_radar` began as a public, empty repository with no default branch. |
| Structural reference | Local `wfrmls` and GitHub `theperrygroup/wfrmls`, current `main` at `d23464a96fdc01bc883d943290186be269caceda`. |
| Vendor contract | Official OpenAPI 3.1 document at `https://developers.propertyradar.com/_spec/api.yaml`, API version `5.1.1.0`, 29 paths and 37 operations as inspected 2026-07-28. |
| Verification path | None existed initially. Phase 0 established `uv sync --all-extras --locked`, Ruff, mypy, pytest/coverage, strict MkDocs, package build, Twine, and installed-wheel verification. |
| External systems and approval boundaries | PropertyRadar paid requests and mutations, PyPI publisher setup, release tags, and package publication remain distinct boundaries. |
| Important unknowns | PyPI publisher ownership is not established; vendor terms and trademark questions are not resolved by this technical plan. |

## Current Status Snapshot

Snapshot date: `2026-07-28`

| Lens | Current answer |
| --- | --- |
| Planning foundation | Full scaffold created from current repository, WFRMLS, GitHub, PyPI, and official PropertyRadar documentation evidence. |
| Working-tree or checked-in implementation truth | Version `0.1.0` implements all 37 documented operations. Release-source revision `ad7aebd450d2dbe3607a7ec875027e0cae573cfe` is pushed to `main`; only the pre-existing untracked `.codex/` tree remains local. |
| Verification or deployed truth | Local gates, CI run `30339288539`, CodeQL run `30339288568`, zero-open-alert readback, and the live Pages deployment all pass. |
| External-service truth | The official 37-operation contract matches the packaged manifest. One authorized non-billable status request authenticated and returned 10 objects without payload disclosure. PyPI is not published. |
| Highest-risk remaining surface | Public-release suitability plus the PyPI pending Trusted Publisher and irreversible `v0.1.0` publication boundary. |

## Fastest Reality Check

- `foundation/architecture-and-safety-adr.md`: durable package and safety
  decisions.
- `execution/api-library-implementation-plan.md`: canonical active sequence.
- `trackers/readiness-overview.md`: current readiness summary.
- `execution/execution-plan.md`: evidence-backed implementation ledger.

## Start Here

1. `foundation/architecture-and-safety-adr.md`
2. `execution/api-library-implementation-plan.md`
3. `trackers/readiness-overview.md`
4. `trackers/api-coverage-readiness.md`
5. `execution/execution-plan.md`
6. `execution/roadmap.md` only for baseline dependency order
7. `ARTIFACT_PATH_INDEX.md` for canonical paths

## Directory Guide

| Folder or file | Role | Open first when you need |
| --- | --- | --- |
| `foundation/` | Durable source, architecture, safety, and release decisions | Ownership or policy questions |
| `trackers/` | Live API and release readiness scoreboards | Current blockers |
| `execution/README.md` | Execution navigation | Next implementation slice |
| `execution/package-layout-plan.md` | Package-layout design baseline | Why the repository is arranged this way |
| `execution/api-library-implementation-plan.md` | Canonical active sequence | What should be implemented next |
| `execution/execution-plan.md` | Evidence-backed status ledger | What is actually complete |
| `ARTIFACT_PATH_INDEX.md` | Naming and path index | Canonical artifact homes |

## Document Precedence

1. `foundation/` wins for durable rules and boundaries.
2. `execution/api-library-implementation-plan.md` wins for the current focused
   execution sequence.
3. Focused trackers plus `execution/execution-plan.md` win for live,
   evidence-backed status.
4. `execution/roadmap.md` is baseline sequencing and historical context.
5. `ARTIFACT_PATH_INDEX.md` wins for exact paths and naming.

## Common Workflows

| Goal | Open these first |
| --- | --- |
| Start the next slice | `execution/execution-plan.md`, `execution/api-library-implementation-plan.md`, and the relevant readiness tracker |
| Check endpoint coverage | `trackers/api-coverage-readiness.md` and the official OpenAPI document |
| Prepare a release | `trackers/release-readiness.md`, the release workflow, and the exact built artifacts |
| Determine what is live | `execution/execution-plan.md` plus GitHub, PyPI, or PropertyRadar authoritative readback |

## Update Order

1. Relevant phase proof file, when needed
2. Relevant focused tracker
3. `trackers/readiness-overview.md`
4. `execution/execution-plan.md`
5. Relevant foundation document if a durable rule changed
6. Landing or path-index files only if navigation or canonical paths changed

## Working Rules

- Keep planning artifacts under this tree and runtime artifacts outside it.
- Use synthetic response fixtures; never check in credentials, licensed
  payloads, or personal data.
- Keep billable behavior and mutations explicitly opt-in.
- Re-read the official OpenAPI document before declaring coverage current.
- Keep local, checked-in, CI, docs-deployed, PyPI-published, and live-API
  evidence separate.
