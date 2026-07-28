# Property Radar Repository Rules

These rules apply to the entire repository.

## Project Shape

- Distribution name: `property-radar`.
- Import package: `property_radar`.
- Runtime source belongs under `src/property_radar/`.
- Unit and contract tests belong under `tests/`.
- User documentation belongs under `docs/`.
- Planning truth belongs under
  `docs/planning/property-radar-python-client/`.

## Commands

Use the project environment and run all relevant gates after the last edit:

```bash
uv sync --all-extras --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv run mkdocs build --strict --clean
uv build
uv run twine check dist/*
```

Run focused tests first while iterating, then the full set before a release
claim.

## Safety And Data

- Never commit PropertyRadar API keys, webhook secrets, tokens, licensed
  payloads, or real personal/property response data.
- Unit and contract tests must remain secretless and synthetic.
- Never make a live PropertyRadar call unless the exact account, target,
  non-billable behavior, and authorization are explicit.
- `Purchase=1` behavior must remain deny-by-default and must never be retried
  automatically.
- Persistent list, import, automation, and webhook changes must remain
  deny-by-default.
- Treat vendor docs and local fixtures as contract evidence, not proof of a
  live account outcome.

## Git And Release

- Preserve unrelated and pre-existing work, including local `.codex/` files.
- Do not stage local-only files unless the task explicitly owns them.
- Do not force-push or bypass required checks.
- Build release artifacts once and reuse the exact files for PyPI and GitHub.
- PyPI publication requires Trusted Publishing and authoritative post-publish
  verification.
