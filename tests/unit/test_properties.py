from __future__ import annotations

import json
import socket
from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import NoReturn, get_args, get_type_hints

import httpx
import pytest

from property_radar import (
    BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT,
    BUYER_TRANSFER_MATCH_CONTRACT,
    BUYER_TRANSFER_PROPERTY_FIELDS,
    PROPERTY_PERSON_IDENTITY_FIELDS,
    TRANSACTION_HISTORY_FIELDS,
    BuyerTransferBillingEvidence,
    BuyerTransferMatchCriteria,
    BuyerTransferMatchResult,
    BuyerTransferRecordingDateRange,
    HistoricalBuyerTransferMatchResult,
    PropertyRadarClient,
    build_buyer_transfer_match_criteria,
    buyer_transfer_scope_fingerprint,
)
from property_radar.buyer_transfer import (
    BUYER_TRANSFER_PREVIEW_FIELDS,
    BuyerTransferResponseError,
)
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


def test_response_envelope_types_total_cost_as_a_json_string_or_number() -> None:
    # A live preview sends totalCost as the JSON integer 0.
    hints = get_type_hints(ResponseEnvelope)
    assert set(get_args(hints["totalCost"])) == {str, int, float}


TOTAL_COST_ENVELOPES: list[ResponseEnvelope] = [
    {"results": [], "totalCost": 0},
    {"results": [], "totalCost": 0.25},
    {"results": [], "totalCost": "0.25"},
]


@pytest.mark.parametrize("envelope", TOTAL_COST_ENVELOPES)
def test_raw_search_returns_total_cost_with_its_json_type(
    envelope: ResponseEnvelope,
) -> None:
    result, _ = capture_request(
        lambda client: client.properties.search(criteria=CRITERIA),
        response=envelope,
    )

    assert result == envelope
    assert type(result["totalCost"]) is type(envelope["totalCost"])


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


TRANSACTION_HISTORY_ERROR = "PropertyRadar returned invalid transaction history ({})."


def synthetic_owner(**changes: object) -> dict[str, object]:
    owner: dict[str, object] = {
        "RadarID": "P-SYNTHETIC",
        "PersonKey": "p-synthetic",
        "PersonType": "Person",
        "FirstName": "Synthetic",
        "LastName": "Purchaser",
    }
    owner.update(changes)
    return owner


def paid_persons() -> dict[str, object]:
    return {
        "results": [synthetic_owner()],
        "totalCost": "0.25",
        "resultCount": 1,
        "totalResultCount": 1,
    }


def withheld_persons_preview() -> dict[str, object]:
    # A Purchase=0 persons response counts the owners and returns none of them.
    return {
        "results": [],
        "totalCost": 0,
        "quantityFreeRemaining": 9866,
        "resultCount": 2,
        "totalResultCount": 2,
    }


def transactions_envelope(*, purchase: bool) -> dict[str, object]:
    envelope: dict[str, object] = {
        "results": [{"Grantee": "SYNTHETIC PURCHASER GROUP"}],
        "totalCost": "0.25",
        "resultCount": 1,
    }
    if not purchase:
        envelope["quantityFreeRemaining"] = 100
    return envelope


def recording_transactions_client(
    *, purchase: bool
) -> tuple[PropertyRadarClient, httpx.Client, list[httpx.Request]]:
    # Charges are allowed, so a check that ran too late would reach the
    # transport and show up in the captured requests.
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=transactions_envelope(purchase=purchase))

    client, http_client = make_client(handler, allow_charges=True)
    return client, http_client, captured


@pytest.mark.parametrize("purchase", [False, True])
@pytest.mark.parametrize("with_persons", [False, True])
@pytest.mark.parametrize("flag", [0, 1, "no"])
def test_transaction_history_rejects_a_non_boolean_persons_purchase_flag(
    flag: object, with_persons: bool, purchase: bool
) -> None:
    client, http_client, captured = recording_transactions_client(purchase=purchase)
    try:
        with pytest.raises(
            TypeError,
            match="property_persons_purchase_requested must be a boolean or None",
        ):
            client.properties.transaction_history(
                "P-SYNTHETIC",
                purchase=purchase,
                property_persons=paid_persons() if with_persons else None,
                property_persons_purchase_requested=flag,  # type: ignore[arg-type]
            )
    finally:
        http_client.close()
    assert captured == []


