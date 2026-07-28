# Contributing

## Setup

```bash
git clone https://github.com/theperrygroup/property_radar.git
cd property_radar
uv sync --all-extras --locked
```

## Working Agreement

- Add type hints and Google-style docstrings to public APIs.
- Keep transport behavior centralized.
- Use synthetic request and response data.
- Add tests for new branches, error handling, query/body encoding, mutation
  denial, and charge denial.
- Update the endpoint manifest and user docs when an API method changes.
- Never add a live credential requirement to unit or contract tests.

## Required Checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv run mkdocs build --strict --clean
uv build
uv run twine check dist/*
```

## Releases

Releases use a `vX.Y.Z` tag, a single built artifact set, PyPI Trusted
Publishing, and a separate GitHub Release job. Do not upload a locally rebuilt
artifact under an existing version.
