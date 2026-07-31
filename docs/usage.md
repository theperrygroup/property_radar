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

### Typed transaction history

The raw `properties.transactions()` method remains unchanged. Use the additive
typed convenience when the exact request context is available:

```python
from property_radar import (
    PROPERTY_PERSON_IDENTITY_FIELDS,
    PropertyRadarClient,
)

with PropertyRadarClient() as client:
    persons = client.properties.persons(
        "P-SYNTHETIC",
        fields=PROPERTY_PERSON_IDENTITY_FIELDS,
        purchase=False,
    )
    history = client.properties.transaction_history(
        "P-SYNTHETIC",
        filter_by="CurrentOwner",
        purchase=False,
        property_persons=persons,
    )
```

`TRANSACTION_HISTORY_CONTRACT` binds the official API version, source
checksum, operation, filters, fields, response shapes, party and composition
sources, billing policy, provider limitations, and a stable contract
fingerprint. The history, records, current-owner parties, and billing evidence
are frozen and detached from caller-owned mappings.

The official contract defines `Grantor` and `Grantee` as scalar display
strings. `grantor_display` and `grantee_display` preserve each whole value;
`grantors` and `grantees` remain `None` because the provider does not expose
party boundaries. The parser never splits punctuation or synthesizes name
components.

The dedicated property-person response is the provider-supported structured
source. `history.current_owners` preserves response order and can contain
people, organizations, and unknown identities with:

- provider `EntityName` as `display_name` when supplied;
- `first_name`, `middle_name`, `last_name`, and `suffix`;
- `PersonKey` as `provider_id`;
- exact `PersonType` and `OwnershipRole`;
- `aliases=None`, because the current provider contract has no alias field.

These are current-owner identities for the property, not asserted members of a
particular transaction's scalar Grantee display. PropertyRadar documents no
person-to-document link, and `isFirstCurrentOwnerRecord` has no documented
truth encoding. Consumers must keep that evidentiary distinction.

`history.billing` records the known request flag, `preview`, `charged`, or
`unknown` status, exact `Decimal` cost, preview-only free quantity, result
count, and a sanitized request ID when an official success source exists.
Currency is currently `None`; the API documents no currency. Parsing a
detached raw envelope without `purchase_requested=` produces `unknown` rather
than guessing from cost or free quantity.

### Typed buyer-transfer property match

Use the exact-target convenience when an application already has one previewed
RadarID and needs typed property/location evidence for the same bounded Buyer
query:

```python
from property_radar import BuyerTransferMatchCriteria, PropertyRadarClient

query = BuyerTransferMatchCriteria(
    buyer_name="Synthetic Buyer",
    radar_id="P-SYNTHETIC",
    state_code="UT",
    county_fips="49035",
    publication_window="Last 7 Days",
    recording_window="Last 30 Days",
)

with PropertyRadarClient() as client:
    result = client.properties.buyer_transfer_match(
        criteria=query,
        purchase=False,
    )
```

`BUYER_TRANSFER_MATCH_CONTRACT` binds the official source, documented Buyer
criterion semantics, fixed criteria/fields, zero-or-one cardinality, parser,
billing rules, and provider limitations. The per-request scope fingerprint
binds the exact criteria, field catalog, limit, and offset without retaining a
separate buyer-name digest.

Set `most_recent_change_of_ownership_only=True` only when the search should be
limited to the most recent ownership-changing transfer. Despite the provider's
technical criterion name, PropertyRadar documents that this transfer may be
either Market or Non-Market.

When present, `result.linkage.property` exposes the exact RadarID, broad
`PType`, address, city, state, ZIP integer, county, FIPS, APN, and `Decimal`
coordinates. Missing optional fields stay unavailable and provider strings are
not trimmed or synthesized. Returned FIPS must identify the requested county.

The linkage relationship is
`provider_buyer_criterion_property_match`: PropertyRadar returned the property
for its Buyer Name (Grantee) criterion. The matching transaction/document,
structured grantees, and exact/fuzzy name-match behavior are unavailable. This
surface supports geographic attribution and caller review; it cannot alone
confirm a recorded grantee or verified purchase.

### Django integration

Keep provider access in a service module and import only public
`property_radar` symbols:

```python
from django.conf import settings
from property_radar import (
    PROPERTY_PERSON_IDENTITY_FIELDS,
    PropertyRadarClient,
    TransactionHistory,
)


def purchaser_identity_evidence(radar_id: str) -> TransactionHistory:
    with PropertyRadarClient(
        api_key=settings.PROPERTY_RADAR_API_KEY,
    ) as client:
        persons = client.properties.persons(
            radar_id,
            fields=PROPERTY_PERSON_IDENTITY_FIELDS,
            purchase=False,
        )
        return client.properties.transaction_history(
            radar_id,
            filter_by="CurrentOwner",
            purchase=False,
            property_persons=persons,
        )
```

The Django application can compare its lead fields with the provider-supplied
components in `history.current_owners`. It should not parse
`record.grantee_display`, invent aliases, or infer that a current owner maps to
one particular displayed grantee without separate evidence.

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
