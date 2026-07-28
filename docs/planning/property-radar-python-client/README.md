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

## Project Baseline

| Surface | Evidence-backed answer |
| --- | --- |
| Repository and branch state | Local `main` has no commits. The only pre-existing files are untracked repo-local skills under `.codex/`. No local remote is configured. |
| GitHub target | `theperrygroup/property_radar` is a public, empty repository with no default branch as of 2026-07-28. |
| Structural reference | Local `wfrmls` and GitHub `theperrygroup/wfrmls`, current `main` at `d23464a96fdc01bc883d943290186be269caceda`. |
| Vendor contract | Official OpenAPI 3.1 document at `https://developers.propertyradar.com/_spec/api.yaml`, API version `5.1.1.0`, 29 paths and 37 operations as inspected 2026-07-28. |
| Current verification commands | None existed at baseline. Phase 0 establishes `uv sync --all-extras`, Ruff, mypy, pytest/coverage, MkDocs strict build, package build, Twine check, and wheel-install smoke verification. |
| CI, deployment, or live proof path | None existed locally or in the empty GitHub target. The plan adds secretless CI, strict docs deployment, and trusted-publishing release automation. |
| External systems and approval boundaries | PropertyRadar credentials and live calls, paid `Purchase=1` requests, lists/imports/automations/webhooks mutations, GitHub push/settings, PyPI project/trusted-publisher setup, release tags, and package publication are distinct boundaries. |
| Important unknowns | PyPI ownership and trusted-publisher configuration are not established; no PropertyRadar test account is in scope; vendor terms and trademark questions are not resolved by this technical plan. |

## Current Status Snapshot

Snapshot date: `2026-07-28`

| Lens | Current answer |
| --- | --- |
| Planning foundation | Full scaffold created from current repository, WFRMLS, GitHub, PyPI, and official PropertyRadar documentation evidence. |
| Working-tree or checked-in implementation truth | No runtime implementation existed when this scaffold was created. |
| Verification or deployed truth | No project-native verification, CI, docs deployment, GitHub revision, or PyPI artifact existed at baseline. |
| External-service truth | Official documentation was inspected read-only. No PropertyRadar API request, mutation, purchase, or credential use occurred. |
| Highest-risk remaining surface | Safe handling of billable lookups, personal data, and mutations while maintaining complete endpoint coverage. |

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
