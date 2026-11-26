# Bounded historical transaction quotes and results

`property_radar.historical_transaction` defines a separate contract for the
reviewed PropertyRadar API **5.3.1.0**. It leaves the existing 0.2/0.3
transaction models and fields unchanged, and its contract stays separate from
theirs. In 0.4.2 both transaction contracts record new response rules (a
JSON-number `totalCost`, and for transaction history the preview
`totalResultCount`, withheld rows, the computed `truncated` flag and withheld
persons-preview owners). In 0.4.3 both record parsers share one record-value
rule, which gives JSON numbers and flag booleans as text and a `null` outside
`RecDate` as a missing field (see
[Preserve record uncertainty](#preserve-record-uncertainty)), and both
contracts record it. Each of these releases gives
`HISTORICAL_TRANSACTION_CONTRACT` and `TRANSACTION_HISTORY_CONTRACT` new
fingerprints. The module only validates inputs and parses supplied data; it
makes no network calls and authorizes no charges.

## Query one bounded selection

```python
from datetime import date

from property_radar.historical_transaction import (
    HistoricalTransactionDateRange,
    HistoricalTransactionQuery,
)

query = HistoricalTransactionQuery(
    radar_id="SYNTHETIC-PROPERTY",
    recording_dates=HistoricalTransactionDateRange(
        start=date(2024, 1, 1),
        end=date(2024, 12, 31),
    ),
    limit=100,
    filter="All",
    doc_groups=("Deed",),
    doc_types=("GRT", "WRT"),
)
preview_parameters = query.params(purchase=False)
```

The start and end must be exact `date` values, in order. They are serialized as
one documented `from: MM/DD/YYYY to: MM/DD/YYYY` expression. The provider does not
specify whether boundary dates are inclusive. Relative periods and an unbounded
request are not supported by this interface.

`limit` is required and must be an exact integer from 1 through 500. This is a
**local safety cap**: the provider documents a default of 500, not a maximum.
The typed `transaction_history()` convenience sends no `Limit`, so that
default applies to it; its `TransactionHistory.truncated` is `True` when a
response that did not withhold its rows returned fewer than its
`totalResultCount`.
`Filter` may be `All` or `CurrentOwner`. Optional document types and groups must
be immutable, duplicate-free tuples. Document groups use the seven documented
values; document types use raw uppercase three-letter codes. Filters apply
before counting, limiting, and billing. The provider defines document groups as
OR within the group axis and AND across filter axes. Row order is not promised.

The explicit field list is the old Standard set plus `RadarID`, `DocType`, and
`DocGroup`. This bounded interface does not support arbitrary fields or
`DocumentID` lookup, because that lookup bypasses `Limit`.

`query.scope_fingerprint` binds the versioned contract, property, exact encoded
date range, filter values and ordering, field list, and limit. It intentionally
excludes `Purchase`, so the quote and paid request share a scope. The fingerprint
is caller-supplied request context, not a provider echo or proof that two calls
saw an unchanged dataset. Do not log it or use it as an authorization token.

## Quote and paid result are different types

```python
from property_radar.historical_transaction import (
    parse_historical_transaction_quote,
    parse_historical_transaction_result,
)

# Wholly synthetic supplied response; the parser performs no request.
quote = parse_historical_transaction_quote(
    {"resultCount": 2, "totalResultCount": 8, "totalCost": "0.0250"},
    query=HistoricalTransactionQuery(
        radar_id="SYNTHETIC-PROPERTY",
        recording_dates=query.recording_dates,
        limit=2,
    ),
)
assert quote.result_count == 2
assert quote.total_result_count == 8
assert quote.truncated
assert quote.billing_status == "preview"
```

A `HistoricalTransactionQuote` accepts omitted `results`, or an empty list as a
compatibility tolerance. Nonempty preview rows are rejected. A quote can have a
positive selected count and estimated cost while returning no rows. It is
never a paid result.

A `HistoricalTransactionResult` requires an explicit `results` list with exactly
`resultCount` rows. Both types require `resultCount`, `totalResultCount`, and
`totalCost`, although the provider schema does not declare them required. Their
absence is an error, never an empty or free result. Counts must be exact
nonnegative integers; booleans, strings, floats, and contradictory counts fail.
The local completeness policy requires
`resultCount == min(query.limit, totalResultCount)`. A truncated result is complete
only for its bounded selection, not for all historical transactions.

Paid responses reject preview-only `quantityFreeRemaining`. Quotes preserve
that count when supplied and otherwise expose `None`. Parsed costs are
nonnegative `Decimal` values. `totalCost` can be a JSON integer of at most 64
digits, a finite JSON number whose plain decimal form has at most 64
characters, or an ASCII decimal string of at most 64 characters (`0`, `0.5` and
`"3.50"` give `Decimal("0")`, `Decimal("0.5")` and `Decimal("3.50")`).
Booleans, `null`, NaN, infinities, negative values, `-0.0` and all other types
fail. No fixed cents scale, rounding, string coercion, or currency is invented.
A JSON integer and a decimal string convert exactly. A JSON number with a
fraction or an exponent reaches the library as a float and converts from its
shortest decimal form: the `Decimal` equals the number as written when it has
at most 15 significant digits, and a longer number can already be rounded by
JSON decoding before the library sees it.
Zero selected rows require zero cost under this per-returned-record contract;
a nonempty selection may still be free under the account's terms.

Choose the parser using the **known request mode**. The response does not echo
`Purchase`; these functions cannot verify how a caller obtained a body. Calling
the paid parser does not authorize spending. Before a paid request, the caller
must independently enforce approved scope, account identity, budget, durable
purchase claim, and the transport's charge opt-in. A quote is not a price lock,
and the parser cannot prevent a higher returned cost after a request has
already been charged. No automatic retries are provided by this module.

## Preserve billing evidence after a rejected response

Contract version **1.1** adds `HistoricalTransactionResponseError`, a subclass of
`InvalidResponseError`. Both parsers raise this error when response validation
fails. Its `billing_evidence` is an immutable
`HistoricalTransactionBillingEvidence` snapshot captured from the same envelope
before validating rows or count completeness. It contains:

- The caller-known `purchase_requested` mode and `scope_fingerprint`.
- `total_cost`, `result_count`, and `total_result_count`, each independently
  validated and nullable. Invalid or absent fields remain `None`.
- `currency=None`, because the provider does not document currency.

For example, a paid response with `totalCost="1.2500"`, selected count 2, total
count 8, and only one returned row is rejected. The error still exposes
`Decimal("1.2500")`, 2, and 8. If the cost is malformed but the counts are valid,
the error exposes `total_cost=None` and preserves those counts. Conflicting
counts do not erase an independently valid cost. A response that cannot be
snapshotted safely exposes unknown metadata rather than fabricating values.

Persist each known billing field even when the paid result is rejected, and
mark the transaction outcome unknown. The snapshot is not a complete result,
a provider settlement receipt, or permission to retry. In particular, do not
replace its known cost with zero or discard it because the rows are incomplete.
Errors retain no raw envelope, row, or party attributes and have no chained
exception context. The library raises the error after dropping input locals,
so its own traceback frames retain no raw response or query. A caller's own
frames remain the caller's responsibility. Error and snapshot representations
omit query identifiers, fingerprints, and record values.

## Preserve record uncertainty

Rows expose immutable `fields` plus typed accessors for document/property IDs,
document type and group, modification status, amount display, grantor/grantee
displays, and recording-date evidence. `missing_fields` lists requested fields
that were not returned; missing values are not fabricated. A row may be
structurally valid while lacking evidence needed for attribution. Duplicate
nonempty document identifiers and returned property IDs that contradict the
query are rejected.

Record values in `fields` are text. PropertyRadar's published spec declares
these record fields as strings, but live rows send JSON numbers and may send
booleans or `null`. After the undocumented-field check, each value is handled
as follows:

- A string is kept exactly.
- A JSON integer whose absolute value has at most 64 digits becomes its
  decimal text, so `250000` gives `"250000"` and `-5` gives `"-5"`.
- A finite JSON number with a fraction or an exponent becomes the plain
  decimal form of its shortest representation, without an exponent or
  rounding: `80.0` gives `"80.0"`, `80.25` gives `"80.25"`, `1e16` gives
  `"10000000000000000"` and `1e-7` gives `"0.0000001"`. That form may have at
  most 64 characters, not counting the sign.
- A boolean becomes `"1"` for `true` and `"0"` for `false`, but only in
  `hasDocumentImage`, `isFirstCurrentOwnerRecord` and `isParentType`. The
  library does not interpret flag text.
- A `null` in any field other than `RecDate` leaves that field out of
  `fields`. `missing_fields` then lists it, and a typed accessor for it
  returns `None`, exactly as for an absent field.

`Status` and `DocGroup` accept only a string or `null`, and their enum checks
then apply. NaN, infinities, `-0.0`, an integer with more than 64 digits, a
float whose plain form has more than 64 characters, a boolean in any other
field, a number in `Status`, `DocGroup` or `RecDate`, objects, arrays outside
`RecDate`, and all other types fail with `record_field_type`. The older
`parse_transaction_history()` applies the same rule to its records, except
that its `RecDate` must be a string.

The current response schema describes `RecDate` as an array of RelativeDate
filter expressions. No scalar response example was found in the reviewed
current schema or endpoint documentation. The existing library's scalar
fixtures are synthetic and do not prove an old-versus-new provider delta.
Accordingly:

- A string is preserved exactly in `recording_date`, with status
  `scalar_unverified`. It is not parsed or asserted to be a valid calendar date.
- An array of strings is frozen into `unverified_recording_dates`, with status
  `ambiguous_array`; `recording_date` remains `None`. Even a one-element date-like
  array is never collapsed into a date. An empty array remains distinguishable
  from missing data.
- An absent field has status `missing`. A `null` `RecDate` still fails
  validation, although a `null` in any other field reads as missing. Numbers,
  booleans, nested arrays, and non-string members fail validation too.

`Grantor` and `Grantee` remain opaque displays. The parser does not split names,
attach current owners, associate a buyer-search match with a document, select a
unique transfer, or make an attribution decision. Such evidence needs explicit
review. Routine representations and validation messages omit row values,
identifiers, dates, and query fingerprints; do not log `fields` or payloads.

## Reviewed provenance

The unauthenticated [public schema](https://developers.propertyradar.com/_spec/api.json)
and [endpoint documentation](https://developers.propertyradar.com/api/properties/get/properties/radarid/transactions)
were inspected on 2026-11-03. The exact schema SHA-256 is
`9feadf6a8fade0530045f4d6f14db69f520144078a71637ef6c999aea8493c14`.
The [changelog](https://developers.propertyradar.com/changelog) also describes
filtering before counts, limits, and billing. `HISTORICAL_TRANSACTION_CONTRACT`
records this provenance and the stricter local policies; its fingerprint is
independent from every prior contract.

Validation uses synthetic fixtures only. No authenticated provider request or
live billing outcome is established by those tests or the public schema.
