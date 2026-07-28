# API Coverage Readiness

## Contract Baseline

- Design source: `https://developers.propertyradar.com/_spec/api.yaml`
- Automated drift source: equivalent JSON document at
  `https://developers.propertyradar.com/_spec/api.json`
- Inspected: `2026-07-28`
- OpenAPI: `3.1.0`
- Vendor API version: `5.1.1.0`
- Paths: `29`
- Operations: `37`
- Tags: Accounts, Automations, Documents, Imports, Integrations, Lists, Persons,
  Properties, Suggestions

Coverage means a dedicated public wrapper method, endpoint-manifest mapping,
request/response/error test, safety classification, and passing focused local
gates. It does not mean the method was called against a live account.

## Coverage Matrix

| # | Method and path | Planned public surface | Class | Status |
| --- | --- | --- | --- | --- |
| 1 | `GET /v1/accounts/members` | `client.accounts.members()` | read | `Verified locally` |
| 2 | `GET /v1/accounts/preferences/statuses` | `client.accounts.status_labels()` | read | `Verified locally` |
| 3 | `GET /v1/documents/{DocumentID}` | `client.documents.get()` | billable preview | `Verified locally` |
| 4 | `GET /v1/properties/{RadarID}` | `client.properties.get()` | billable preview | `Verified locally` |
| 5 | `POST /v1/properties` | `client.properties.search()` | read-like POST, billable preview | `Verified locally` |
| 6 | `GET /v1/properties/{RadarID}/persons` | `client.properties.persons()` | billable preview, personal data | `Verified locally` |
| 7 | `GET /v1/properties/{RadarID}/evictions` | `client.properties.evictions()` | billable preview, personal data | `Verified locally` |
| 8 | `GET /v1/properties/{RadarID}/comps/sales` | `client.properties.comparable_sales()` | billable preview | `Verified locally` |
| 9 | `GET /v1/properties/{RadarID}/comps/forsale` | `client.properties.comparable_listings()` | billable preview | `Verified locally` |
| 10 | `GET /v1/properties/{RadarID}/parcels` | `client.properties.parcels()` | billable preview | `Verified locally` |
| 11 | `GET /v1/properties/{RadarID}/transactions` | `client.properties.transactions()` | billable preview | `Verified locally` |
| 12 | `GET /v1/persons/{PersonKey}/bankruptcies` | `client.persons.bankruptcies()` | billable preview, personal data | `Verified locally` |
| 13 | `GET /v1/persons/{PersonKey}/divorces` | `client.persons.divorces()` | billable preview, personal data | `Verified locally` |
| 14 | `GET /v1/persons/{PersonKey}/liens` | `client.persons.liens()` | billable preview, personal data | `Verified locally` |
| 15 | `GET /v1/persons/{PersonKey}/probates` | `client.persons.probates()` | billable preview, personal data | `Verified locally` |
| 16 | `GET /v1/persons/{PersonKey}/relatives` | `client.persons.relatives()` | billable preview, personal data | `Verified locally` |
| 17 | `POST /v1/persons/{PersonKey}/Phone` | `client.persons.phone()` | billable, personal data | `Verified locally` |
| 18 | `POST /v1/persons/{PersonKey}/Email` | `client.persons.email()` | billable, personal data | `Verified locally` |
| 19 | `POST /v1/suggestions/SiteAddress` | `client.suggestions.site_addresses()` | read-like POST | `Verified locally` |
| 20 | `POST /v1/suggestions/County` | `client.suggestions.counties()` | read-like POST | `Verified locally` |
| 21 | `GET /v1/lists` | `client.lists.all()` | read | `Verified locally` |
| 22 | `POST /v1/lists` | `client.lists.create()` | mutation | `Verified locally` |
| 23 | `GET /v1/lists/{ListID}` | `client.lists.get()` | read | `Verified locally` |
| 24 | `PATCH /v1/lists/{ListID}` | `client.lists.update()` | mutation | `Verified locally` |
| 25 | `DELETE /v1/lists/{ListID}` | `client.lists.delete()` | destructive mutation | `Verified locally` |
| 26 | `GET /v1/lists/{ListID}/items` | `client.lists.items()` | read | `Verified locally` |
| 27 | `PUT /v1/lists/{ListID}/items` | `client.lists.add_items()` | mutation | `Verified locally` |
| 28 | `DELETE /v1/lists/{ListID}/items/{RadarID}` | `client.lists.delete_item()` | destructive mutation | `Verified locally` |
| 29 | `GET /v1/lists/{ListID}/import/items` | `client.imports.items()` | read, personal data | `Verified locally` |
| 30 | `POST /v1/lists/{ListID}/import/items` | `client.imports.match()` | mutation, billable preview, personal data | `Verified locally` |
| 31 | `PATCH /v1/lists/{ListID}/import/items/{ListImportItemID}` | `client.imports.update_match()` | mutation | `Verified locally` |
| 32 | `DELETE /v1/lists/{ListID}/import/items/{ListImportItemID}` | `client.imports.delete_match()` | destructive mutation | `Verified locally` |
| 33 | `GET /v1/lists/{ListID}/automations` | `client.automations.get()` | read | `Verified locally` |
| 34 | `PUT /v1/lists/{ListID}/automations` | `client.automations.update()` | mutation, possible ongoing charge | `Verified locally` |
| 35 | `GET /v1/integrations/webhooks` | `client.integrations.webhooks()` | read, secret-bearing response | `Verified locally` |
| 36 | `POST /v1/integrations/webhooks` | `client.integrations.create_webhook()` | mutation | `Verified locally` |
| 37 | `DELETE /v1/integrations/webhooks/{WebhookID}` | `client.integrations.delete_webhook()` | destructive mutation | `Verified locally` |

## Current Totals

| State | Count |
| --- | --- |
| Contract operations | 37 |
| Implemented locally | 37 |
| Verified locally | 37 |
| Live verified | 1 |

Live verification covers only the account status-label request and
authentication boundary. The other 36 operations remain contract/mock
verified; no paid or mutating endpoint was called.

## Contract Ambiguities To Preserve

- Changelog mentions `/v1/lists/groups`, but the current OpenAPI omits it; do
  not invent a wrapper.
- Webhook `Lists` is typed as objects but exemplified as integer IDs.
- Automation update is a full replacement; callers need GET/modify/PUT
  guidance.
- Status examples disagree on whether level 10 exists.
- Document `DryRun` has mutation-like prose despite a GET with no body.
- Relatives has a `Purchase` parameter but lacks normal paid-envelope metadata.
- Phone/email purchase responses do not contain the purchased values.
- No numeric rate limit, cursor, idempotency key, 429 contract, or mutation
  concurrency mechanism is documented.
- OAuth is mentioned in prose but no OAuth flow is in the OpenAPI document.

## Refresh Rule

Run the read-only drift check against the official spec before changing this
denominator or publishing a release. Review additions/removals manually; do not
generate new mutating methods without a safety classification.
