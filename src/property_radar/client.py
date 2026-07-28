"""Public facade for the synchronous PropertyRadar API client."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from ._transport import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, Transport
from .resources import (
    AccountsResource,
    AutomationsResource,
    DocumentsResource,
    ImportsResource,
    IntegrationsResource,
    ListsResource,
    PersonsResource,
    PropertiesResource,
    SuggestionsResource,
)


class PropertyRadarClient:
    """Synchronous facade exposing PropertyRadar resource clients.

    Args:
        api_key: Bearer token. Falls back to ``PROPERTY_RADAR_API_KEY``.
        token_provider: Callback returning a current bearer token. Mutually
            exclusive with ``api_key``.
        base_url: Absolute HTTPS PropertyRadar API origin without embedded
            credentials, a query, or a fragment.
        timeout: Request timeout passed to HTTPX.
        allow_mutations: Enable persistent list/import/automation/webhook calls.
        allow_charges: Enable invocations that explicitly request purchases.
        max_retries: Retry count for operations classified as safe.
        http_client: Optional injected HTTPX client, primarily for custom
            transports and tests. The caller retains its lifecycle.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        token_provider: Callable[[], str] | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        allow_mutations: bool = False,
        allow_charges: bool = False,
        max_retries: int = 2,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Initialize the facade and its shared transport."""
        self._transport = Transport(
            api_key=api_key,
            token_provider=token_provider,
            base_url=base_url,
            timeout=timeout,
            allow_mutations=allow_mutations,
            allow_charges=allow_charges,
            max_retries=max_retries,
            http_client=http_client,
        )
        self._accounts: AccountsResource | None = None
        self._automations: AutomationsResource | None = None
        self._documents: DocumentsResource | None = None
        self._imports: ImportsResource | None = None
        self._integrations: IntegrationsResource | None = None
        self._lists: ListsResource | None = None
        self._persons: PersonsResource | None = None
        self._properties: PropertiesResource | None = None
        self._suggestions: SuggestionsResource | None = None

    def __enter__(self) -> PropertyRadarClient:
        """Return this client for context-managed use."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close the internally owned HTTP connection pool."""
        self.close()

    def __repr__(self) -> str:
        """Return a credential-free representation."""
        return f"{type(self).__name__}({self._transport!r})"

    def close(self) -> None:
        """Close the internally owned HTTP connection pool."""
        self._transport.close()

    @property
    def accounts(self) -> AccountsResource:
        """Return the lazily constructed account resource."""
        if self._accounts is None:
            self._accounts = AccountsResource(self._transport)
        return self._accounts

    @property
    def automations(self) -> AutomationsResource:
        """Return the lazily constructed automation resource."""
        if self._automations is None:
            self._automations = AutomationsResource(self._transport)
        return self._automations

    @property
    def documents(self) -> DocumentsResource:
        """Return the lazily constructed document resource."""
        if self._documents is None:
            self._documents = DocumentsResource(self._transport)
        return self._documents

    @property
    def imports(self) -> ImportsResource:
        """Return the lazily constructed import resource."""
        if self._imports is None:
            self._imports = ImportsResource(self._transport)
        return self._imports

    @property
    def integrations(self) -> IntegrationsResource:
        """Return the lazily constructed integration resource."""
        if self._integrations is None:
            self._integrations = IntegrationsResource(self._transport)
        return self._integrations

    @property
    def lists(self) -> ListsResource:
        """Return the lazily constructed list resource."""
        if self._lists is None:
            self._lists = ListsResource(self._transport)
        return self._lists

    @property
    def persons(self) -> PersonsResource:
        """Return the lazily constructed person resource."""
        if self._persons is None:
            self._persons = PersonsResource(self._transport)
        return self._persons

    @property
    def properties(self) -> PropertiesResource:
        """Return the lazily constructed property resource."""
        if self._properties is None:
            self._properties = PropertiesResource(self._transport)
        return self._properties

    @property
    def suggestions(self) -> SuggestionsResource:
        """Return the lazily constructed suggestion resource."""
        if self._suggestions is None:
            self._suggestions = SuggestionsResource(self._transport)
        return self._suggestions
