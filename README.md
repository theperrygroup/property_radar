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

Version `0.3.0` covers all 37 operations in official API `5.2.0.0`. It adds
immutable, fingerprinted contracts for strict transaction history and for an
exact-target Buyer-criterion property/location match. Releases are built once
and published through the configured PyPI Trusted Publisher.

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

## Typed Transaction Evidence

`client.properties.transactions()` remains the raw, backward-compatible
envelope method. Version `0.2.0` adds
`client.properties.transaction_history()` for immutable records and typed
billing evidence.

The provider documents transaction `Grantor` and `Grantee` as scalar display
strings, so the library preserves each whole value and reports party boundaries
as unknown. Structured current-owner identities can be composed from the
dedicated property-persons endpoint with
`PROPERTY_PERSON_IDENTITY_FIELDS`; they remain separate from any unsupported
person-to-transaction linkage.

## Typed Buyer-Transfer Location Evidence

`client.properties.buyer_transfer_match()` builds a fixed
`POST /v1/properties` query with PropertyRadar's documented Buyer Name
(Grantee) criterion, an exact RadarID, bounded geography/windows, one-result
limit, and typed property/location fields. Its scope fingerprint binds the
exact criteria, field catalog, limit, and offset; paid use remains dual opt-in
and single-attempt, with malformed purchase flags rejected before network I/O.

The result proves only that the provider returned that property for the Buyer
criterion. It does not expose the matching document, structured grantees, or
exact/fuzzy name-match semantics, so it cannot by itself confirm a recorded
grantee or verified purchase.

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
