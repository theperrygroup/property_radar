from __future__ import annotations

import json
import socket
from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import NoReturn

import httpx
import pytest

from property_radar import (
    BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT,
    BUYER_TRANSFER_MATCH_CONTRACT,
    BUYER_TRANSFER_PROPERTY_FIELDS,
    PROPERTY_PERSON_IDENTITY_FIELDS,
    TRANSACTION_HISTORY_FIELDS,
    BuyerTransferMatchCriteria,
    BuyerTransferMatchResult,
    BuyerTransferRecordingDateRange,
    HistoricalBuyerTransferMatchResult,
    PropertyRadarClient,
    buyer_transfer_scope_fingerprint,
)
from property_radar.buyer_transfer import BUYER_TRANSFER_PREVIEW_FIELDS
from property_radar.exceptions import (
    BadRequestError,
    ChargeNotAllowedError,
    ConfigurationError,
    InvalidResponseError,
    NotFoundError,
    RateLimitError,
    ServerError,
)
from property_radar.types import Criterion, ResponseEnvelope

Handler = Callable[[httpx.Request], httpx.Response]
Operation = Callable[[PropertyRadarClient], ResponseEnvelope]
BuyerMatchResult = BuyerTransferMatchResult | HistoricalBuyerTransferMatchResult

CRITERIA: list[Criterion] = [
    {"name": "RadarID", "value": ["P-SYNTHETIC"]},
]


@pytest.fixture(autouse=True)
def _deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> NoReturn:
        raise AssertionError("synthetic tests must not open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


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


def test_typed_transaction_history_is_additive_and_requests_exact_fields() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "Grantor": "SYNTHETIC SELLER GROUP",
                        "Grantee": "SYNTHETIC BUYER GROUP",
                    }
                ],
                "totalCost": "0.25",
                "quantityFreeRemaining": 100,
                "resultCount": 1,
            },
        )

    client, http_client = make_client(handler)
    history = client.properties.transaction_history(
        "P-SYNTHETIC",
        filter_by="CurrentOwner",
    )

    assert history.billing_status == "preview"
    assert history.records[0].grantee_display == "SYNTHETIC BUYER GROUP"
    assert len(captured) == 1
    assert captured[0].url.params.multi_items() == [
        ("Fields", ",".join(TRANSACTION_HISTORY_FIELDS)),
        ("Filter", "CurrentOwner"),
        ("Purchase", "0"),
    ]
    http_client.close()


def test_typed_transaction_history_composes_prefetched_property_persons() -> None:
    persons = {
        "results": [
            {
                "RadarID": "P-SYNTHETIC",
                "PersonKey": "p-synthetic",
                "PersonType": "Person",
                "FirstName": "Synthetic",
                "LastName": "Purchaser",
            }
        ],
        "totalCost": "0.25",
        "quantityFreeRemaining": 100,
        "resultCount": 1,
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [{"Grantee": "SYNTHETIC PURCHASER GROUP"}],
                "totalCost": "0.25",
                "quantityFreeRemaining": 100,
                "resultCount": 1,
            },
        )

    client, http_client = make_client(handler)
    history = client.properties.transaction_history(
        "P-SYNTHETIC",
        property_persons=persons,
    )

    assert PROPERTY_PERSON_IDENTITY_FIELDS[0] == "RadarID"
    assert history.current_owners is not None
    assert history.current_owners[0].provider_id == "p-synthetic"
    assert history.records[0].grantees is None
    http_client.close()


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


