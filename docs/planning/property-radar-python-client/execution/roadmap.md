# Property Radar Python Client Task Roadmap

This roadmap is the baseline dependency map. Use
`api-library-implementation-plan.md` for the canonical active sequence and
`execution-plan.md` for current evidence.

## Scope And Evidence

- Structural source: local and GitHub `theperrygroup/wfrmls` at `d23464a`.
- Vendor source: official OpenAPI 3.1 version 5.1.1.0 plus official criteria,
  welcome, and changelog pages, inspected 2026-07-28.
- Target: empty local and GitHub `theperrygroup/property_radar` repositories.
- Initial verification: none; Phase 0 establishes it.
- Approval boundaries: live credentials/data, charges, persistent API
  mutations, GitHub settings beyond the push target, PyPI registration/trusted
  publishing, tags/releases, and publication.

## Harsh Sequencing Rule

No resource family may be called complete until its methods are mapped in the
endpoint manifest, request construction and safety behavior are tested, strict
typing/linting pass, and the aggregate ledger records the proof. No mocked proof
may be promoted to a live vendor, CI, docs deployment, or PyPI outcome.

## Phase 0 - Repository Foundation

### P0-001 - Bootstrap The Installable Package

- Why this task exists: the repository has no runtime or verification baseline.
- Exact files or modules affected: root metadata/governance, `src/`, `tests/`,
  user docs, `pyproject.toml`, lockfile.
- Dependency prerequisites: planning scaffold.
- Severity: `BLOCKING`
- Estimated complexity: `MEDIUM`
- Feature domain: package foundation
- Slice type: `CODE`, `CONFIG`, `DOCS`
- External state change: `NONE`
- Verification level required: `local`
- Acceptance criteria: all bootstrap checks in the active plan pass.
- What could break if skipped: later endpoint work would have no trustworthy
  import, package, or verification boundary.

## Phase 1 - Transport And Safety

### P1-001 - Shared Transport, Errors, Types, And Facade

- Dependency prerequisites: P0-001.
- Severity: `BLOCKING`
- Estimated complexity: `HIGH`
- Feature domain: client core
- Slice type: `CODE`
- External state change: `NONE`
- Verification level required: `local`
- Acceptance criteria: lifecycle, auth, encoding, safe retry, status mapping,
  charge denial, mutation denial, and shared resource ownership are tested.
- What could break if skipped: every resource would duplicate unsafe and
  inconsistent HTTP behavior.

## Phase 2 - Read And Preview Resources

### P2-001 - Accounts And Documents

- Dependencies: P1-001.
- Severity: `HIGH`
- Complexity: `LOW`
- Slice type: `CODE`
- External state change: `NONE` in secretless tests.
- Verification level required: `local`.

### P2-002 - Properties

- Dependencies: P1-001.
- Severity: `HIGH`
- Complexity: `HIGH`
- Slice type: `CODE`
- External state change: `NONE` in secretless tests.
- Verification level required: `local`.

### P2-003 - Persons And Suggestions

- Dependencies: P1-001.
- Severity: `HIGH`
- Complexity: `MEDIUM`
- Slice type: `CODE`
- External state change: `NONE` in secretless tests.
- Verification level required: `local`.

## Phase 3 - Persistent Resources

### P3-001 - Lists And List Items

- Dependencies: P1-001.
- Severity: `HIGH`
- Complexity: `MEDIUM`
- Slice type: `CODE`
- External state change: `NONE` in tests; wrapper exposes guarded mutations.
- Verification level required: `local`.

### P3-002 - Imports, Automations, And Integrations

- Dependencies: P1-001 and P3-001.
- Severity: `CRITICAL`
- Complexity: `HIGH`
- Slice type: `CODE`
- External state change: `NONE` in tests; wrapper exposes guarded mutation and
  billable fields.
- Verification level required: `local`.

## Phase 4 - Contract And User Documentation

### P4-001 - Complete Coverage And Strict Docs

- Dependencies: P2 and P3.
- Severity: `HIGH`
- Complexity: `MEDIUM`
- Slice type: `CODE`, `DOCS`
- External state change: official spec download only (`READ-ONLY`).
- Verification level required: `local`.

## Phase 5 - Delivery Automation

### P5-001 - CI, Pages, Dependabot, And Trusted Publishing

- Dependencies: P0 and P4.
- Severity: `HIGH`
- Complexity: `MEDIUM`
- Slice type: `AUTOMATION`, `CONFIG`
- External state change: `NONE` while files are authored.
- Verification level required: `local`, later `CI`.

## Phase 6 - Release Proof

### P6-001 - Verify The Local Release Candidate

- Dependencies: P1-P5.
- Severity: `BLOCKING`
- Complexity: `MEDIUM`
- Slice type: `CODE`, `CONFIG`, `DOCS`
- External state change: `NONE`
- Verification level required: `local`.

### P6-002 - Push And Monitor The Exact Revision

- Dependencies: P6-001.
- Severity: `HIGH`
- Complexity: `LOW`
- Slice type: `EXTERNAL-OPERATION`
- External state change: Git commit/push to the specified empty repository.
- Verification level required: `checked-in`, `CI`.

### P6-003 - Publish Version 0.1.0

- Dependencies: P6-001, P6-002, PyPI/trusted-publisher setup, exact release
  approval.
- Severity: `CRITICAL`
- Complexity: `MEDIUM`
- Slice type: `EXTERNAL-OPERATION`
- External state change: permanent PyPI version plus GitHub tag/release.
- Verification level required: `external outcome`.

### P6-004 - Optional Non-Billable Live Smoke

- Dependencies: licensed credential and explicit authorization.
- Severity: `OPTIONAL`
- Complexity: `LOW`
- Slice type: `EXTERNAL-OPERATION`
- External state change: read-only vendor request.
- Verification level required: `external outcome`.
