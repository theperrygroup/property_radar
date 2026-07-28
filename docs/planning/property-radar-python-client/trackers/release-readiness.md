# Release Readiness

Snapshot date: `2026-07-28`

## Readiness Matrix

| Surface | Required proof | Current state |
| --- | --- | --- |
| Package metadata | Valid PEP 621 metadata and one version source | `Verified locally for final 0.1.0 candidate` |
| Source distribution | Builds and contains intended files only | `Verified: 25 files, Twine pass, no tests/.env/.codex` |
| Wheel | Builds, contains `py.typed`, installs cleanly, imports | `Verified: 24 files, clean Python 3.14 install, pip check, version/manifest smoke` |
| Formatting/lint | Ruff hard gate after final edit | `Verified locally after final code edit` |
| Typing | Strict mypy hard gate after final edit | `Verified locally for 33 source files` |
| Unit/contract tests | Secretless pass with enforced honest coverage | `155 passed at 99.11% on Python 3.13; also passed on 3.10 and 3.14` |
| Secret/personal-data scan | No credential, token, webhook secret, or real payload | `Zero detect-secrets findings; .env ignored; no live payload persisted` |
| User docs | MkDocs strict build | `Verified locally after final docs edit` |
| Endpoint contract | 37/37 wrapper mappings and zero drift at snapshot | `Verified against official JSON spec` |
| CI workflow | Exact GitHub revision reaches terminal success | `Implemented/actionlint clean; push proof pending` |
| Docs deployment | Exact revision deployed by Pages | `Workflow implemented; Pages enablement/deploy proof pending` |
| GitHub release | Exact tag/revision and artifact hashes | `Blocked by implementation and release choice` |
| PyPI name/ownership | Exact `property-radar` project controlled by publisher | `Unclaimed/unknown; 404 at snapshot` |
| Trusted publisher | Exact owner/repo/workflow/environment tuple configured | `Blocked by external setup` |
| PyPI version | Exact wheel/sdist and hashes visible, non-yanked | `Not published` |
| Live vendor smoke | Authorized non-billable request with sanitized readback | `Passed: status-label GET, list count 10, no payload disclosure` |

## Release Safety Rules

- A tag must match `vX.Y.Z`, built metadata, and an exact CI-green `main`
  revision.
- Build once and publish the same downloaded artifacts to PyPI and GitHub.
- Grant `id-token: write` only to the PyPI publishing job and
  `contents: write` only to the GitHub release job.
- Do not configure or use a long-lived PyPI password.
- Do not run live PropertyRadar integration tests in CI or release.
- Do not publish until the API terms/public-SDK suitability question is
  explicitly resolved.
- If PyPI succeeds and GitHub Release fails, do not re-upload the immutable PyPI
  version; reconcile the GitHub release from the existing exact artifacts.

## Current Conclusion

The repository is a verified local release candidate. Checked-in GitHub,
CI/CodeQL, Pages, and public package proof remain distinct pending steps.
Public publication is also gated by external PyPI configuration and
vendor/account-agreement confirmation.
