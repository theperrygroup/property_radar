# Requests And Responses

## Resource facade

One `PropertyRadarClient` owns a shared HTTP connection pool. Its resource
objects are created lazily:

```python
from property_radar import PropertyRadarClient

with PropertyRadarClient() as client:
    preview = client.properties.search(
        criteria=[{"name": "City", "value": ["Denver"]}],
        limit=25,
    )
```

The resources are `accounts`, `automations`, `documents`, `imports`,
`integrations`, `lists`, `persons`, `properties`, and `suggestions`.

## Response envelopes

Methods return the vendor JSON object without inventing model fields.
Documented common keys include:

- `results`
- `resultCount`
- `totalResultCount`
- `totalCost`
- `quantityFreeRemaining`
- `updateCount`
- `deleteCount`

The API contract evolves independently of this package, so code should use
optional access for envelope fields:

```python
cost = preview.get("totalCost")
count = preview.get("resultCount", 0)
```

`accounts.status_labels()` has a dedicated response type because `menu`
returns a list, `edit` returns an object, and `compact` returns a
comma-delimited string.

## Criteria

Criteria preserve the PropertyRadar object shape and criterion-specific value:

```python
criteria = [
    {"name": "City", "value": ["Denver"]},
    {"name": "Beds", "value": [3, 4]},
]
```

Consult the official criteria catalog for supported names and values. The
client intentionally does not hard-code that fast-changing catalog.

## Pagination

Methods expose the vendor's `limit` and `start` controls where documented.
Property searches also provide `iter_search()`, which advances through pages
and yields individual result objects:

```python
with PropertyRadarClient() as client:
    for property_record in client.properties.iter_search(
        criteria=[{"name": "City", "value": ["Denver"]}],
        page_size=100,
        max_results=250,
    ):
        process(property_record)
```

Set a deliberate `max_results` for production jobs. The API reference does not
publish a universal numeric rate limit, so callers should also budget time,
cost, and downstream storage.

The iterator defaults to at most 500 records. `max_results=None` explicitly
requests unbounded preview iteration and is rejected when `purchase=True`.

## Query serialization

Public method names and arguments are Pythonic; outgoing JSON and query keys
preserve vendor casing. Fields and enumerated list parameters use the
comma-delimited encoding declared by the OpenAPI contract. The few filters
declared as repeated query parameters remain repeated.
