# Security Policy

## Supported Versions

Security fixes are applied to the latest released minor version.

## Reporting

Do not open a public issue for a credential exposure or exploitable
vulnerability. Use GitHub's private vulnerability reporting for
`theperrygroup/property_radar` when available, or contact the repository owner
through the organization profile.

## Credential And Data Policy

- Never include PropertyRadar tokens, webhook secrets, personal records, or
  licensed response payloads in an issue, test, example, log, or pull request.
- Rotate a credential immediately if it is exposed; deleting it from the latest
  revision does not remove it from history or published artifacts.
- The default test suite is intentionally secretless and must remain so.

## Safe Defaults

The client denies persistent API mutations and paid lookups unless callers
enable the corresponding client options. This guard reduces accidents but does
not replace account permissions, balance controls, consent, suppression,
retention, or applicable law.