def test_typed_transaction_purchase_requires_opt_in_and_is_never_retried() -> None:
    denied_calls = 0

    def denied_handler(_: httpx.Request) -> httpx.Response:
        nonlocal denied_calls
        denied_calls += 1
        return httpx.Response(200, json={})

    denied_client, denied_http_client = make_client(denied_handler, max_retries=2)
    with pytest.raises(ChargeNotAllowedError):
        denied_client.properties.transaction_history(
            "P-SYNTHETIC",
            purchase=True,
        )
    assert denied_calls == 0
    denied_http_client.close()

    charged_calls = 0

    def charged_handler(_: httpx.Request) -> httpx.Response:
        nonlocal charged_calls
        charged_calls += 1
        return httpx.Response(503, json={"message": "temporary"})

    charged_client, charged_http_client = make_client(
        charged_handler,
        allow_charges=True,
        max_retries=2,
    )
    with pytest.raises(ServerError):
        charged_client.properties.transaction_history(
            "P-SYNTHETIC",
            purchase=True,
        )
    assert charged_calls == 1
    charged_http_client.close()


@pytest.mark.parametrize("purchase", [1, 0, None, "true"])
def test_typed_transaction_rejects_non_boolean_purchase_before_network(
    purchase: object,
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client, http_client = make_client(handler, allow_charges=True)
    with pytest.raises(TypeError, match="purchase must be a boolean"):
        client.properties.transaction_history(
            "P-SYNTHETIC",
            purchase=purchase,  # type: ignore[arg-type]
        )
    assert calls == 0
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


# Buyer-transfer match through the typed resource methods (0.4.2 live shapes).

BUYER_MODES = ("recent", "historical")
PROPERTY_TYPE_CRITERION: Criterion = {
    "name": "PropertyType",
    "value": [{"name": "PType", "value": ["SFR", "CND", "MFR", "APT", "RES"]}],
}
EXPECTED_BUYER_CRITERIA: dict[str, list[Criterion]] = {
    "recent": [
        {"name": "State", "value": ["UT"]},
        {"name": "County", "value": [49035]},
        {"name": "Buyer", "value": ["Synthetic Adapter Buyer"]},
        {"name": "TransferPublishedDate", "value": ["Last 7 Days"]},
        PROPERTY_TYPE_CRITERION,
        {"name": "RadarID", "value": ["P-SYNTHETIC"]},
    ],
    "historical": [
        {"name": "State", "value": ["UT"]},
        {"name": "County", "value": [49035]},
        {"name": "Buyer", "value": ["Synthetic Adapter Buyer"]},
        {"name": "TransferRecDate", "value": ["from: 1/2/2023 to: 10/31/2023"]},
        PROPERTY_TYPE_CRITERION,
        {"name": "RadarID", "value": ["P-SYNTHETIC"]},
    ],
}
PREVIEW_PARAMS = [
    ("Fields", "RadarID"),
    ("Limit", "1"),
    ("Start", "0"),
    ("Purchase", "0"),
]
PAID_PARAMS = [
    (
        "Fields",
        "RadarID,PType,Address,City,State,ZipFive,County,FIPS,APN,Latitude,Longitude",
    ),
    ("Limit", "1"),
    ("Start", "0"),
    ("Purchase", "1"),
]


def buyer_criteria(mode: str) -> BuyerTransferMatchCriteria:
    # Built the way the theperrygroup adapter builds them: keywords only.
    if mode == "historical":
        return BuyerTransferMatchCriteria(
            buyer_name="Synthetic Adapter Buyer",
            radar_id="P-SYNTHETIC",
            state_code="UT",
            county_fips="49035",
            publication_window=None,
            recording_date_range=BuyerTransferRecordingDateRange(
                start=date(2023, 1, 2), end=date(2023, 10, 31)
            ),
        )
    return BuyerTransferMatchCriteria(
        buyer_name="Synthetic Adapter Buyer",
        radar_id="P-SYNTHETIC",
        state_code="UT",
        county_fips="49035",
    )


def call_buyer_match(
    client: PropertyRadarClient, mode: str, *, purchase: bool = False
) -> BuyerMatchResult:
    criteria = buyer_criteria(mode)
    if mode == "historical":
        return client.properties.historical_buyer_transfer_match(
            criteria=criteria, purchase=purchase
        )
    return client.properties.buyer_transfer_match(criteria=criteria, purchase=purchase)


def run_buyer_match(
    mode: str,
    responses: list[httpx.Response],
    *,
    purchase: bool = False,
    allow_charges: bool = False,
    max_retries: int = 0,
) -> tuple[BuyerMatchResult, list[httpx.Request]]:
    captured: list[httpx.Request] = []
    pending = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return pending.pop(0)

    client, http_client = make_client(
        handler, allow_charges=allow_charges, max_retries=max_retries
    )
    try:
        result = call_buyer_match(client, mode, purchase=purchase)
    finally:
        http_client.close()
    return result, captured


def live_bare_zero_hit_preview() -> dict[str, object]:
    # Exact live 0-hit POST /v1/properties?Purchase=0 body: no metadata at all.
    return {"results": []}


def live_one_hit_radar_id_only_preview() -> dict[str, object]:
    # Live 1-hit Fields=RadarID preview shape with a synthetic RadarID.
    return {
        "results": [{"RadarID": "P-SYNTHETIC"}],
        "totalCost": 0,
        "resultCount": 0,
        "totalResultCount": 1,
    }


def live_withheld_record_preview() -> dict[str, object]:
    return {
        "results": [],
        "totalCost": 0,
        "resultCount": 0,
        "totalResultCount": 1,
        "quantityFreeRemaining": 9866,
    }


def paid_buyer_envelope(mode: str, total_cost: object = 1) -> dict[str, object]:
    record: dict[str, object] = {
        "RadarID": "P-SYNTHETIC",
        "PType": "Single Family",
        "ZipFive": "84101" if mode == "historical" else 84101,
        "FIPS": "49035",
    }
    return {
        "results": [record],
        "totalCost": total_cost,
        "resultCount": 1,
        "totalResultCount": 1,
    }


def adapter_precheck(result: BuyerMatchResult, *, mode: str) -> str:
    # Mirrors the reads of theperrygroup's non-billable precheck.
    criteria = buyer_criteria(mode)
    if mode == "historical":
        if type(result) is not HistoricalBuyerTransferMatchResult:
            return "reject_result_type"
        contract = BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT
    else:
        if type(result) is not BuyerTransferMatchResult:
            return "reject_result_type"
        contract = BUYER_TRANSFER_MATCH_CONTRACT
    if result.contract_fingerprint != contract["contract_fingerprint"]:
        return "reject_contract_fingerprint"
    expected_scope = buyer_transfer_scope_fingerprint(criteria)
    if result.scope_fingerprint != expected_scope:
        return "reject_scope_fingerprint"
    billing = result.billing
    if (
        billing.purchase_requested is not False
        or billing.status != "preview"
        or billing.total_cost != Decimal("0")
        or billing.currency is not None
    ):
        return "reject_billing"
    if not result.matched:
        return "no_match"
    linkage = result.linkage
    if linkage is None or linkage.scope_fingerprint != expected_scope:
        return "reject_linkage_scope"
    if linkage.property.radar_id != criteria.radar_id:
        return "reject_radar_id"
    if linkage.property.fips is not None and (
        linkage.property.fips != criteria.county_fips
    ):
        return "reject_fips"
    if linkage.property.is_residential is True:
        return "paid_claim_allowed"
    if linkage.property.is_residential is False:
        return "non_residential"
    return "residential_unknown"


@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_preview_sends_radar_id_only_with_property_type_before_radar_id(
    mode: str,
) -> None:
    result, captured = run_buyer_match(
        mode, [httpx.Response(200, json=live_one_hit_radar_id_only_preview())]
    )

    assert result.matched is True
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/v1/properties"
    assert request.url.params.multi_items() == PREVIEW_PARAMS
    assert request.url.params["Fields"] == ",".join(BUYER_TRANSFER_PREVIEW_FIELDS)
    body = json.loads(request.content)
    assert body == {"Criteria": EXPECTED_BUYER_CRITERIA[mode]}
    assert body["Criteria"][-2] == PROPERTY_TYPE_CRITERION
    assert body["Criteria"][-1] == {"name": "RadarID", "value": ["P-SYNTHETIC"]}


@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_paid_call_sends_every_property_field_with_the_same_criteria(
    mode: str,
) -> None:
    _, preview_requests = run_buyer_match(
        mode, [httpx.Response(200, json=live_one_hit_radar_id_only_preview())]
    )
    paid, paid_requests = run_buyer_match(
        mode,
        [httpx.Response(200, json=paid_buyer_envelope(mode))],
        purchase=True,
        allow_charges=True,
    )

    assert paid.billing.status == "charged"
    assert paid.billing.purchase_requested is True
    assert paid.billing.total_cost == Decimal("1")
    assert len(paid_requests) == 1
    request = paid_requests[0]
    assert request.method == "POST"
    assert request.url.path == "/v1/properties"
    assert request.url.params.multi_items() == PAID_PARAMS
    assert request.url.params["Fields"] == ",".join(BUYER_TRANSFER_PROPERTY_FIELDS)
    assert json.loads(request.content) == {"Criteria": EXPECTED_BUYER_CRITERIA[mode]}
    assert json.loads(request.content) == json.loads(preview_requests[0].content)


@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_purchase_still_needs_allow_charges_before_the_network(
    mode: str,
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=paid_buyer_envelope(mode))

    client, http_client = make_client(handler, allow_charges=False, max_retries=3)
    try:
        with pytest.raises(ChargeNotAllowedError):
            call_buyer_match(client, mode, purchase=True)
    finally:
        http_client.close()
    assert calls == 0


@pytest.mark.parametrize(
    ("status_code", "error"),
    [(429, RateLimitError), (500, ServerError), (503, ServerError)],
)
@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_paid_request_is_never_retried(
    mode: str, status_code: int, error: type[Exception]
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["Purchase"] == "1"
        return httpx.Response(
            status_code,
            headers={"Retry-After": "0"},
            json={"message": "synthetic failure"},
        )

    client, http_client = make_client(handler, allow_charges=True, max_retries=3)
    try:
        with pytest.raises(error):
            call_buyer_match(client, mode, purchase=True)
    finally:
        http_client.close()
    assert calls == 1


@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_preview_request_keeps_its_safe_retry(mode: str) -> None:
    result, captured = run_buyer_match(
        mode,
        [
            httpx.Response(
                503, headers={"Retry-After": "0"}, json={"message": "synthetic"}
            ),
            httpx.Response(200, json=live_one_hit_radar_id_only_preview()),
        ],
        max_retries=1,
    )

    assert result.matched is True
    assert len(captured) == 2
    assert all(request.url.params["Purchase"] == "0" for request in captured)
    assert all(request.url.params["Fields"] == "RadarID" for request in captured)


@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_live_one_hit_radar_id_only_preview_is_a_residential_match(
    mode: str,
) -> None:
    result, _ = run_buyer_match(
        mode, [httpx.Response(200, json=live_one_hit_radar_id_only_preview())]
    )

    assert result.matched is True
    assert result.linkage is not None
    property_value = result.linkage.property
    assert property_value.radar_id == "P-SYNTHETIC"
    assert property_value.fips is None
    assert property_value.property_type is None
    assert property_value.is_residential is True
    assert property_value.residential_basis == "property_type_criterion"
    assert result.billing.total_cost == Decimal("0")
    assert result.billing.result_count == 0
    assert result.billing.total_result_count == 1


@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_live_bare_zero_hit_preview_is_a_no_match(mode: str) -> None:
    result, captured = run_buyer_match(
        mode, [httpx.Response(200, json=live_bare_zero_hit_preview())]
    )

    assert len(captured) == 1
    assert result.matched is False
    assert result.linkage is None
    assert result.billing.provider_metadata_omitted is True
    assert result.billing.quantity_free_remaining is None


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (live_withheld_record_preview(), "preview_record_withheld"),
        (
            {"results": [], "totalCost": 0, "resultCount": 0, "totalResultCount": 2},
            "total_result_count",
        ),
        (
            {
                "results": [{"RadarID": "P-SYNTHETIC"}],
                "totalCost": 0,
                "resultCount": 0,
                "totalResultCount": 2,
            },
            "total_result_count",
        ),
    ],
)
@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_withheld_and_multi_match_previews_fail_closed(
    mode: str, payload: dict[str, object], reason: str
) -> None:
    with pytest.raises(InvalidResponseError, match=rf"\({reason}\)") as caught:
        run_buyer_match(mode, [httpx.Response(200, json=payload)])
    assert "9866" not in str(caught.value)
    assert "P-SYNTHETIC" not in str(caught.value)


