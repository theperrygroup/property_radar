# Getting Started

## Install

```bash
pip install property-radar
```

## Authenticate

Pass an API key to the client or set `PROPERTY_RADAR_API_KEY`. The explicit
constructor value takes precedence.

```python
from property_radar import PropertyRadarClient

with PropertyRadarClient(api_key="your-api-key") as client:  # pragma: allowlist secret
    preview = client.properties.get("P0000000")
```

The test suite does not require a credential.

## Preview Before Purchase

Methods with a PropertyRadar `Purchase` parameter send `Purchase=0` unless you
explicitly request and enable charges. Preview responses can report counts and
costs without returning paid fields.