@pytest.mark.parametrize("purchase", [False, True])
@pytest.mark.parametrize("flag", [False, True])
def test_transaction_history_persons_purchase_flag_requires_property_persons(
    flag: bool, purchase: bool
) -> None:
    client, http_client, captured = recording_transactions_client(purchase=purchase)
    try:
        with pytest.raises(
            ValueError,
            match="property_persons_purchase_requested requires property_persons",
        ) as caught:
            client.properties.transaction_history(
                "P-SYNTHETIC",
                purchase=purchase,
                property_persons_purchase_requested=flag,
            )
    finally:
        http_client.close()
    assert type(caught.value) is ValueError
    assert captured == []


INVALID_PROPERTY_PERSONS = [
    pytest.param(
        ["SYNTHETIC OWNER"], None, "property_persons_envelope_type", id="envelope"
    ),
    pytest.param({"results": [], 7: 0}, None, "property_persons_key_type", id="key"),
    pytest.param(
        {"results": [], "resultCount": 0, "nextPageToken": "synthetic"},
        None,
        "property_persons_undocumented_envelope_fields",
        id="undocumented_envelope_fields",
    ),
    pytest.param(
        {"results": {}, "resultCount": 0},
        None,
        "property_persons_results_type",
        id="results_type",
    ),
    pytest.param(
        {"results": ["SYNTHETIC OWNER"], "resultCount": 1},
        None,
        "property_person_type",
        id="person_type",
    ),
    pytest.param(
        {"results": [synthetic_owner(MailingCity="SYNTHETIC")], "resultCount": 1},
        None,
        "property_person_undocumented_fields",
        id="undocumented_person_fields",
    ),
    pytest.param(
        {"results": [synthetic_owner(FirstName=7)], "resultCount": 1},
        None,
        "property_person_field_type",
        id="person_field_type",
    ),
    pytest.param(
        {"results": [synthetic_owner(RadarID="P-OTHER")], "resultCount": 1},
        None,
        "property_person_radar_id_mismatch",
        id="person_radar_id_mismatch",
    ),
    pytest.param(
        {"results": [synthetic_owner(PersonType="Castle")], "resultCount": 1},
        None,
        "property_person_type_enum",
        id="person_type_enum",
    ),
    pytest.param(
        {"results": [], "resultCount": -1},
        None,
        "property_persons_result_count",
        id="result_count",
    ),
    pytest.param(
        {"results": [], "resultCount": 0, "totalResultCount": "0"},
        None,
        "property_persons_total_result_count",
        id="total_result_count",
    ),
    pytest.param(
        {"results": [synthetic_owner()], "resultCount": 1, "totalResultCount": 0},
        None,
        "property_persons_total_result_count_mismatch",
        id="total_below_result_count",
    ),
    pytest.param(
        {"results": [synthetic_owner()], "resultCount": 1, "totalResultCount": 2},
        True,
        "property_persons_total_result_count_mismatch",
        id="paid_total_above_the_people",
    ),
    pytest.param(
        {"results": [synthetic_owner()], "totalResultCount": 2},
        False,
        "property_persons_total_result_count_mismatch",
        id="preview_with_people_total_above_the_people",
    ),
    pytest.param(
        {"results": [synthetic_owner()], "resultCount": 2, "totalResultCount": 2},
        False,
        "property_persons_result_count_mismatch",
        id="preview_with_people_result_count",
    ),
    pytest.param(
        withheld_persons_preview(),
        None,
        "property_persons_result_count_mismatch",
        id="withheld_shape_detached",
    ),
    pytest.param(
        withheld_persons_preview(),
        True,
        "property_persons_result_count_mismatch",
        id="withheld_shape_paid",
    ),
    pytest.param(
        {"results": [], "totalCost": 0, "quantityFreeRemaining": 9866},
        False,
        "property_persons_preview_count_missing",
        id="preview_count_missing",
    ),
    pytest.param(
        {**paid_persons(), "totalCost": "-0.25"}, True, "total_cost", id="total_cost"
    ),
    pytest.param(
        {"results": [], "resultCount": 0, "quantityFreeRemaining": -1},
        None,
        "property_persons_quantity_free_remaining",
        id="quantity_free_remaining",
    ),
]


