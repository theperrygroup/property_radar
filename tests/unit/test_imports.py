from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from property_radar import PropertyRadarClient
from property_radar.exceptions import (
    ChargeNotAllowedError,
    MutationNotAllowedError,
    ServerError,
)
from property_radar.types import ImportItem

Handler = Callable[[httpx.Request], httpx.Response]
ClientOperation = Callable[[PropertyRadarClient], object]


def make_client(
    handler: Handler,
    *,
    allow_mutations: bool = False,
    allow_charges: bool = False,
    max_retries: int = 0,
) -> tuple[PropertyRadarClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PropertyRadarClient(
        api_key="synthetic-token",
        allow_mutations=allow_mutations,
        allow_charges=allow_charges,
        max_retries=max_retries,
        http_client=http_client,
    )
    return client, http_client


def request_body(request: httpx.Request) -> object:
    payload: object = json.loads(request.content)
    return payload


def synthetic_import_items() -> list[ImportItem]:
    return [
        {
            "FirstName": "Synthetic",
            "LastName": "Owner",
            "Email": "synthetic@example.invalid",
            "Phone": "555-0100",
            "Address": "100 Test Way",
            "City": "Example",
            "State": "CO",
            "ZipFive": 80000,
            "County": "SYNTHETIC",
            "APN": "TEST-0001",
        }
    ]


def test_all_four_import_operations_construct_exact_requests() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    client, http_client = make_client(handler, allow_mutations=True)
    import_items = synthetic_import_items()

    client.imports.items(
        404,
        fields=["ListImportItemID", "-Email"],
        limit=12,
        sort="MatchScore",
        direction="desc",
        start=3,
        match_score=75,
        property_status="Matched",
        person_status="Matched Primary",
    )
    client.imports.match(
        404,
        import_items,
        fields=["ListImportItemID"],
    )
    client.imports.update_match(
        404,
        505,
        person_key="PERSON-SYNTHETIC",
        radar_id="PTEST0004",
    )
    client.imports.delete_match(404, 505)

    assert [(request.method, request.url.path) for request in captured] == [
        ("GET", "/v1/lists/404/import/items"),
        ("POST", "/v1/lists/404/import/items"),
        ("PATCH", "/v1/lists/404/import/items/505"),
        ("DELETE", "/v1/lists/404/import/items/505"),
    ]
    assert captured[0].url.params.multi_items() == [
        ("Fields", "ListImportItemID,-Email"),
        ("Limit", "12"),
        ("Sort", "MatchScore"),
        ("Dir", "desc"),
        ("Start", "3"),
        ("MatchScore", "75"),
        ("PropertyStatus", "Matched"),
        ("PersonStatus", "Matched Primary"),
    ]
    assert captured[1].url.params.multi_items() == [
        ("Fields", "ListImportItemID"),
        ("Purchase", "0"),
    ]
    assert request_body(captured[1]) == import_items
    assert request_body(captured[2]) == {
        "PersonKey": "PERSON-SYNTHETIC",
        "RadarID": "PTEST0004",
    }
    http_client.close()


def test_import_match_purchase_requires_charge_opt_in_before_network_io() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client, http_client = make_client(handler, allow_mutations=True)
    with pytest.raises(ChargeNotAllowedError):
        client.imports.match(606, synthetic_import_items(), purchase=True)

    assert calls == 0
    http_client.close()


def test_update_match_omits_unset_values() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    client, http_client = make_client(handler, allow_mutations=True)
    client.imports.update_match(
        606,
        707,
        person_key="PERSON-ONLY-SYNTHETIC",
    )

    assert request_body(captured[0]) == {
        "PersonKey": "PERSON-ONLY-SYNTHETIC",
    }
    http_client.close()


def test_every_import_mutation_is_blocked_before_network_io() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client, http_client = make_client(handler)
    operations: list[ClientOperation] = [
        lambda value: value.imports.match(606, synthetic_import_items()),
        lambda value: value.imports.update_match(
            606,
            707,
            radar_id="PTEST0005",
        ),
        lambda value: value.imports.delete_match(606, 707),
    ]

    for operation in operations:
        with pytest.raises(MutationNotAllowedError):
            operation(client)

    assert calls == 0
    http_client.close()


@pytest.mark.parametrize(
    "operation",
    [
        lambda client: client.imports.match(808, synthetic_import_items()),
        lambda client: client.imports.update_match(
            808,
            909,
            radar_id="PTEST0006",
        ),
        lambda client: client.imports.delete_match(808, 909),
    ],
)
def test_import_mutations_are_never_retried(operation: ClientOperation) -> None:
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