@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_bare_envelope_on_a_paid_call_fails_closed(mode: str) -> None:
    with pytest.raises(InvalidResponseError, match=r"\(required_envelope_fields\)"):
        run_buyer_match(
            mode,
            [httpx.Response(200, json=live_bare_zero_hit_preview())],
            purchase=True,
            allow_charges=True,
        )


@pytest.mark.parametrize(
    ("total_cost", "expected"),
    [
        (0, Decimal("0")),
        (2, Decimal("2")),
        (0.25, Decimal("0.25")),
        (1.0, Decimal("1.0")),
        ("3.50", Decimal("3.50")),
    ],
)
@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_total_cost_int_float_and_decimal_string_through_the_resource(
    mode: str, total_cost: object, expected: Decimal
) -> None:
    paid, _ = run_buyer_match(
        mode,
        [httpx.Response(200, json=paid_buyer_envelope(mode, total_cost))],
        purchase=True,
        allow_charges=True,
    )
    preview, _ = run_buyer_match(
        mode,
        [
            httpx.Response(
                200,
                json={**live_one_hit_radar_id_only_preview(), "totalCost": total_cost},
            )
        ],
    )

    assert type(paid.billing.total_cost) is Decimal
    assert paid.billing.total_cost == expected
    assert preview.billing.total_cost == expected


