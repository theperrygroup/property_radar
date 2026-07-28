from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from property_radar import PropertyRadarClient
from property_radar.exceptions import (
    BadRequestError,
    ChargeNotAllowedError,
    ConfigurationError,
    InvalidResponseError,
    NotFoundError,
    ServerError,
)
from property_radar.types import Criterion, ResponseEnvelope

Handler = Callable[[httpx.Request], httpx.Response]
Operation = Callable[[PropertyRadarClient], ResponseEnvelope]

CRITERIA: list[Criterion] = [
    {"name": "RadarID", "value": ["P-SYNTHETIC"]},
]


def make_client(
    handler: Handler,
    *,
    allow_charges: bool = False,
    max_retries: int = 0,
) -> tuple[PropertyRadarClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PropertyRadarClient(
        api_key="synthetic-token",  # pragma: allowlist secret
        allow_charges=allow_charges,
        max_retries=max_retries,
        http_client=http_client,
    )
    return client, http_client


def capture_request(
    operation: Operation,
    *,
    response: ResponseEnvelope | None = None,
) -> tuple[ResponseEnvelope, httpx.Request]:
    captured: list[httpx.Request] = []
    payload: ResponseEnvelope = response if response is not None else {"results": []}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=payload)

    client, http_client = make_client(handler)
    try:
        result = operation(client)
    finally:
        http_client.close()
    return result, captured[0]


def test_property_get_request() -> None:
    result, request = capture_request(
        lambda client: client.properties.get(
            "P-SYNTHETIC",
            fields=("Overview", "APN"),
        ),
        response={"results": [{"RadarID": "P-SYNTHETIC"}]},
    )

    assert result["results"] == [{"RadarID": "P-SYNTHETIC"}]
    assert request.method == "GET"
    assert request.url.path == "/v1/properties/P-SYNTHETIC"
    assert request.url.params.multi_items() == [
        ("Fields", "Overview,APN"),
        ("Purchase", "0"),
    ]
    assert request.content == b""


def test_property_search_request_body_and_query() -> None:
    _, request = capture_request(
        lambda client: client.properties.search(
            criteria=CRITERIA,
            fields=("RadarID", "APN"),
            limit=25,
            sort="APN ASC",
            start=50,
        )
    )

    assert request.method == "POST"
    assert request.url.path == "/v1/properties"
    assert request.url.params.multi_items() == [
        ("Fields", "RadarID,APN"),
        ("Limit", "25"),
        ("Sort", "APN ASC"),
        ("Start", "50"),
        ("Purchase", "0"),
    ]
    assert json.loads(request.content) == {"Criteria": CRITERIA}


def test_property_persons_and_evictions_requests() -> None:
    _, persons_request = capture_request(
        lambda client: client.properties.persons(
            "P-SYNTHETIC",
            fields=("PersonKey", "FirstName"),
        )
    )
    _, evictions_request = capture_request(
        lambda client: client.properties.evictions(
            "P-SYNTHETIC",
            fields=("EvictionFilingDate", "EvictionCaseNumber"),
            limit=20,
            start=40,
        )
    )

    assert persons_request.method == "GET"
    assert persons_request.url.path == "/v1/properties/P-SYNTHETIC/persons"
    assert persons_request.url.params.multi_items() == [
        ("Fields", "PersonKey,FirstName"),
        ("Purchase", "0"),
    ]
    assert evictions_request.method == "GET"
    assert evictions_request.url.path == "/v1/properties/P-SYNTHETIC/evictions"
    assert evictions_request.url.params.multi_items() == [
        ("Fields", "EvictionFilingDate,EvictionCaseNumber"),
        ("Limit", "20"),
        ("Start", "40"),
        ("Purchase", "0"),
    ]


