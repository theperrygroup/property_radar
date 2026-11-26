# Property Radar Python Client

`property-radar` is an unofficial, synchronous Python client for the official
PropertyRadar API.

The base client targets API contract `5.2.0.0`, with a separate historical
Buyer-match interface grounded in official API `5.3.1.0` evidence. It emphasizes
explicit authentication, typed interfaces, secretless tests, and
deny-by-default paid or persistent operations.

## Project State

The `0.4.3` implementation covers all 37 operations in PropertyRadar API
contract `5.2.0.0` and adds a separate immutable, fingerprinted historical
Buyer-criterion property/location interface based on API `5.3.1.0`. Exact,
inclusive, ordered recording-date ranges may span multiple years. Historical
results use new types and preserve five-digit ZIP strings with leading zeros.
Version `0.4.3` accepts the JSON numbers that live historical-transaction rows
send in record fields declared as strings. Both record parsers give a number
as its exact decimal text, a boolean in one of the three flag fields as `"1"`
or `"0"`, and a `null` outside `RecDate` as a missing field, and both
transaction contracts have new fingerprints; the
[record value rule](historical-transactions.md#preserve-record-uncertainty)
gives the details. The `0.4.2` preview and `totalCost` rules are unchanged.
Existing parameters, attributes, and raw resource return types remain. New
parameters are keyword-only with defaults, and new dataclass fields come last
with defaults; the project changelog lists them. See the
[usage guide](usage.md#historical-recording-dates) for historical queries.

The separate [historical transaction interface](historical-transactions.md)
returns preview counts and estimated cost without requiring rows, and retains
the selected paid rows with explicit completeness and date-ambiguity metadata.

Releases use a build-once workflow and PyPI Trusted Publishing.

## Vendor Boundary

This project is not affiliated with or endorsed by PropertyRadar. Review
PropertyRadar's service and data-use terms before using the client, especially
for third-party applications, marketing, personal data, or redistribution.