@pytest.mark.parametrize("total_cost", [True, None, -1, -0.0, 1e64, 10**64, "1e3"])
@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_invalid_total_cost_through_the_resource_fails_closed(
    mode: str, total_cost: object
) -> None:
    with pytest.raises(InvalidResponseError, match=r"\(total_cost\)"):
        run_buyer_match(
            mode,
            [httpx.Response(200, json=paid_buyer_envelope(mode, total_cost))],
            purchase=True,
            allow_charges=True,
        )


@pytest.mark.parametrize(
    ("token", "total_cost"),
    [("NaN", float("nan")), ("Infinity", float("inf")), ("-Infinity", float("-inf"))],
)
@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_non_finite_total_cost_token_through_the_resource_fails_closed(
    mode: str, token: str, total_cost: float
) -> None:
    # httpx refuses to encode NaN or Infinity, so the envelope goes out as raw
    # JSON text; the transport's JSON decoder reads these tokens as floats.
    body = json.dumps(paid_buyer_envelope(mode, total_cost))
    assert f'"totalCost": {token},' in body
    with pytest.raises(InvalidResponseError, match=r"\(total_cost\)"):
        run_buyer_match(
            mode,
            [
                httpx.Response(
                    200,
                    content=body.encode(),
                    headers={"content-type": "application/json"},
                )
            ],
            purchase=True,
            allow_charges=True,
        )


