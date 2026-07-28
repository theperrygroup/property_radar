# Authentication

PropertyRadar uses bearer-token authentication. Supply a token directly,
through an environment variable, or with a callback that can refresh it.

## Environment variable

```bash
export PROPERTY_RADAR_API_KEY="replace-with-your-token"  # pragma: allowlist secret
```

```python
from property_radar import PropertyRadarClient

with PropertyRadarClient() as client:
    statuses = client.accounts.status_labels()
```

`PROPERTYRADAR_API_KEY` is accepted as a legacy fallback. The library does not
read `.env` files itself. For a local checkout using uv, you can opt in:

```bash
uv run --env-file .env python your_script.py
```

## Explicit token

```python
from property_radar import PropertyRadarClient

client = PropertyRadarClient(
    api_key="replace-with-your-token"  # pragma: allowlist secret
)
```

An explicit token takes precedence over environment variables. Client and
transport representations never include the token.

## Refresh callback

```python
from property_radar import PropertyRadarClient


def current_token() -> str:
    return credential_store.fetch_propertyradar_token()


with PropertyRadarClient(token_provider=current_token) as client:
    members = client.accounts.members()
```

Do not pass both `api_key` and `token_provider`.

## Credential hygiene

- Keep `.env` and downloaded API data out of version control.
- Give CI only the credentials required by explicit live-test jobs.
- Do not put tokens in exception messages, logs, URLs, examples, or fixtures.
- Rotate a token immediately if it is committed or otherwise exposed.