def test_comparable_sales_request_and_comma_delimited_filters() -> None:
    _, request = capture_request(
        lambda client: client.properties.comparable_sales(
            "P-SYNTHETIC",
            fields=("RadarID", "TransferValue"),
            limit=7,
            p_type=("SFR", "CND"),
            beds=3,
            baths="2-4",
            units=2,
            sq_ft=1800,
            lot_size=6000,
            year_built="1990-2020",
            transfer_type=("Market", "REOResale"),
        )
    )

    assert request.method == "GET"
    assert request.url.path == "/v1/properties/P-SYNTHETIC/comps/sales"
    assert request.url.params.multi_items() == [
        ("Fields", "RadarID,TransferValue"),
        ("Purchase", "0"),
        ("Limit", "7"),
        ("PType", "SFR,CND"),
        ("Beds", "3"),
        ("Baths", "2-4"),
        ("Units", "2"),
        ("SqFt", "1800"),
        ("LotSize", "6000"),
        ("YearBuilt", "1990-2020"),
        ("TransferType", "Market,REOResale"),
    ]


def test_comparable_listings_request_and_comma_delimited_filters() -> None:
    _, request = capture_request(
        lambda client: client.properties.comparable_listings(
            "P-SYNTHETIC",
            fields=("RadarID", "ListingPrice"),
            limit=9,
            p_type=("SFR", "MFR"),
            beds=4,
            baths="3+",
            units=3,
            sq_ft=2400,
            lot_size=8000,
            year_built="2000+",
            listing_type=("Market", "REO"),
        )
    )

    assert request.method == "GET"
    assert request.url.path == "/v1/properties/P-SYNTHETIC/comps/forsale"
    assert request.url.params.multi_items() == [
        ("Fields", "RadarID,ListingPrice"),
        ("Purchase", "0"),
        ("Limit", "9"),
        ("PType", "SFR,MFR"),
        ("Beds", "4"),
        ("Baths", "3+"),
        ("Units", "3"),
        ("SqFt", "2400"),
        ("LotSize", "8000"),
        ("YearBuilt", "2000+"),
        ("ListingType", "Market,REO"),
    ]


def test_parcels_and_transactions_requests() -> None:
    _, parcels_request = capture_request(
        lambda client: client.properties.parcels("P-SYNTHETIC")
    )
    _, transactions_request = capture_request(
        lambda client: client.properties.transactions(
            "P-SYNTHETIC",
            fields=("DocumentID", "RecDate"),
            filter_by="CurrentOwner",
        )
    )

    assert parcels_request.method == "GET"
    assert parcels_request.url.path == "/v1/properties/P-SYNTHETIC/parcels"
    assert parcels_request.url.params.multi_items() == [("Purchase", "0")]
    assert transactions_request.method == "GET"
    assert transactions_request.url.path == "/v1/properties/P-SYNTHETIC/transactions"
    assert transactions_request.url.params.multi_items() == [
        ("Fields", "DocumentID,RecDate"),
        ("Filter", "CurrentOwner"),
        ("Purchase", "0"),
    ]


PURCHASE_OPERATIONS: list[tuple[str, Operation]] = [
    (
        "get",
        lambda client: client.properties.get("P-SYNTHETIC", purchase=True),
    ),
    (
        "search",
        lambda client: client.properties.search(
            criteria=CRITERIA,
            purchase=True,
        ),
    ),
    (
        "persons",
        lambda client: client.properties.persons(
            "P-SYNTHETIC",
            purchase=True,
        ),
    ),
    (
        "evictions",
        lambda client: client.properties.evictions(
            "P-SYNTHETIC",
            purchase=True,
        ),
    ),
    (
        "comparable_sales",
        lambda client: client.properties.comparable_sales(
            "P-SYNTHETIC",
            purchase=True,
        ),
    ),
    (
        "comparable_listings",
        lambda client: client.properties.comparable_listings(
            "P-SYNTHETIC",
            purchase=True,
        ),
    ),
    (
        "parcels",
        lambda client: client.properties.parcels(
            "P-SYNTHETIC",
            purchase=True,
        ),
    ),
    (
        "transactions",
        lambda client: client.properties.transactions(
            "P-SYNTHETIC",
            purchase=True,
        ),
    ),
]


@pytest.mark.parametrize(("name", "operation"), PURCHASE_OPERATIONS)
def test_property_purchases_require_charge_opt_in_before_network_io(
    name: str,
    operation: Operation,
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"results": []})

    client, http_client = make_client(handler)

    with pytest.raises(ChargeNotAllowedError):
        operation(client)

    assert captured == [], name
    http_client.close()