@pytest.mark.parametrize("property_type", ["Commercial", "Land", "Unknown"])
@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_returned_ptype_outside_the_residential_names_fails_closed(
    mode: str, property_type: str
) -> None:
    payload = paid_buyer_envelope(mode)
    payload["results"] = [{"RadarID": "P-SYNTHETIC", "PType": property_type}]
    with pytest.raises(
        InvalidResponseError, match=r"\(property_type_outside_criterion\)"
    ):
        run_buyer_match(
            mode,
            [httpx.Response(200, json=payload)],
            purchase=True,
            allow_charges=True,
        )


@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_scope_fingerprint_binds_the_preview_and_the_paid_result(
    mode: str,
) -> None:
    expected = buyer_transfer_scope_fingerprint(buyer_criteria(mode))
    preview, _ = run_buyer_match(
        mode, [httpx.Response(200, json=live_one_hit_radar_id_only_preview())]
    )
    paid, _ = run_buyer_match(
        mode,
        [httpx.Response(200, json=paid_buyer_envelope(mode))],
        purchase=True,
        allow_charges=True,
    )
    bare, _ = run_buyer_match(
        mode, [httpx.Response(200, json=live_bare_zero_hit_preview())]
    )

    for result in (preview, paid):
        assert result.scope_fingerprint == expected
        assert result.linkage is not None
        assert result.linkage.scope_fingerprint == expected
    assert bare.scope_fingerprint == expected
    assert paid.linkage is not None
    assert paid.linkage.property.residential_basis == "property_type"
    assert paid.linkage.property.is_residential is True


