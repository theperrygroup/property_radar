# Development And Release

## Local gates

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

The tests use HTTPX mock transports and require no API credential. The endpoint
manifest is also checked against a local synthetic OpenAPI document.

## Contract drift

Run the opt-in live drift check against the official specification:

```bash
uv run property-radar-openapi-check
```

The scheduled GitHub workflow runs the same command. A contract change requires
reviewing request semantics and safety classifications, not only updating an
operation count.

## Release

Before tagging, run the live drift check above and review any vendor change.
The release workflow then accepts a stable semantic version tag whose version
exactly matches `pyproject.toml` and whose commit is contained in `main`. It
reruns deterministic repository gates, builds distributions once, and passes
those exact artifacts to PyPI and the GitHub release.

PyPI publishing uses OpenID Connect trusted publishing. The pending publisher
for `property-radar` is configured for GitHub owner `theperrygroup`, repository
`property_radar`, workflow `release.yml`, and environment `pypi`. The GitHub
environment accepts only `v*` tags.

Do not create the first tag until PropertyRadar or qualified legal review
confirms that publishing and distributing this unofficial client is compatible
with the applicable account agreement and trademark rights.
