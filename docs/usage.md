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
        property_persons_purchase_requested=False,
    )
```

Pass the `purchase` choice of the `persons()` call as
`property_persons_purchase_requested`. Like a transactions preview, a persons
preview can report a positive `resultCount` or `totalResultCount` without
returning people. With `property_persons_purchase_requested=False` the history
then has `current_owners=None` and `current_owners_withheld=True`: the owners
exist but were not returned. Counts that are all `0` give `current_owners=()`,
and an empty persons preview without any count fails closed with
`property_persons_preview_count_missing`. This preview rule mirrors the
transactions preview and has not been probed live. In every other case,
including `True` and the default `None`, each count that is present must equal
the number of returned people. The persons response may carry
`totalResultCount`, which must not be less than its `resultCount`.

`transaction_history()` checks the `property_persons` data completely before it
sends the transactions request, so invalid persons data never sends a request,
and never a billable one. The identity fields that `current_owners` carries
come from a paid persons call; see the [Django integration](#django-integration)
example.

`TRANSACTION_HISTORY_CONTRACT` binds the official API version, source
checksum, operation, filters, fields, response shapes, party and composition
sources, billing policy, provider limitations, and a stable contract
fingerprint. The history, records, current-owner parties, and billing evidence
are frozen and detached from caller-owned mappings.

Record values are text. The official contract declares the record fields as
strings, but live rows can send JSON numbers. Since `0.4.3` the parser gives
each value as exact text by the
[record value rule](historical-transactions.md#preserve-record-uncertainty)
that both record parsers share: `250000` gives `"250000"`, `80.25` gives
`"80.25"`, and a boolean gives `"1"` or `"0"`, but only in
`hasDocumentImage`, `isFirstCurrentOwnerRecord` and `isParentType`. A field
sent as `null` is left out of `returned_fields` and its attribute is `None`,
as for an absent field. `RecDate` must be a string; a `null`, a list or any
other type there fails with `record_field_type`, and so do a number or a
boolean in `Status`, NaN, infinities, `-0.0` and numbers of more than 64
characters, not counting the sign.

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

`history.billing.total_result_count` keeps the provider `totalResultCount` when
the response supplies it, and is `None` otherwise; `history.total_result_count`
then falls back to `result_count`. A preview (`purchase=False`) can report a
positive `resultCount` or `totalResultCount` with an empty `results` list: the
history then has no records and `records_withheld=True`. A purchased or
detached response still requires exactly `resultCount` rows. When the rows were
not withheld and `total_result_count` is greater than the number of returned
records, `history.truncated` is `True`: the history is partial, for example
because the provider limited the response to its documented default of 500
rows. `truncated` is a computed property, not a stored field.

`totalCost` can be a JSON integer, a finite JSON number or a decimal string,
and the cost is a `Decimal`. A JSON integer and a decimal string convert
exactly. JSON decoding gives a number with a fraction or an exponent to the
library as a float: the `Decimal` equals that number as written when it has at
most 15 significant digits, and a longer number can already be rounded before
the library sees it.

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
binds the exact paid criteria, the preview's `PropertyType` criterion, both
field catalogs (`BUYER_TRANSFER_PROPERTY_FIELDS` and
`BUYER_TRANSFER_PREVIEW_FIELDS`), limit, and offset without retaining a
separate buyer-name digest. The preview and the paid request for the same
criteria share one scope fingerprint.

Only a preview (`purchase=False`), recent or historical, adds the official
residential criterion
`{"name": "PropertyType", "value": [{"name": "PType", "value": ["SFR", "CND",
"MFR", "APT", "RES"]}]}` (`BUYER_TRANSFER_RESIDENTIAL_PTYPE_CODES`) just before
the RadarID criterion, which stays last. This criterion on `Purchase=0` follows
the official reference and has not been probed live. A preview's
`matched=False` therefore also covers a non-residential or `Unknown` transfer
that the provider dropped under the criterion. A paid request
(`purchase=True`) sends the `0.4.1` criteria list without the criterion, so it
still returns such a transfer and classifies it from the returned `PType`.
`build_buyer_transfer_match_criteria(criteria)` returns the paid list, and
`build_buyer_transfer_match_criteria(criteria, preview=True)` returns the
preview list; `preview` is keyword-only and must be exactly a boolean.

A preview (`purchase=False`) requests `Fields=RadarID` only
(`BUYER_TRANSFER_PREVIEW_FIELDS`), because PropertyRadar returns no record when
a preview asks for any paid field. Preview counts follow the provider:
`resultCount` counts purchased rows (`0` or the number of returned records) and
`totalResultCount` counts matches (`0` or `1`). A preview that reports one match
without the record fails closed with `preview_record_withheld`, and a preview
with more than one match fails with `total_result_count`. A zero-hit preview can
arrive as the bare envelope `{"results": []}`; it parses as no match with zero
counts, zero cost and `billing.provider_metadata_omitted=True`. Paid and
detached responses keep the strict rule that `resultCount`, the number of
records and `totalResultCount` are equal. `totalCost` can be a JSON integer, a
finite JSON number or a decimal string, and parses to a `Decimal` by the rules
given for transaction history above.

Set `most_recent_change_of_ownership_only=True` only when the search should be
limited to the most recent ownership-changing transfer. Despite the provider's
technical criterion name, PropertyRadar documents that this transfer may be
either Market or Non-Market.

When present, `result.linkage.property` exposes the exact RadarID, broad
`PType`, address, city, state, ZIP integer, county, FIPS, APN, and `Decimal`
coordinates. Missing optional fields stay unavailable and provider strings are
not trimmed or synthesized. Returned FIPS must identify the requested county.
A preview record carries only the RadarID, so its other fields are `None`.

`is_residential` and `residential_basis` explain the classification, which
depends on the request mode:

- Preview (`purchase_requested=False`). A record without a returned `PType`
  (every preview, because a preview requests only `RadarID`) is residential by
  the criterion: `is_residential=True` and
  `residential_basis="property_type_criterion"`. A returned `PType` gives
  `residential_basis="property_type"` and must be one of the five residential
  display names (Single Family, Condominium, Multi-Family 2-4, Multi-Family 5+,
  Other Res.); any other documented type, `Unknown` included, fails closed with
  `property_type_outside_criterion`.
- Paid or detached (`purchase_requested=True` or `None`). The parse classifies
  from the returned `PType` as `0.4.1` did and never fails because of the type:
  `residential_basis="property_type"`, and `is_residential` is `True` for the
  five residential types, `False` for the other documented types and `None`
  for `Unknown`. A record without `PType` has `residential_basis=None` and
  `is_residential=None`.

A directly constructed property keeps `residential_basis=None` and the `0.4.1`
classification.

Both buyer-transfer parsers validate the envelope, the counts and `totalCost`
before the returned record. When they reject the record after that point, they
raise `BuyerTransferResponseError`, a subclass of `InvalidResponseError`. Its
`billing_evidence` is the validated `BuyerTransferBillingEvidence`, so a
rejected paid record keeps the cost and counts of the charged request. The
message holds only the reason code. Persist that evidence and treat the
purchase outcome as unknown; the error is not permission to retry. A rejection
before the billing evidence exists stays a plain `InvalidResponseError`.

The linkage relationship is
`provider_buyer_criterion_property_match`: PropertyRadar returned the property
for its Buyer Name (Grantee) criterion. The matching transaction/document,
structured grantees, and exact/fuzzy name-match behavior are unavailable. This
surface supports geographic attribution and caller review; it cannot alone
confirm a recorded grantee or verified purchase.

#### Historical recording dates

For a historical query, use `historical_buyer_transfer_match()` with an
explicit `BuyerTransferRecordingDateRange` and `publication_window=None`.
This selects recording dates without the recent publication filter:

```python
from datetime import date

