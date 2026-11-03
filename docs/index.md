# Property Radar Python Client

`property-radar` is an unofficial, synchronous Python client for the official
PropertyRadar API.

The base client targets API contract `5.2.0.0`, with a separate historical
Buyer-match interface grounded in official API `5.3.1.0` evidence. It emphasizes
explicit authentication, typed interfaces, secretless tests, and
deny-by-default paid or persistent operations.

## Project State

The `0.4.0` release candidate covers all 37 operations in PropertyRadar API
contract `5.2.0.0` and adds a separate immutable, fingerprinted historical
Buyer-criterion property/location interface based on API `5.3.1.0`. Exact,
inclusive, ordered recording-date ranges may span multiple years. Historical
results use new types and preserve five-digit ZIP strings with leading zeros;
existing recent-query contracts, fingerprints, types, typed transaction-history
evidence, and raw resource return types remain unchanged. See the
[usage guide](usage.md#historical-recording-dates) for historical queries.

Tagging and publication are pending. Releases use a build-once workflow and
PyPI Trusted Publishing.

## Vendor Boundary

This project is not affiliated with or endorsed by PropertyRadar. Review
PropertyRadar's service and data-use terms before using the client, especially
for third-party applications, marketing, personal data, or redistribution.
