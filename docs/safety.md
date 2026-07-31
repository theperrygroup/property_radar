# Safety And Data

## Paid Requests

Paid requests require two independent choices:

1. Construct the client with `allow_charges=True`.
2. Pass `purchase=True` to the specific method.

`allow_charges` and `allow_mutations` must be exact booleans. Values such as
the strings `"true"` or `"false"`, integers, and `None` are rejected during
client construction rather than interpreted by truthiness. Internal request
classifications and automation boolean controls enforce the same rule before
network I/O.

The transport does not automatically retry a paid request after an ambiguous
network failure because PropertyRadar does not document idempotency keys.

For transaction history, call `transaction_history(purchase=False)` first. A
valid preview does not authorize a later purchase. A purchased call still
requires client-level `allow_charges=True`, is never retried automatically,
and fails closed if required result-count or cost evidence is unavailable or
if preview-only free-quantity metadata appears in the charged response. The
purchase flag must be exactly boolean and is validated before network I/O.

`buyer_transfer_match()` uses the same dual opt-in and no-paid-retry rules. It
adds an exact RadarID criterion and a one-result limit, but a preview remains
only cost/request evidence and never authorizes a purchase automatically. Its
purchase flag must be exactly boolean or the method fails before network I/O.

The provider does not return the request's `Purchase` choice. Detached raw
responses therefore parse to unknown billing status unless the caller supplies
the exact request context. The provider also documents no currency or success
request identifier, so those values remain `None` rather than defaulting to
USD or an invented identifier.

## Persistent Mutations

List, import, automation, and webhook changes require
`allow_mutations=True`. Read-like POST searches and suggestions do not.

Automation `update()` is a vendor-defined full replacement. It also requires
`confirm_full_replacement=True`, rejects an empty replacement, and omits fields
you do not supply. Fetch the current configuration first and pass every setting
that must remain.

Webhook creation accepts only absolute HTTPS destinations without embedded URL
credentials so the vendor-sent bearer secret is not routed over cleartext.

## Personal And Licensed Data

PropertyRadar responses can contain names, addresses, phones, emails,
relatives, financial/legal events, and other sensitive fields. Callers remain
responsible for permitted use, access control, consent, suppression, retention,
deletion, and applicable laws.

The library does not log response bodies or persist API data. Tests and examples
use synthetic values. Typed transaction, party, record, and billing
representations report only shape and availability metadata; they omit names,
addresses, document/person identifiers, and licensed record values.

Typed buyer-transfer representations likewise omit buyer names, property IDs,
addresses, parcels, and scope fingerprints from `repr`. The linkage states
only that a property was returned for the provider's Buyer criterion. The
matching transaction, structured grantees, and exact/fuzzy name semantics are
unavailable and must not be inferred.

Transaction `Grantor` and `Grantee` values are opaque group displays. The
library never splits them into people or organizations. Optional property-person
composition verifies the same `RadarID`, preserves provider order, and exposes
current-owner identity evidence separately from any unsupported
person-to-transaction linkage.
