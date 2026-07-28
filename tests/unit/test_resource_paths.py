from __future__ import annotations

from collections.abc import Callable
from typing import cast

import httpx
import pytest

from property_radar import PropertyRadarClient
from property_radar.exceptions import ConfigurationError

InvalidOperation = Callable[[PropertyRadarClient, str], object]


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[PropertyRadarClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PropertyRadarClient(
        api_key="synthetic-token",  # pragma: allowlist secret
        allow_mutations=True,
        allow_charges=True,
        max_retries=0,
        http_client=http_client,
    )
    return client, http_client


def test_dynamic_identifiers_are_single_percent_encoded_path_segments() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    client, http_client = make_client(handler)
    identifier = "synthetic/child?mode=full#part.one"
    integer_identifier = cast(int, identifier)

    client.documents.get(identifier)
    client.persons.relatives(identifier)
    client.lists.delete_item(integer_identifier, identifier)
    client.imports.delete_match(integer_identifier, integer_identifier)
    client.automations.get(integer_identifier)
    client.integrations.delete_webhook(integer_identifier)

    encoded = b"synthetic%2Fchild%3Fmode%3Dfull%23part.one"
    assert [(request.method, request.url.raw_path) for request in captured] == [
        ("GET", b"/v1/documents/" + encoded + b"?Purchase=0"),
        ("GET", b"/v1/persons/" + encoded + b"/relatives?Purchase=0"),
        ("DELETE", b"/v1/lists/" + encoded + b"/items/" + encoded),
        (
            "DELETE",
            b"/v1/lists/" + encoded + b"/import/items/" + encoded,
        ),
        ("GET", b"/v1/lists/" + encoded + b"/automations"),
        ("DELETE", b"/v1/integrations/webhooks/" + encoded),
    ]
    http_client.close()


@pytest.mark.parametrize("invalid_identifier", ["", ".", ".."])
@pytest.mark.parametrize(
    "operation",
    [
        lambda client, value: client.documents.get(value),
        lambda client, value: client.persons.phone(value),
        lambda client, value: client.lists.get(cast(int, value)),
        lambda client, value: client.lists.delete_item(101, value),
        lambda client, value: client.imports.items(cast(int, value)),
        lambda client, value: client.imports.update_match(
            101,
            cast(int, value),
            radar_id="synthetic-radar-id",
        ),
        lambda client, value: client.automations.get(cast(int, value)),
        lambda client, value: client.integrations.delete_webhook(cast(int, value)),
    ],
)
def test_invalid_path_segments_are_rejected_before_network_io(
    invalid_identifier: str,
    operation: InvalidOperation,
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    client, http_client = make_client(handler)

    with pytest.raises(ConfigurationError, match="path segments"):
        operation(client, invalid_identifier)

    assert captured == []
    http_client.close()
