from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from property_radar import PropertyRadarClient
from property_radar.exceptions import (
    BadRequestError,
    ConfigurationError,
    MutationNotAllowedError,
    ServerError,
)

Handler = Callable[[httpx.Request], httpx.Response]
ClientOperation = Callable[[PropertyRadarClient], object]


def make_client(
    handler: Handler,
    *,
    allow_mutations: bool = False,
    max_retries: int = 0,
) -> tuple[PropertyRadarClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PropertyRadarClient(
        api_key="synthetic-token",  # pragma: allowlist secret
        allow_mutations=allow_mutations,
        max_retries=max_retries,
        http_client=http_client,
    )
    return client, http_client


def request_body(request: httpx.Request) -> object:
    payload: object = json.loads(request.content)
    return payload


def test_all_three_integration_operations_construct_exact_requests() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    client, http_client = make_client(handler, allow_mutations=True)
    client.integrations.webhooks(
        fields=["WebhookID", "-Secret"],
        limit=15,
        sort="WebhookName",
        direction="desc",
        start=2,
    )
    client.integrations.create_webhook(
        hook_url="https://example.invalid/property-radar",
        webhook_name="Synthetic Hook",
        secret="synthetic-webhook-secret",  # pragma: allowlist secret
        list_ids=[1101, 1102],
    )
    client.integrations.delete_webhook(1201)

    assert [(request.method, request.url.path) for request in captured] == [
        ("GET", "/v1/integrations/webhooks"),
        ("POST", "/v1/integrations/webhooks"),
        ("DELETE", "/v1/integrations/webhooks/1201"),
    ]
    assert captured[0].url.params.multi_items() == [
        ("Fields", "WebhookID,-Secret"),
        ("Limit", "15"),
        ("Sort", "WebhookName"),
        ("Dir", "desc"),
        ("Start", "2"),
    ]
    assert request_body(captured[1]) == {
        "HookUrl": "https://example.invalid/property-radar",
        "WebhookName": "Synthetic Hook",
        "Secret": "synthetic-webhook-secret",  # pragma: allowlist secret
        "Lists": [1101, 1102],
    }
    http_client.close()


def test_every_integration_mutation_is_blocked_before_network_io() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client, http_client = make_client(handler)
    operations: list[ClientOperation] = [
        lambda value: value.integrations.create_webhook(
            hook_url="https://example.invalid/blocked",
            webhook_name="Blocked",
            secret="blocked-secret",  # pragma: allowlist secret
        ),
        lambda value: value.integrations.delete_webhook(1301),
    ]

    for operation in operations:
        with pytest.raises(MutationNotAllowedError) as captured:
            operation(client)
        assert "blocked-secret" not in str(captured.value)
        assert "blocked-secret" not in repr(captured.value)

    assert calls == 0
    http_client.close()


def test_webhook_secret_is_sent_only_in_body_and_redacted_from_errors_and_repr() -> (
    None
):
    secret = "never-expose-this-webhook-secret"  # pragma: allowlist secret
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            400,
            json={
                "eventid": "synthetic-webhook-event",
                "message": secret,
            },
        )

    client, http_client = make_client(handler, allow_mutations=True)
    with pytest.raises(BadRequestError) as captured_error:
        client.integrations.create_webhook(
            hook_url="https://example.invalid/error",
            webhook_name="Synthetic Error Hook",
            secret=secret,
        )

    request = captured_requests[0]
    assert secret not in str(request.url)
    assert all(secret not in value for value in request.headers.values())
    assert request_body(request) == {
        "HookUrl": "https://example.invalid/error",
        "WebhookName": "Synthetic Error Hook",
        "Secret": secret,
    }
    for value in (
        str(captured_error.value),
        repr(captured_error.value),
        repr(client),
        repr(client.integrations),
    ):
        assert secret not in value
    http_client.close()


@pytest.mark.parametrize(
    "operation",
    [
        lambda client: client.integrations.create_webhook(
            hook_url="https://example.invalid/retry",
            webhook_name="Synthetic",
        ),
        lambda client: client.integrations.delete_webhook(1401),
    ],
)
def test_integration_mutations_are_never_retried(
    operation: ClientOperation,
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={})

    client, http_client = make_client(
        handler,
        allow_mutations=True,
        max_retries=3,
    )
    with pytest.raises(ServerError):
        operation(client)

    assert calls == 1
    http_client.close()


@pytest.mark.parametrize(
    "hook_url",
    [
        "http://example.invalid/insecure",
        "https://user:password@example.invalid/embedded",  # pragma: allowlist secret
        "https://example.invalid:invalid-port/webhook",
        "not-an-absolute-url",
    ],
)
def test_create_webhook_rejects_unsafe_urls_before_network_io(
    hook_url: str,
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client, http_client = make_client(handler, allow_mutations=True)
    with pytest.raises(ConfigurationError, match="Webhook URL"):
        client.integrations.create_webhook(
            hook_url=hook_url,
            webhook_name="Unsafe",
            secret="must-not-be-sent",  # pragma: allowlist secret
        )

    assert calls == 0
    http_client.close()
