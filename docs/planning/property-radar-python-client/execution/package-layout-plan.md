# Property Radar Package Layout Plan

Status: `PLANNING COMPLETE`

Effective date: `2026-07-28`

This is the first requested plan. It defines the repository and package
structure using the local and GitHub WFRMLS projects as references. The
canonical implementation sequence is
`api-library-implementation-plan.md`.

## 1. Outcome

Create a modern, PyPI-ready Python library that keeps WFRMLS's useful
facade/resource organization while correcting its lifecycle, typing, secret,
pagination, verification, and release weaknesses.

User-visible acceptance:

- `from property_radar import PropertyRadarClient` is the stable entry point.
- `with PropertyRadarClient(...) as client:` owns one shared connection pool.
- Resource methods are discoverable as `client.properties`, `client.persons`,
  `client.lists`, and related domains.
- Package metadata, typing marker, documentation, tests, CI, and release
  artifacts are included in the repository from the first release.
- Default behavior cannot make a paid lookup or persistent mutation.

## 2. Reference Findings

### Adopt From WFRMLS

- One top-level facade with lazy resource access.
- One focused module per resource family.
- Central transport and exception mapping.
- Explicit public exports and a shipped `py.typed` marker.
- MkDocs/mkdocstrings documentation.
- Tag/version validation, build-once artifact handoff, Twine checks, PyPI
  publication, and GitHub Release sequencing.

### Do Not Copy

- Hard-coded credentials or examples that print real property/person data.
- Per-resource HTTP sessions.
- Import-time `load_dotenv()`.
- No default timeout or cleanup.
- Catch-all pagination that silently returns partial/duplicate data.
- Untyped raw dictionaries as the only public contract.
- Unit tests that require API credentials.
- Soft-failed lint/type/security gates or an inaccurate coverage claim.
- Global workflow write permissions or token-based PyPI publication.
- Duplicated version values and duplicated requirements files.

## 3. Canonical Repository Layout

```text
.
├── .github/
│   ├── dependabot.yml
│   └── workflows/
│       ├── ci.yml
│       ├── docs.yml
│       └── release.yml
├── docs/
│   ├── api/
│   ├── guides/
│   ├── planning/
│   └── index.md
├── examples/
│   └── preview_property_search.py
├── scripts/
│   └── check_openapi_coverage.py
├── src/
│   └── property_radar/
│       ├── __init__.py
│       ├── _transport.py
│       ├── client.py
│       ├── exceptions.py
│       ├── types.py
│       ├── endpoint_manifest.json
│       ├── py.typed
│       └── resources/
│           ├── __init__.py
│           ├── _base.py
│           ├── accounts.py
│           ├── automations.py
│           ├── documents.py
│           ├── imports.py
│           ├── integrations.py
│           ├── lists.py
│           ├── persons.py
│           ├── properties.py
│           └── suggestions.py
├── tests/
│   ├── contract/
│   └── unit/
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── SECURITY.md
├── mkdocs.yml
├── pyproject.toml
└── uv.lock
```

The implementation may combine tiny test directories or documentation pages
when that reduces empty scaffolding, but runtime ownership stays as shown.

## 4. Module Responsibilities

| Surface | Responsibility |
| --- | --- |
| `client.py` | Public facade, configuration, context management, lazy resource properties |
| `_transport.py` | Authentication, query encoding, timeouts, safe retries, response parsing, error mapping, mutation/charge guards |
| `exceptions.py` | Typed error hierarchy with sanitized status/request/retry metadata |
| `types.py` | JSON values, criteria, response envelope, import item, and safe option contracts |
| `resources/_base.py` | Shared resource access to the single transport |
| Resource modules | Pythonic methods mapped one-to-one to official operations |
| `endpoint_manifest.json` | Small checked-in operation inventory for coverage/drift checks |
| `scripts/check_openapi_coverage.py` | Read-only comparison between manifest and official OpenAPI |
| `tests/unit/` | Secretless request, response, safety, and lifecycle tests |
| `tests/contract/` | Manifest/public-method mapping and artifact contract tests |

## 5. Public API Shape

```python
from property_radar import PropertyRadarClient

criteria = [{"name": "RadarID", "value": ["P0000000"]}]

with PropertyRadarClient(api_key="...") as client:
    preview = client.properties.search(criteria=criteria)
```

Persistent changes require `allow_mutations=True`. Paid results require both
`allow_charges=True` and `purchase=True` on the method invocation.

## 6. Packaging And Tooling

- `pyproject.toml` is the single dependency and tool-configuration source.
- Hatchling builds a `src/` package; `importlib.metadata` provides the runtime
  version.
- `uv.lock` locks development and documentation tooling.
- Ruff owns formatting and linting; mypy runs strict typing.
- pytest runs secretless tests with an honest, enforced coverage threshold.
- MkDocs builds in strict mode.
- `python -m build`, Twine, artifact-content inspection, and a clean wheel
  install prove distribution integrity.

## 7. CI And Release Shape

- CI defaults to `contents: read`, runs on pull requests and `main`, and cancels
  obsolete pull-request runs.
- Linux covers every supported Python version; one current version covers
  Windows and macOS smoke behavior.
- The package build depends on required quality/test/docs gates.
- Docs deployment grants Pages/OIDC permissions only to its deployment job.
- Release builds once, checks `vX.Y.Z` parity, publishes the same artifacts via
  Trusted Publishing, then creates a GitHub Release in a separate permission
  boundary.
- No PropertyRadar API token is used in CI or release automation.

## 8. Layout Acceptance Checklist

- [ ] Package imports only from an installed `src/` distribution.
- [ ] One top-level client owns and closes one transport.
- [ ] Every official resource family has a module and facade property.
- [ ] Stable response metadata is typed; vendor fields remain forward
      compatible.
- [ ] Mutation and paid-request guards are unit-tested.
- [ ] No credential or personal-data fixture is tracked or packaged.
- [ ] Wheel and sdist contain only intended runtime/docs/license artifacts.
- [ ] CI, docs, and release workflows use least privilege and hard gates.
- [ ] Root docs state unofficial status, vendor terms boundary, support policy,
      and sync-only scope.

## 9. Deferred Decisions

- Async client: defer until demand justifies shared sync/async transport work.
- Generated field models and the full 250+ criteria catalog: defer to avoid
  stale, lossy snapshots.
- Live integration suite: defer until a licensed, non-billable test account and
  sanitized fixture policy are explicitly authorized.
- PyPI project/trusted-publisher creation and first public release: external
  setup and publication evidence are tracked separately.