from property_radar import (
    BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT,
    BuyerTransferMatchCriteria,
    BuyerTransferRecordingDateRange,
    HistoricalBuyerTransferMatchResult,
    PropertyRadarClient,
)

historical_query = BuyerTransferMatchCriteria(
    buyer_name="Synthetic Buyer",
    radar_id="P-SYNTHETIC",
    state_code="UT",
    county_fips="49035",
    publication_window=None,
    recording_date_range=BuyerTransferRecordingDateRange(
        start=date(2024, 7, 1),
        end=date(2024, 7, 31),
    ),
)

with PropertyRadarClient() as client:
    result: HistoricalBuyerTransferMatchResult = (
        client.properties.historical_buyer_transfer_match(
            criteria=historical_query,
            purchase=False,
        )
    )

assert (
    result.contract_fingerprint
    == (BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT["contract_fingerprint"])
)
```

`start` and `end` must be exact, finite `datetime.date` values, with
`start <= end`. Both dates are inclusive, and ranges may span multiple years.
No provider maximum span is documented; any narrower limit belongs to the
caller's authorization policy. A historical range cannot be combined with the
relative `recording_window` or a non-`None` `publication_window`.

`BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT` version 1 binds separate official
API `5.3.1.0` provenance. Historical scope fingerprints seal the mode, contract
fingerprint, and exact recording-date range as well as the paid request
criteria, the preview's `PropertyType` criterion, both field catalogs, limit,
and offset. The historical method follows the same rules as the recent one:
`Fields=RadarID` only and the `PropertyType` criterion on previews only,
provider preview counts, the bare zero-hit envelope, the classification by
request mode with `residential_basis`, and `BuyerTransferResponseError` for a
record rejected after billing. For a detached response envelope, use
`parse_historical_buyer_transfer_match`; it reports the historical contract
fingerprint and returns `HistoricalBuyerTransferMatchResult`.

The new `HistoricalBuyerTransferMatchResult`,
`HistoricalBuyerTransferLinkage`, and `HistoricalBuyerTransferProperty` types
expose the same attributes as their recent-query counterparts except that
historical `zip_five` is `str | None`. A supplied ZIP must contain exactly five
digits and is preserved unchanged, including leading zeros such as `"01234"`.
The historical parser validates known optional envelope metadata and discards
it; the typed result retains no raw response. Historical calls request at most
one result, reject counts greater than one, and never paginate.

The recent-query method `buyer_transfer_match()` and
`parse_buyer_transfer_match` keep their API `5.2.0.0` signatures, and their
types keep every `0.4.1` attribute. `0.4.2` adds the keyword-only `preview`
parameter of `build_buyer_transfer_match_criteria()` and the last fields
`residential_basis` and `provider_metadata_omitted`. New fields take part in
equality, hashing and `repr`, so a parsed property differs from one built by
hand without them, and objects built or pickled under `0.4.1` are not
supported. Both buyer-transfer contracts record the rules above, so
`BUYER_TRANSFER_MATCH_CONTRACT` and `BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT`
have new contract fingerprints; callers that pin a fingerprint must update it.

A recording date is the document's recording date, not the transaction's
closing date. Historical results retain the same property-level Buyer
criterion relationship: they do not identify the matching document, provide
structured grantees, or automatically verify a purchase. The no-charge controls
are unchanged; the example explicitly requests `purchase=False`.

### Django integration

Keep provider access in a service module and import only public
`property_radar` symbols. This example purchases the identity fields, so both
requests are billable: they need `allow_charges=True` on the client and
`purchase=True` on each call, and the library never retries them. Run it only
after the preview and the application's own approval, budget and purchase-claim
checks:

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
        allow_charges=True,
    ) as client:
        persons = client.properties.persons(
            radar_id,
            fields=PROPERTY_PERSON_IDENTITY_FIELDS,
            purchase=True,
        )
        return client.properties.transaction_history(
            radar_id,
            filter_by="CurrentOwner",
            purchase=True,
            property_persons=persons,
            property_persons_purchase_requested=True,
        )
```

With `property_persons_purchase_requested=True`, every persons count that is
present must equal the number of returned people, and the history's billing
status is `charged`. If the persons data fails its checks, the method raises
`InvalidResponseError` before it sends the paid transactions request; the
persons call was already billed.

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