@pytest.mark.parametrize(("persons", "flag", "reason"), INVALID_PROPERTY_PERSONS)
@pytest.mark.parametrize("purchase", [False, True])
def test_transaction_history_rejects_invalid_persons_before_the_request(
    purchase: bool, persons: object, flag: bool | None, reason: str
) -> None:
    client, http_client, captured = recording_transactions_client(purchase=purchase)
    try:
        with pytest.raises(InvalidResponseError) as caught:
            client.properties.transaction_history(
                "P-SYNTHETIC",
                purchase=purchase,
                property_persons=persons,  # type: ignore[arg-type]
                property_persons_purchase_requested=flag,
            )
    finally:
        http_client.close()

    message = TRANSACTION_HISTORY_ERROR.format(reason)
    assert type(caught.value) is InvalidResponseError
    assert str(caught.value) == message
    assert caught.value.args == (message,)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
    # The persons data fails before the transactions request, paid or not.
    assert captured == []


@pytest.mark.parametrize("purchase", [False, True])
def test_transaction_history_rejects_a_non_string_radar_id_with_persons(
    purchase: bool,
) -> None:
    client, http_client, captured = recording_transactions_client(purchase=purchase)
    try:
        with pytest.raises(InvalidResponseError) as caught:
            client.properties.transaction_history(
                49035,  # type: ignore[arg-type]
                purchase=purchase,
                property_persons=paid_persons(),
            )
    finally:
        http_client.close()

    assert str(caught.value) == TRANSACTION_HISTORY_ERROR.format("composition_radar_id")
    assert captured == []


@pytest.mark.parametrize("radar_id", ["", ".", ".."])
def test_transaction_history_with_persons_keeps_the_path_segment_error(
    radar_id: str,
) -> None:
    client, http_client, captured = recording_transactions_client(purchase=False)
    try:
        with pytest.raises(ConfigurationError):
            client.properties.transaction_history(
                radar_id, property_persons=paid_persons()
            )
    finally:
        http_client.close()
    assert captured == []


@pytest.mark.parametrize("purchase", [False, True])
def test_transaction_history_reports_owners_withheld_by_a_persons_preview(
    purchase: bool,
) -> None:
    client, http_client, captured = recording_transactions_client(purchase=purchase)
    try:
        history = client.properties.transaction_history(
            "P-SYNTHETIC",
            purchase=purchase,
            property_persons=withheld_persons_preview(),
            property_persons_purchase_requested=False,
        )
    finally:
        http_client.close()

    assert history.current_owners is None
    assert history.current_owners_withheld is True
    assert "current_owners_withheld=True" in repr(history)
    assert history.billing_status == ("charged" if purchase else "preview")
    assert len(captured) == 1
    assert captured[0].url.params["Purchase"] == ("1" if purchase else "0")


VISIBLE_OWNER_PERSONS = [
    pytest.param(
        {
            "results": [],
            "totalCost": 0,
            "quantityFreeRemaining": 9866,
            "resultCount": 0,
            "totalResultCount": 0,
        },
        False,
        0,
        id="zero_count_preview",
    ),
    pytest.param(
        {
            "results": [synthetic_owner()],
            "totalCost": 0,
            "quantityFreeRemaining": 9866,
            "resultCount": 1,
            "totalResultCount": 1,
        },
        False,
        1,
        id="preview_with_an_owner",
    ),
    pytest.param(paid_persons(), True, 1, id="paid"),
    pytest.param(paid_persons(), None, 1, id="detached"),
]


