# Property Radar Python Client

[![CI](https://github.com/theperrygroup/property_radar/actions/workflows/ci.yml/badge.svg)](https://github.com/theperrygroup/property_radar/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/property-radar.svg)](https://pypi.org/project/property-radar/)
[![Python](https://img.shields.io/pypi/pyversions/property-radar.svg)](https://pypi.org/project/property-radar/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/theperrygroup/property_radar/blob/main/LICENSE)

An unofficial, typed Python client for the
[PropertyRadar API](https://developers.propertyradar.com/api).

> **Important:** PropertyRadar documents its API for end users and restricts
> how its data may be used or redistributed. This library is not affiliated
> with or endorsed by PropertyRadar. Review the vendor terms and obtain any
> needed partner approval before using it in a product for third parties.

## Status

Version `0.1.0` covers all 37 operations in the official API `5.1.1.0`
contract. Releases are built once and published through the configured PyPI
Trusted Publisher.

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

See
[CONTRIBUTING.md](https://github.com/theperrygroup/property_radar/blob/main/CONTRIBUTING.md)
and the
[development guide](https://theperrygroup.github.io/property_radar/development/).

## License

This client is licensed under the MIT License. PropertyRadar data and service
access remain governed by PropertyRadar's own agreements.
