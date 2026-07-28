from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable

import httpx

from property_radar import PropertyRadarClient
from property_radar.types import Criterion

Handler = Callable[[httpx.Request], httpx.Response]


def make_client(
    handler: Handler,
    *,
    max_retries: int = 0,
) -> tuple[PropertyRadarClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PropertyRadarClient(
        api_key="synthetic-token",  # pragma: allowlist secret
        base_url="https://property-radar.test",
        max_retries=max_retries,
        http_client=http_client,
    )
    return client, http_client


def test_suggestions_encode_exact_queries_and_criteria_bodies() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"results": [{"Synthetic": True}]})

    client, http_client = make_client(handler)
    address_criteria: list[Criterion] = [{"name": "State", "value": ["UT"]}]
    county_criteria: list[Criterion] = [{"name": "State", "value": ["CO"]}]

    assert client.suggestions.site_addresses(
        "100 SYNTHETIC",
        criteria=address_criteria,
        limit=12,
        start=3,
    ) == {"results": [{"Synthetic": True}]}
    assert client.suggestions.counties(
        "SYNTH",
        criteria=county_criteria,
    ) == {"results": [{"Synthetic": True}]}

    assert [
        (request.method, request.url.path, request.url.params.multi_items())
        for request in captured
    ] == [
        (
            "POST",
            "/v1/suggestions/SiteAddress",
            [
                ("SuggestionInput", "100 SYNTHETIC"),
                ("Limit", "12"),
                ("Start", "3"),
            ],
        ),
        (
            "POST",
            "/v1/suggestions/County",
            [("SuggestionInput", "SYNTH")],
        ),
    ]
    assert [json.loads(request.content) for request in captured] == [
        {"Criteria": [{"name": "State", "value": ["UT"]}]},
        {"Criteria": [{"name": "State", "value": ["CO"]}]},
    ]
    client.close()
    http_client.close()


def test_suggestion_defaults_still_send_required_body_and_site_paging() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"results": []})

    client, http_client = make_client(handler)

    client.suggestions.site_addresses()
    client.suggestions.counties()

    assert [
        (request.url.path, request.url.params.multi_items()) for request in captured
    ] == [
        (
            "/v1/suggestions/SiteAddress",
            [("Limit", "255"), ("Start", "0")],
        ),
        ("/v1/suggestions/County", []),
    ]
    assert [json.loads(request.content) for request in captured] == [
        {"Criteria": []},
        {"Criteria": []},
    ]
    client.close()
    http_client.close()


def test_suggestion_posts_are_retryable_reads_not_mutations() -> None:
    attempts: defaultdict[str, int] = defaultdict(int)

    def handler(request: httpx.Request) -> httpx.Response:
        attempts[request.url.path] += 1
        if attempts[request.url.path] == 1:
            return httpx.Response(503, json={"message": "synthetic outage"})
        return httpx.Response(200, json={"results": []})

    client, http_client = make_client(handler, max_retries=1)

    assert client.suggestions.site_addresses("100 SYNTHETIC") == {"results": []}
    assert client.suggestions.counties("SYNTH") == {"results": []}
    assert attempts == {
        "/v1/suggestions/SiteAddress": 2,
        "/v1/suggestions/County": 2,
    }
    client.close()
    http_client.close()
