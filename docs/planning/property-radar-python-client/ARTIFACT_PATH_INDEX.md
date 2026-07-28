# Property Radar Python Client Artifact Path Index

## Purpose

- This file is the canonical naming and path index for the planning set.
- This file is not the current-status ledger.
- Future prompts should use this file instead of hardcoded path assumptions.

## Canonical Role Index

### Planning Root

- Actual repo path: `docs/planning/property-radar-python-client/`
- Already exists: `YES`
- Canonical for future prompts: `YES`
- Confidence: `High`
- Explanation: One initiative owns package layout, API coverage, release
  automation, and publication readiness.

### Landing README

- Actual repo path:
  `docs/planning/property-radar-python-client/README.md`
- Already exists: `YES`
- Canonical for future prompts: `YES`
- Confidence: `High`

### Foundation Decisions

- Actual repo path:
  `docs/planning/property-radar-python-client/foundation/`
- Already exists: `YES`
- Canonical for future prompts: `YES`
- Confidence: `High`

### Readiness Overview

- Actual repo path:
  `docs/planning/property-radar-python-client/trackers/readiness-overview.md`
- Already exists: `YES`
- Canonical for future prompts: `YES`
- Confidence: `High`

### Execution Directory

- Actual repo path:
  `docs/planning/property-radar-python-client/execution/`
- Already exists: `YES`
- Canonical for future prompts: `YES`
- Confidence: `High`

### Execution Ledger

- Actual repo path:
  `docs/planning/property-radar-python-client/execution/execution-plan.md`
- Already exists: `YES`
- Canonical for future prompts: `YES`
- Confidence: `High`

### Package Layout Plan

- Actual repo path:
  `docs/planning/property-radar-python-client/execution/package-layout-plan.md`
- Already exists: `YES`
- Canonical for future prompts: `YES`
- Confidence: `High`
- Explanation: Architecture baseline; it is not a competing active plan.

### Canonical Active Plan

- Actual repo path:
  `docs/planning/property-radar-python-client/execution/api-library-implementation-plan.md`
- Already exists: `YES`
- Canonical for future prompts: `YES`
- Confidence: `High`

### Future Phase Proof Files

- Actual repo path:
  `docs/planning/property-radar-python-client/execution/client_PHASE_##_<slug>.md`
- Already exists: `NO`
- Canonical for future prompts: `YES`
- Confidence: `High`

## Runtime Artifact Homes

| Artifact | Canonical path |
| --- | --- |
| Distribution metadata and tool configuration | `pyproject.toml` |
| Importable package | `src/property_radar/` |
| Shared transport and error boundary | `src/property_radar/_transport.py`, `src/property_radar/exceptions.py` |
| Public facade | `src/property_radar/client.py` |
| Resource clients | `src/property_radar/resources/` |
| Typed public contracts | `src/property_radar/types.py`, `src/property_radar/py.typed` |
| Secretless unit and contract tests | `tests/` |
| User documentation | `docs/` outside `docs/planning/` |
| Examples | `examples/` using synthetic identifiers and environment-only credentials |
| CI, docs, and release automation | `.github/workflows/` |

## Directory Structure

```text
docs/planning/property-radar-python-client/
  README.md
  ARTIFACT_PATH_INDEX.md
  foundation/
  trackers/
  execution/
```