def test_preview_search_is_retryable() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"message": "temporary"})
        return httpx.Response(
            200,
            json={"results": [{"RadarID": "P-SYNTHETIC"}]},
        )

    client, http_client = make_client(handler, max_retries=1)
    result = client.properties.search(criteria=CRITERIA)

    assert result["results"] == [{"RadarID": "P-SYNTHETIC"}]
    assert calls == 2
    http_client.close()


def test_purchased_search_is_not_retryable() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"message": "temporary"})

    client, http_client = make_client(
        handler,
        allow_charges=True,
        max_retries=2,
    )

    with pytest.raises(ServerError):
        client.properties.search(criteria=CRITERIA, purchase=True)

    assert calls == 1
    http_client.close()


def test_iter_search_advances_start_and_stops_on_short_page() -> None:
    starts: list[int] = []
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page_start = int(request.url.params["Start"])
        starts.append(page_start)
        if page_start == 5:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"RadarID": "P-SYNTHETIC-1"},
                        {"RadarID": "P-SYNTHETIC-2"},
                    ],
                    "totalResultCount": 20,
                },
            )
        return httpx.Response(
            200,
            json={"results": [{"RadarID": "P-SYNTHETIC-3"}]},
        )

    client, http_client = make_client(handler)
    records = list(
        client.properties.iter_search(
            criteria=CRITERIA,
            fields=("RadarID",),
            page_size=2,
            sort="RadarID ASC",
            start=5,
        )
    )

    assert [record["RadarID"] for record in records] == [
        "P-SYNTHETIC-1",
        "P-SYNTHETIC-2",
        "P-SYNTHETIC-3",
    ]
    assert starts == [5, 7]
    assert all(request.method == "POST" for request in requests)
    assert [request.url.params.multi_items() for request in requests] == [
        [
            ("Fields", "RadarID"),
            ("Limit", "2"),
            ("Sort", "RadarID ASC"),
            ("Start", "5"),
            ("Purchase", "0"),
        ],
        [
            ("Fields", "RadarID"),
            ("Limit", "2"),
            ("Sort", "RadarID ASC"),
            ("Start", "7"),
            ("Purchase", "0"),
        ],
    ]
    assert all(
        json.loads(request.content) == {"Criteria": CRITERIA} for request in requests
    )
    http_client.close()


def test_iter_search_stops_on_empty_page() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"results": []})

    client, http_client = make_client(handler)

    assert list(client.properties.iter_search(criteria=CRITERIA, page_size=2)) == []
    assert calls == 1
    http_client.close()


def test_iter_search_stops_at_total_result_count() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "results": [
                    {"RadarID": "P-SYNTHETIC-1"},
                    {"RadarID": "P-SYNTHETIC-2"},
                ],
                "totalResultCount": 2,
            },
        )

    client, http_client = make_client(handler)
    records = list(client.properties.iter_search(criteria=CRITERIA, page_size=2))

    assert len(records) == 2
    assert calls == 1
    http_client.close()


def test_iter_search_propagates_later_page_error() -> None:
    starts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page_start = int(request.url.params["Start"])
        starts.append(page_start)
        if page_start == 0:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"RadarID": "P-SYNTHETIC-1"},
                        {"RadarID": "P-SYNTHETIC-2"},
                    ]
                },
            )
        return httpx.Response(400, json={"message": "private vendor detail"})

    client, http_client = make_client(handler)
    records = client.properties.iter_search(criteria=CRITERIA, page_size=2)

    assert next(records)["RadarID"] == "P-SYNTHETIC-1"
    assert next(records)["RadarID"] == "P-SYNTHETIC-2"
    with pytest.raises(BadRequestError):
        next(records)
    assert starts == [0, 2]
    http_client.close()