@pytest.mark.parametrize(("persons", "flag", "owner_count"), VISIBLE_OWNER_PERSONS)
@pytest.mark.parametrize("purchase", [False, True])
def test_transaction_history_composes_the_visible_owners_for_each_persons_flag(
    purchase: bool, persons: dict[str, object], flag: bool | None, owner_count: int
) -> None:
    client, http_client, captured = recording_transactions_client(purchase=purchase)
    try:
        history = client.properties.transaction_history(
            "P-SYNTHETIC",
            purchase=purchase,
            property_persons=persons,
            property_persons_purchase_requested=flag,
        )
    finally:
        http_client.close()

    assert history.current_owners is not None
    provider_ids = [owner.provider_id for owner in history.current_owners]
    assert provider_ids == ["p-synthetic"] * owner_count
    assert history.current_owners_withheld is False
    assert "current_owners_withheld=False" in repr(history)
    assert len(captured) == 1


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
# A paid call (purchase=True) sends exactly the 0.4.1 criteria list.
EXPECTED_PAID_BUYER_CRITERIA: dict[str, list[Criterion]] = {
    "recent": [
        {"name": "State", "value": ["UT"]},
        {"name": "County", "value": [49035]},
        {"name": "Buyer", "value": ["Synthetic Adapter Buyer"]},
        {"name": "TransferPublishedDate", "value": ["Last 7 Days"]},
        {"name": "RadarID", "value": ["P-SYNTHETIC"]},
    ],
    "historical": [
        {"name": "State", "value": ["UT"]},
        {"name": "County", "value": [49035]},
        {"name": "Buyer", "value": ["Synthetic Adapter Buyer"]},
        {"name": "TransferRecDate", "value": ["from: 1/2/2023 to: 10/31/2023"]},
        {"name": "RadarID", "value": ["P-SYNTHETIC"]},
    ],
}
# A preview (purchase=False) inserts the PropertyType item just before RadarID.
EXPECTED_PREVIEW_BUYER_CRITERIA: dict[str, list[Criterion]] = {
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
RESIDENTIAL_PTYPE_NAMES = (
    "Single Family",
    "Condominium",
    "Multi-Family 2-4",
    "Multi-Family 5+",
    "Other Res.",
)
NON_RESIDENTIAL_PTYPE_NAMES = (
    "Commercial",
    "Industrial",
    "Agricultural",
    "Land",
    "Government",
    "Recreation",
    "Transport",
    "Utility",
    "Other",
)
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


def charged_billing_evidence(total_cost: Decimal) -> BuyerTransferBillingEvidence:
    return BuyerTransferBillingEvidence(
        purchase_requested=True,
        status="charged",
        total_cost=total_cost,
        currency=None,
        quantity_free_remaining=None,
        result_count=1,
        total_result_count=1,
    )


def criterion_names(request: httpx.Request) -> list[str]:
    return [item["name"] for item in json.loads(request.content)["Criteria"]]


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
    assert body == {"Criteria": EXPECTED_PREVIEW_BUYER_CRITERIA[mode]}
    assert body["Criteria"] == list(
        build_buyer_transfer_match_criteria(buyer_criteria(mode), preview=True)
    )
    assert criterion_names(request).count("PropertyType") == 1
    assert body["Criteria"][-2] == PROPERTY_TYPE_CRITERION
    assert body["Criteria"][-1] == {"name": "RadarID", "value": ["P-SYNTHETIC"]}


@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_paid_call_sends_every_property_field_and_the_0_4_1_criteria(
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
    paid_body = json.loads(request.content)
    assert paid_body == {"Criteria": EXPECTED_PAID_BUYER_CRITERIA[mode]}
    assert paid_body["Criteria"] == list(
        build_buyer_transfer_match_criteria(buyer_criteria(mode))
    )
    assert "PropertyType" not in criterion_names(request)
    # The preview of the same criteria differs only by the PropertyType item.
    preview_body = json.loads(preview_requests[0].content)
    assert [
        item for item in preview_body["Criteria"] if item != PROPERTY_TYPE_CRITERION
    ] == paid_body["Criteria"]


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
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
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
    assert len(captured) == 1
    assert captured[0].url.params["Purchase"] == "1"
    assert json.loads(captured[0].content) == {
        "Criteria": EXPECTED_PAID_BUYER_CRITERIA[mode]
    }


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
    assert all(
        json.loads(request.content)
        == {"Criteria": EXPECTED_PREVIEW_BUYER_CRITERIA[mode]}
        for request in captured
    )


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
    # A count rejection comes before the billing evidence exists.
    assert type(caught.value) is InvalidResponseError
    assert "9866" not in str(caught.value)
    assert "P-SYNTHETIC" not in str(caught.value)


@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_bare_envelope_on_a_paid_call_fails_closed(mode: str) -> None:
    with pytest.raises(
        InvalidResponseError, match=r"\(required_envelope_fields\)"
    ) as caught:
        run_buyer_match(
            mode,
            [httpx.Response(200, json=live_bare_zero_hit_preview())],
            purchase=True,
            allow_charges=True,
        )
    assert type(caught.value) is InvalidResponseError


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
    with pytest.raises(InvalidResponseError, match=r"\(total_cost\)") as caught:
        run_buyer_match(
            mode,
            [httpx.Response(200, json=paid_buyer_envelope(mode, total_cost))],
            purchase=True,
            allow_charges=True,
        )
    # Without a valid totalCost there is no billing evidence to attach.
    assert type(caught.value) is InvalidResponseError


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
    with pytest.raises(InvalidResponseError, match=r"\(total_cost\)") as caught:
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
    assert type(caught.value) is InvalidResponseError


@pytest.mark.parametrize(
    ("property_type", "is_residential"),
    [
        *((name, True) for name in RESIDENTIAL_PTYPE_NAMES),
        *((name, False) for name in NON_RESIDENTIAL_PTYPE_NAMES),
        ("Unknown", None),
    ],
)
@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_paid_call_classifies_the_returned_ptype_as_0_4_1_did(
    mode: str, property_type: str, is_residential: bool | None
) -> None:
    # The paid request carries no PropertyType criterion, so the provider can
    # return any documented type; the result classifies it and never raises.
    payload = paid_buyer_envelope(mode)
    payload["results"] = [{"RadarID": "P-SYNTHETIC", "PType": property_type}]
    paid, captured = run_buyer_match(
        mode,
        [httpx.Response(200, json=payload)],
        purchase=True,
        allow_charges=True,
    )

    assert len(captured) == 1
    assert "PropertyType" not in criterion_names(captured[0])
    assert paid.matched is True
    assert paid.billing.status == "charged"
    assert paid.linkage is not None
    property_value = paid.linkage.property
    assert property_value.property_type == property_type
    assert property_value.residential_basis == "property_type"
    assert property_value.is_residential is is_residential


@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_paid_call_without_a_ptype_leaves_the_classification_unknown(
    mode: str,
) -> None:
    payload = paid_buyer_envelope(mode)
    payload["results"] = [{"RadarID": "P-SYNTHETIC", "FIPS": "49035"}]
    paid, _ = run_buyer_match(
        mode,
        [httpx.Response(200, json=payload)],
        purchase=True,
        allow_charges=True,
    )

    assert paid.matched is True
    assert paid.linkage is not None
    property_value = paid.linkage.property
    assert property_value.property_type is None
    assert property_value.residential_basis is None
    assert property_value.is_residential is None


@pytest.mark.parametrize("property_type", RESIDENTIAL_PTYPE_NAMES)
@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_preview_with_a_residential_ptype_classifies_from_the_ptype(
    mode: str, property_type: str
) -> None:
    payload = {
        **live_one_hit_radar_id_only_preview(),
        "results": [{"RadarID": "P-SYNTHETIC", "PType": property_type}],
    }
    result, _ = run_buyer_match(mode, [httpx.Response(200, json=payload)])

    assert result.linkage is not None
    assert result.linkage.property.property_type == property_type
    assert result.linkage.property.residential_basis == "property_type"
    assert result.linkage.property.is_residential is True
    assert adapter_precheck(result, mode=mode) == "paid_claim_allowed"


@pytest.mark.parametrize("property_type", [*NON_RESIDENTIAL_PTYPE_NAMES, "Unknown"])
@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_preview_ptype_outside_the_criterion_fails_closed_with_evidence(
    mode: str, property_type: str
) -> None:
    payload = {
        **live_one_hit_radar_id_only_preview(),
        "quantityFreeRemaining": 9866,
        "results": [{"RadarID": "P-SYNTHETIC", "PType": property_type}],
    }
    with pytest.raises(BuyerTransferResponseError) as caught:
        run_buyer_match(mode, [httpx.Response(200, json=payload)])

    assert str(caught.value) == (
        "PropertyRadar returned invalid buyer-transfer match "
        "(property_type_outside_criterion)."
    )
    assert caught.value.billing_evidence == BuyerTransferBillingEvidence(
        purchase_requested=False,
        status="preview",
        total_cost=Decimal("0"),
        currency=None,
        quantity_free_remaining=9866,
        result_count=0,
        total_result_count=1,
    )
    assert property_type not in str(caught.value)
    assert "P-SYNTHETIC" not in str(caught.value)


PAID_RECORD_REJECTIONS = [
    pytest.param(
        {"RadarID": "P-OTHER", "PType": "Single Family"},
        "radar_id_mismatch",
        id="radar_id_mismatch",
    ),
    pytest.param(
        {"RadarID": "P-SYNTHETIC", "FIPS": "06037"}, "fips_mismatch", id="fips_mismatch"
    ),
    pytest.param(
        {"PType": "Single Family", "FIPS": "49035"},
        "missing_radar_id",
        id="missing_radar_id",
    ),
    pytest.param(
        {"RadarID": "P-SYNTHETIC", "OwnerName": "SYNTHETIC OWNER"},
        "undocumented_property_fields",
        id="undocumented_property_fields",
    ),
    pytest.param(["P-SYNTHETIC"], "property_type", id="record_not_an_object"),
    pytest.param({"RadarID": ""}, "radar_id", id="radar_id"),
    pytest.param(
        {"RadarID": "P-SYNTHETIC", "PType": "Castle"}, "property_type", id="ptype"
    ),
    pytest.param({"RadarID": "P-SYNTHETIC", "FIPS": "49O35"}, "fips", id="fips"),
    pytest.param({"RadarID": "P-SYNTHETIC", "ZipFive": "841"}, "zip_five", id="zip"),
    pytest.param({"RadarID": "P-SYNTHETIC", "Address": 7}, "address", id="address"),
    pytest.param({"RadarID": "P-SYNTHETIC", "APN": 7}, "apn", id="apn"),
    pytest.param({"RadarID": "P-SYNTHETIC", "Latitude": 91}, "latitude", id="lat"),
    pytest.param(
        {"RadarID": "P-SYNTHETIC", "Longitude": "-111.9"}, "longitude", id="lon"
    ),
]


@pytest.mark.parametrize(("record", "reason"), PAID_RECORD_REJECTIONS)
@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_paid_record_rejection_carries_the_billing_evidence(
    mode: str, record: object, reason: str
) -> None:
    payload = paid_buyer_envelope(mode, total_cost="2.50")
    payload["results"] = [record]
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=payload)

    client, http_client = make_client(handler, allow_charges=True, max_retries=3)
    try:
        with pytest.raises(BuyerTransferResponseError) as caught:
            call_buyer_match(client, mode, purchase=True)
    finally:
        http_client.close()

    error = caught.value
    message = f"PropertyRadar returned invalid buyer-transfer match ({reason})."
    assert isinstance(error, InvalidResponseError)
    assert str(error) == message
    assert error.args == (message,)
    assert type(error.billing_evidence) is BuyerTransferBillingEvidence
    assert error.billing_evidence == charged_billing_evidence(Decimal("2.50"))
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    for value in ("P-OTHER", "P-SYNTHETIC", "06037", "SYNTHETIC OWNER", "Castle"):
        assert value not in str(error)
        assert value not in repr(error)
    # The provider charged once; the rejected paid request is never retried.
    assert len(captured) == 1
    assert captured[0].url.params["Purchase"] == "1"


PAID_REJECTIONS_BEFORE_THE_BILLING_EVIDENCE = [
    pytest.param(
        {"results": [{"RadarID": "P-OTHER"}], "totalCost": "-1", "resultCount": 1},
        "required_envelope_fields",
        id="required_envelope_fields",
    ),
    pytest.param(
        {
            "results": [{"RadarID": "P-OTHER"}],
            "totalCost": "-1",
            "resultCount": 1,
            "totalResultCount": 1,
        },
        "total_cost",
        id="total_cost_before_the_record",
    ),
    pytest.param(
        {
            "results": [{"RadarID": "P-SYNTHETIC"}, {"RadarID": "P-OTHER"}],
            "totalCost": 2,
            "resultCount": 2,
            "totalResultCount": 2,
        },
        "ambiguous_results",
        id="ambiguous_results",
    ),
    pytest.param(
        {
            "results": [{"RadarID": "P-OTHER"}],
            "totalCost": 1,
            "resultCount": 0,
            "totalResultCount": 1,
        },
        "result_count_mismatch",
        id="result_count_mismatch",
    ),
    pytest.param(
        {
            "results": [{"RadarID": "P-OTHER"}],
            "totalCost": 1,
            "quantityFreeRemaining": 9866,
            "resultCount": 1,
            "totalResultCount": 1,
        },
        "charged_preview_metadata",
        id="charged_preview_metadata",
    ),
]


@pytest.mark.parametrize(
    ("payload", "reason"), PAID_REJECTIONS_BEFORE_THE_BILLING_EVIDENCE
)
@pytest.mark.parametrize("mode", BUYER_MODES)
def test_buyer_paid_rejection_before_the_billing_evidence_stays_plain(
    mode: str, payload: dict[str, object], reason: str
) -> None:
    with pytest.raises(InvalidResponseError) as caught:
        run_buyer_match(
            mode,
            [httpx.Response(200, json=payload)],
            purchase=True,
            allow_charges=True,
        )

    assert type(caught.value) is InvalidResponseError
    assert str(caught.value) == (
        f"PropertyRadar returned invalid buyer-transfer match ({reason})."
    )
    assert not hasattr(caught.value, "billing_evidence")


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