@pytest.mark.parametrize("mode", BUYER_MODES)
def test_adapter_precheck_reads_on_the_live_one_hit_preview(mode: str) -> None:
    result, _ = run_buyer_match(
        mode, [httpx.Response(200, json=live_one_hit_radar_id_only_preview())]
    )

    billing = result.billing
    assert billing.purchase_requested is False
    assert billing.status == "preview"
    assert billing.total_cost == Decimal("0")
    assert billing.currency is None
    assert result.matched is True
    assert result.linkage is not None
    assert result.linkage.property.is_residential is True
    assert adapter_precheck(result, mode=mode) == "paid_claim_allowed"


@pytest.mark.parametrize("mode", BUYER_MODES)
def test_adapter_precheck_reads_on_the_live_bare_zero_hit_preview(mode: str) -> None:
    result, _ = run_buyer_match(
        mode, [httpx.Response(200, json=live_bare_zero_hit_preview())]
    )

    billing = result.billing
    assert billing.purchase_requested is False
    assert billing.status == "preview"
    assert billing.total_cost == Decimal("0")
    assert billing.currency is None
    assert result.matched is False
    assert adapter_precheck(result, mode=mode) == "no_match"


@pytest.mark.parametrize("mode", BUYER_MODES)
def test_adapter_precheck_never_allows_a_paid_claim_on_a_paid_result(
    mode: str,
) -> None:
    paid, _ = run_buyer_match(
        mode,
        [httpx.Response(200, json=paid_buyer_envelope(mode))],
        purchase=True,
        allow_charges=True,
    )

    assert adapter_precheck(paid, mode=mode) == "reject_billing"


@pytest.mark.parametrize(
    "contract",
    [BUYER_TRANSFER_MATCH_CONTRACT, BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT],
)
def test_buyer_contracts_keep_the_values_the_adapter_checks(
    contract: Mapping[str, object],
) -> None:
    assert type(contract) is MappingProxyType
    assert contract["operation"] == "properties.search"
    assert contract["method"] == "POST"
    assert contract["path"] == "/v1/properties"
    assert contract["relationship"] == "provider_buyer_criterion_property_match"
    limitations = contract["provider_limitations"]
    assert type(limitations) is MappingProxyType
    assert limitations["matched_transaction_identifier"] is None
    assert limitations["matched_structured_grantees"] is None
    assert limitations["transaction_party_boundaries"] is None
    assert limitations["scalar_grantor_grantee_parsing"] is False
    fingerprint = contract["contract_fingerprint"]
    assert type(fingerprint) is str
    assert len(fingerprint) == 64