@pytest.mark.parametrize(
    ("page_size", "max_results", "start", "message"),
    [
        (0, 1, 0, "page_size must be greater than zero"),
        (1, -1, 0, "max_results must be zero or greater"),
        (1, 1, -1, "start must be zero or greater"),
    ],
)
def test_iter_search_validates_pagination(
    page_size: int,
    max_results: int,
    start: int,
    message: str,
) -> None:
    client, http_client = make_client(
        lambda _: httpx.Response(500, json={"message": "must not be called"})
    )

    with pytest.raises(ValueError, match=message):
        list(
            client.properties.iter_search(
                criteria=CRITERIA,
                page_size=page_size,
                max_results=max_results,
                start=start,
            )
        )

    http_client.close()


def test_iter_search_honors_cap_without_overfetching() -> None:
    limits: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        limits.append(int(request.url.params["Limit"]))
        return httpx.Response(
            200,
            json={
                "results": [
                    {"RadarID": "P-SYNTHETIC-1"},
                    {"RadarID": "P-SYNTHETIC-2"},
                ],
                "totalResultCount": 20,
            },
        )

    client, http_client = make_client(handler)
    records = list(
        client.properties.iter_search(
            criteria=CRITERIA,
            page_size=10,
            max_results=2,
        )
    )

    assert [record["RadarID"] for record in records] == [
        "P-SYNTHETIC-1",
        "P-SYNTHETIC-2",
    ]
    assert limits == [2]
    http_client.close()


def test_iter_search_continues_after_short_page_when_total_reports_more() -> None:
    starts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page_start = int(request.url.params["Start"])
        starts.append(page_start)
        if page_start == 0:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"RadarID": "P-SYNTHETIC-1"},
                        {"RadarID": "P-SYNTHETIC-2"},
                    ],
                    "totalResultCount": 3,
                },
            )
        return httpx.Response(
            200,
            json={
                "results": [{"RadarID": "P-SYNTHETIC-3"}],
                "totalResultCount": 3,
            },
        )

    client, http_client = make_client(handler)
    records = list(
        client.properties.iter_search(
            criteria=CRITERIA,
            page_size=3,
            max_results=3,
        )
    )

    assert len(records) == 3
    assert starts == [0, 2]
    http_client.close()


def test_iter_search_rejects_unbounded_purchase_and_invalid_shapes() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"results": "not-a-list"})

    client, http_client = make_client(handler, allow_charges=True)
    with pytest.raises(ValueError, match="finite max_results"):
        list(
            client.properties.iter_search(
                criteria=CRITERIA,
                max_results=None,
                purchase=True,
            )
        )
    with pytest.raises(InvalidResponseError, match="search results"):
        list(client.properties.iter_search(criteria=CRITERIA))

    assert calls == 1
    http_client.close()


def test_iter_search_zero_cap_avoids_io_and_invalid_total_is_rejected() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "results": [{"RadarID": "P-SYNTHETIC"}],
                "totalResultCount": "invalid",
            },
        )

    client, http_client = make_client(handler)
    assert (
        list(
            client.properties.iter_search(
                criteria=CRITERIA,
                max_results=0,
            )
        )
        == []
    )
    with pytest.raises(InvalidResponseError, match="pagination"):
        list(
            client.properties.iter_search(
                criteria=CRITERIA,
                page_size=2,
                max_results=None,
            )
        )

    assert calls == 1
    http_client.close()


def test_property_ids_are_encoded_as_single_path_segments() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"results": []})

    client, http_client = make_client(handler)
    client.properties.get("P/segment?query#fragment")

    assert captured[0].url.raw_path == (
        b"/v1/properties/P%2Fsegment%3Fquery%23fragment?Purchase=0"
    )
    http_client.close()


@pytest.mark.parametrize("radar_id", ["", ".", ".."])
def test_property_ids_reject_invalid_path_segments(radar_id: str) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client, http_client = make_client(handler)
    with pytest.raises(ConfigurationError, match="path segment"):
        client.properties.get(radar_id)

    assert calls == 0
    http_client.close()


def test_property_get_error_is_propagated() -> None:
    client, http_client = make_client(
        lambda _: httpx.Response(404, json={"message": "private vendor detail"})
    )

    with pytest.raises(NotFoundError):
        client.properties.get("P-MISSING")

    http_client.close()
