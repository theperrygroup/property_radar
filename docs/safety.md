# Safety And Data

## Paid Requests

Paid requests require two independent choices:

1. Construct the client with `allow_charges=True`.
2. Pass `purchase=True` to the specific method.

The transport does not automatically retry a paid request after an ambiguous
network failure because PropertyRadar does not document idempotency keys.

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
use synthetic values.
