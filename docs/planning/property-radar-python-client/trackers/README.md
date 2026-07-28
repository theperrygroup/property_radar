# Readiness Trackers

These trackers provide live, evidence-backed status views. They do not replace
the execution ledger or prove deployment/publication.

## Read Order

1. `readiness-overview.md`
2. `api-coverage-readiness.md` for wrapper completeness
3. `release-readiness.md` for GitHub/docs/PyPI status

## Grade Rules

- `Planned`: task and acceptance criteria exist only in docs.
- `Implemented locally`: working-tree implementation exists.
- `Verified locally`: every focused local gate passed after the last edit.
- `CI verified`: exact pushed revision passed configured CI.
- `Published`: authoritative PyPI/GitHub/docs readback proves the artifact.
- `Externally verified`: an authorized live vendor outcome was observed.
- `Blocked`: next action is known but requires a missing external prerequisite.

## Update Rules

- Update the focused tracker first, then `readiness-overview.md`, then the
  execution ledger.
- Re-read the official specification before changing the denominator.
- Never count a generic raw request escape hatch as documented method coverage.
