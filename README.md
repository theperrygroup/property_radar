# Property Radar Python Client

[![CI](https://github.com/theperrygroup/property_radar/actions/workflows/ci.yml/badge.svg)](https://github.com/theperrygroup/property_radar/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/property-radar.svg)](https://pypi.org/project/property-radar/)
[![Python](https://img.shields.io/pypi/pyversions/property-radar.svg)](https://pypi.org/project/property-radar/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An unofficial, typed Python client for the
[PropertyRadar API](https://developers.propertyradar.com/api).

> [!IMPORTANT]
> PropertyRadar documents its API for end users and restricts how its data may
> be used or redistributed. This library is not affiliated with or endorsed by
> PropertyRadar. Review the vendor terms and obtain any needed partner approval
> before using it in a product for third parties.

## Status

The `0.1.0` implementation covers all 37 operations in the official API
`5.1.1.0` contract. The PyPI Trusted Publisher is configured. Public release
remains gated by vendor or qualified legal confirmation that distributing this
unofficial SDK is compatible with the applicable PropertyRadar agreement and
trademark rights.

## Installation

```bash
pip install property-radar
```

## Safe Quickstart

```python
from property_radar import PropertyRadarClient

criteria = [{"name": "RadarID", "value": ["P0000000"]}]

with PropertyRadarClient(api_key="your-api-key") as client:  # pragma: allowlist secret
    preview = client.properties.search(criteria=criteria)
```

Preview-capable endpoints send `Purchase=0` by default. Persistent list,
import, automation, and webhook operations require `allow_mutations=True`.
Paid requests require both `allow_charges=True` on the client and
`purchase=True` on the method call.

## Authentication

Pass the token explicitly or set `PROPERTY_RADAR_API_KEY`. The library does not
load `.env` files and never needs an API credential for its test suite.

## Development

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

See [CONTRIBUTING.md](CONTRIBUTING.md) and the
[implementation planning tree](docs/planning/property-radar-python-client/README.md).

## License

This client is licensed under the MIT License. PropertyRadar data and service
access remain governed by PropertyRadar's own agreements.
