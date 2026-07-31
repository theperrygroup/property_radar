# Property Radar Python Client

`property-radar` is an unofficial, synchronous Python client for the official
PropertyRadar API.

The client targets API contract `5.2.0.0` and emphasizes explicit
authentication, typed interfaces, secretless tests, and deny-by-default paid
or persistent operations.

## Project State

The `0.2.0` implementation covers all 37 operations in PropertyRadar API
contract `5.2.0.0` and exposes an immutable, fingerprinted transaction-history
contract, typed party/current-owner composition, and typed billing evidence.
Raw `0.1.0` resource return types remain compatible. Releases use a build-once
workflow and PyPI Trusted Publishing.

## Vendor Boundary

This project is not affiliated with or endorsed by PropertyRadar. Review
PropertyRadar's service and data-use terms before using the client, especially
for third-party applications, marketing, personal data, or redistribution.
