from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from property_radar import PropertyRadarClient
from property_radar.exceptions import ChargeNotAllowedError, ServerError
from property_radar.types import ResponseEnvelope

Handler = Callable[[httpx.Request], httpx.Response]


def make_client(
    handler: Handler,
    *,
    allow_charges: bool = False,
    max_retries: int = 0,
) -> tuple[PropertyRadarClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PropertyRadarClient(
        api_key="synthetic-token",  # pragma: allowlist secret
        base_url="https://property-radar.test",
        allow_charges=allow_charges,
        max_retries=max_retries,
        http_client=http_client,
    )
    return client, http_client


def test_person_record_previews_encode_exact_paths_and_queries() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"results": [{"SyntheticRecord": True}]})

    client, http_client = make_client(handler)

    results = [
        client.persons.bankruptcies(
            "person-bankruptcy",
            fields=("PersonKey", "-BankruptcyAttorneyPhone"),
            limit=17,
            start=4,
        ),
        client.persons.divorces("person-divorce"),
        client.persons.liens(
            "person-lien",
            fields=("PersonLienKey", "-DocImageUrl"),
        ),
        client.persons.probates("person-probate"),
        client.persons.relatives("person-relative"),
    ]

    assert all(result["results"] == [{"SyntheticRecord": True}] for result in results)
    assert [
        (request.method, request.url.path, request.url.params.multi_items())
        for request in captured
    ] == [
        (
            "GET",
            "/v1/persons/person-bankruptcy/bankruptcies",
            [
                ("Fields", "PersonKey,-BankruptcyAttorneyPhone"),
                ("Limit", "17"),
                ("Start", "4"),
                ("Purchase", "0"),
            ],
        ),
        (
            "GET",
            "/v1/persons/person-divorce/divorces",
            [("Limit", "100"), ("Start", "0"), ("Purchase", "0")],
        ),
        (
            "GET",
            "/v1/persons/person-lien/liens",
            [
                ("Fields", "PersonLienKey,-DocImageUrl"),
                ("Limit", "500"),
                ("Purchase", "0"),
            ],
        ),
        (
            "GET",
            "/v1/persons/person-probate/probates",
            [("Limit", "100"), ("Start", "0"), ("Purchase", "0")],
        ),
        (
            "GET",
            "/v1/persons/person-relative/relatives",
            [("Purchase", "0")],
        ),
    ]
    assert all(request.content == b"" for request in captured)
    client.close()
    http_client.close()


def test_contact_previews_use_cased_post_paths_without_bodies() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"results": []})

    client, http_client = make_client(handler)

    assert client.persons.phone("person-phone") == {"results": []}
    assert client.persons.email("person-email") == {"results": []}

    assert [
        (request.method, request.url.path, request.url.params.multi_items())
        for request in captured
    ] == [
        (
            "POST",
            "/v1/persons/person-phone/Phone",
            [("Purchase", "0")],
        ),
        (
            "POST",
            "/v1/persons/person-email/Email",
            [("Purchase", "0")],
        ),
    ]
    assert all(request.content == b"" for request in captured)
    client.close()
    http_client.close()


def test_every_person_purchase_is_denied_before_network_io() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client, http_client = make_client(handler)
    paid_operations: list[Callable[[], ResponseEnvelope]] = [
        lambda: client.persons.bankruptcies(
            "person-bankruptcy",
            purchase=True,
        ),
        lambda: client.persons.divorces("person-divorce", purchase=True),
        lambda: client.persons.liens("person-lien", purchase=True),
        lambda: client.persons.probates("person-probate", purchase=True),
        lambda: client.persons.relatives("person-relative", purchase=True),
        lambda: client.persons.phone("person-phone", purchase=True),
        lambda: client.persons.email("person-email", purchase=True),
    ]

    for operation in paid_operations:
        with pytest.raises(ChargeNotAllowedError, match="requests are disabled"):
            operation()

    assert calls == 0
    client.close()
    http_client.close()


def test_paid_contact_posts_are_not_retried() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(503, json={"message": "synthetic outage"})

    client, http_client = make_client(
        handler,
        allow_charges=True,
        max_retries=3,
    )

    with pytest.raises(ServerError):
        client.persons.phone("person-phone", purchase=True)
    with pytest.raises(ServerError):
        client.persons.email("person-email", purchase=True)

    assert [
        (request.url.path, request.url.params.multi_items(), request.content)
        for request in captured
    ] == [
        (
            "/v1/persons/person-phone/Phone",
            [("Purchase", "1")],
            b"",
        ),
        (
            "/v1/persons/person-email/Email",
            [("Purchase", "1")],
            b"",
        ),
    ]
    client.close()
    http_client.close()
