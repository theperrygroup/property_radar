# Execution Docs

This folder holds the ordered plans and evidence-backed ledger for the Property
Radar Python client.

Read this alongside:

- `../foundation/architecture-and-safety-adr.md`
- `../trackers/readiness-overview.md`
- the focused tracker for the selected slice

## File Roles

| File | Use it for | Not for |
| --- | --- | --- |
| `execution-plan.md` | Live evidence-backed ledger, blockers, completed proof | Historical sequencing |
| `package-layout-plan.md` | Completed architecture planning baseline | Current implementation status |
| `api-library-implementation-plan.md` | Canonical active implementation sequence | Replacing the ledger |
| `roadmap.md` | Baseline dependency order and task definitions | Freshest status |
| `client_PHASE_##_<slug>.md` | Durable proof for one explicit slice when needed | Aggregate status |

## Canonical Active Plan

`api-library-implementation-plan.md` is the single canonical active plan.
`package-layout-plan.md` records the first requested planning outcome and feeds
the active plan; it is not a competing active sequence.

## Fastest Answers

| Question | Open first |
| --- | --- |
| What is the latest evidence-backed status? | `execution-plan.md`, then `../trackers/readiness-overview.md` |
| What should happen next? | `api-library-implementation-plan.md` |
| Why is the package arranged this way? | `package-layout-plan.md` |
| Which endpoint wrappers remain? | `../trackers/api-coverage-readiness.md` |
| What blocks release? | `../trackers/release-readiness.md` |

## Rules

- Complete tasks only when every named acceptance criterion has current proof.
- Update focused trackers, readiness overview, and the execution ledger after
  each verified slice.
- Edit `roadmap.md` only when baseline order, dependencies, or task definitions
  change.
- Keep live API, GitHub, docs, PyPI, and local evidence distinct.
