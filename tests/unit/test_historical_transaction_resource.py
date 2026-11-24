from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import httpx
import pytest

from property_radar import (
    HISTORICAL_TRANSACTION_FIELDS,
    ChargeNotAllowedError,
    HistoricalTransactionDateRange,
    HistoricalTransactionQuery,
    HistoricalTransactionQuote,
    HistoricalTransactionResponseError,
    HistoricalTransactionResult,
    PropertyRadarClient,
    ServerError,
)


def query() -> HistoricalTransactionQuery:
    return HistoricalTransactionQuery(
        radar_id="P-SYNTHETIC",
        recording_dates=HistoricalTransactionDateRange(
            start=date(2023, 1, 1), end=date(2024, 12, 31)
        ),
        limit=2,
        doc_types=("GRT", "WRT"),
        doc_groups=("Deed",),
    )


def make_client(
    handler: Callable[[httpx.Request], httpx.Response], *, allow_charges: bool = False
) -> tuple[PropertyRadarClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return (
        PropertyRadarClient(
            api_key="synthetic-token",  # pragma: allowlist secret
            http_client=http_client,
            allow_charges=allow_charges,
            max_retries=3,
        ),
        http_client,
    )


def json_response(body: str) -> httpx.Response:
    """Return a 200 response that carries the exact JSON wire text."""
    return httpx.Response(
        200,
        content=body.encode("ascii"),
        headers={"Content-Type": "application/json"},
    )


def live_preview_body(total_cost: str = "0") -> str:
    """Return the exact live Purchase=0 transactions body with one totalCost token."""
    return (
        '{"results":[],"totalCost":'
        + total_cost
        + ',"quantityFreeRemaining":9866,"resultCount":2,"totalResultCount":2}'
    )


def paid_body(total_cost: str) -> str:
    """Return a synthetic Purchase=1 body with two rows and one totalCost token."""
    return (
        '{"results":[{"RadarID":"P-SYNTHETIC","DocumentID":"D-SYNTHETIC-1"},'
        '{"RadarID":"P-SYNTHETIC","DocumentID":"D-SYNTHETIC-2"}],'
        '"resultCount":2,"totalResultCount":3,"totalCost":' + total_cost + "}"
    )


# JSON wire tokens for totalCost that 0.4.2 accepts, and the exact Decimal each
# one must become after the transport's stdlib JSON decode.
ACCEPTED_WIRE_TOTAL_COSTS = [
    pytest.param("0", Decimal("0"), id="json-int-zero-live"),
    pytest.param("12", Decimal("12"), id="json-int"),
    pytest.param("0.5", Decimal("0.5"), id="json-float-half"),
    pytest.param("1.25", Decimal("1.25"), id="json-float"),
    pytest.param("1.5", Decimal("1.5"), id="json-float-one-and-a-half"),
    pytest.param("0.1", Decimal("0.1"), id="json-float-repr-not-binary"),
    pytest.param(
        "0.30000000000000004",
        Decimal("0.30000000000000004"),
        id="json-float-17-significant-digits",
    ),
    # D9: JSON decoding can round a fraction with more than 15 significant
    # digits to the nearest float before the library sees it; no rejection.
    pytest.param(
        "0.300000000000000044",
        Decimal("0.30000000000000004"),
        id="json-float-18-significant-digits-rounded-by-json-decoding",
    ),
    pytest.param(
        "123456789012345678901234567890",
        Decimal("123456789012345678901234567890"),
        id="json-long-int-stays-exact",
    ),
    pytest.param("1e-7", Decimal("1E-7"), id="json-float-exponent-form"),
    pytest.param('"3.50"', Decimal("3.50"), id="json-decimal-string"),
]
# JSON wire tokens for totalCost that 0.4.2 still rejects with total_cost.
REJECTED_WIRE_TOTAL_COSTS = [
    pytest.param("true", id="json-true"),
    pytest.param("false", id="json-false"),
    pytest.param("null", id="json-null"),
    pytest.param("NaN", id="json-nan-token"),
    pytest.param("Infinity", id="json-infinity-token"),
    pytest.param("-Infinity", id="json-negative-infinity-token"),
    pytest.param("1E400", id="json-float-overflow-to-infinity"),
    pytest.param("-1", id="json-negative-int"),
    pytest.param("-0.5", id="json-negative-float"),
    pytest.param("-0.0", id="json-negative-zero-float"),
    pytest.param("1" + "0" * 64, id="json-int-65-digits"),
    pytest.param('"' + "1" * 65 + '"', id="json-string-65-characters"),
    pytest.param("1e300", id="json-float-301-character-plain-form"),
    pytest.param("[]", id="json-array"),
    pytest.param("{}", id="json-object"),
]


def test_live_transactions_preview_envelope_with_json_int_total_cost_is_a_quote() -> (
    None
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(live_preview_body())

    requested = query()
    client, transport = make_client(handler)
    try:
        quote = client.properties.historical_transaction_history(
            query=requested, purchase=False
        )
    finally:
        transport.close()

    assert isinstance(quote, HistoricalTransactionQuote)
    assert type(quote.total_cost) is Decimal
    assert quote.total_cost == Decimal("0")
    assert quote.total_cost.as_tuple() == Decimal("0").as_tuple()
    assert quote.result_count == 2
    assert quote.total_result_count == 2
    assert quote.quantity_free_remaining == 9866
    assert quote.truncated is False
    assert quote.purchase_requested is False
    assert quote.scope_fingerprint == requested.scope_fingerprint
    assert not hasattr(quote, "records")
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/v1/properties/P-SYNTHETIC/transactions"
    assert requests[0].url.params["Purchase"] == "0"


@pytest.mark.parametrize(("total_cost", "expected"), ACCEPTED_WIRE_TOTAL_COSTS)
def test_live_preview_envelope_quotes_each_accepted_wire_total_cost_exactly(
    total_cost: str, expected: Decimal
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(live_preview_body(total_cost))

    client, transport = make_client(handler)
    try:
        quote = client.properties.historical_transaction_history(query=query())
    finally:
        transport.close()

    assert isinstance(quote, HistoricalTransactionQuote)
    assert type(quote.total_cost) is Decimal
    assert quote.total_cost == expected
    assert quote.total_cost.as_tuple() == expected.as_tuple()
    assert quote.result_count == 2
    assert quote.total_result_count == 2
    assert len(requests) == 1


@pytest.mark.parametrize("total_cost", REJECTED_WIRE_TOTAL_COSTS)
def test_live_preview_envelope_rejects_each_invalid_wire_total_cost(
    total_cost: str,
) -> None:
    requests: list[httpx.Request] = []
    requested = query()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(live_preview_body(total_cost))

    client, transport = make_client(handler)
    try:
        with pytest.raises(
            HistoricalTransactionResponseError, match=r"\(total_cost\)"
        ) as captured:
            client.properties.historical_transaction_history(query=requested)
    finally:
        transport.close()

    evidence = captured.value.billing_evidence
    assert evidence.purchase_requested is False
    assert evidence.scope_fingerprint == requested.scope_fingerprint
    assert evidence.total_cost is None
    assert evidence.result_count == 2
    assert evidence.total_result_count == 2
    assert len(requests) == 1


@pytest.mark.parametrize(
    ("total_cost", "expected"),
    [
        pytest.param("0", Decimal("0"), id="json-int-zero"),
        pytest.param("12", Decimal("12"), id="json-int"),
        pytest.param("1.25", Decimal("1.25"), id="json-float"),
        pytest.param("1.5", Decimal("1.5"), id="json-float-one-and-a-half"),
        pytest.param("0.1", Decimal("0.1"), id="json-float-one-tenth"),
        pytest.param(
            "0.30000000000000004",
            Decimal("0.30000000000000004"),
            id="json-float-17-significant-digits",
        ),
        pytest.param('"0.75"', Decimal("0.75"), id="json-decimal-string"),
    ],
)
def test_paid_selection_accepts_json_int_float_and_decimal_string_costs(
    total_cost: str, expected: Decimal
) -> None:
    requests: list[httpx.Request] = []
    requested = query()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(paid_body(total_cost))

    client, transport = make_client(handler, allow_charges=True)
    try:
        result = client.properties.historical_transaction_history(
            query=requested, purchase=True
        )
    finally:
        transport.close()

    assert isinstance(result, HistoricalTransactionResult)
    assert len(result.records) == 2
    assert type(result.total_cost) is Decimal
    assert result.total_cost.as_tuple() == expected.as_tuple()
    assert result.scope_fingerprint == requested.scope_fingerprint
    assert result.purchase_requested is True
    assert len(requests) == 1
    assert requests[0].url.params["Purchase"] == "1"


@pytest.mark.parametrize(
    "total_cost",
    [
        pytest.param("NaN", id="json-nan-token"),
        pytest.param("Infinity", id="json-infinity-token"),
        pytest.param("true", id="json-true"),
        pytest.param("-1", id="json-negative-int"),
        pytest.param("-0.0", id="json-negative-zero-float"),
    ],
)
def test_paid_selection_rejects_invalid_wire_cost_with_evidence_and_no_retry(
    total_cost: str,
) -> None:
    requests: list[httpx.Request] = []
    requested = query()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(paid_body(total_cost))

    client, transport = make_client(handler, allow_charges=True)
    try:
        with pytest.raises(
            HistoricalTransactionResponseError, match=r"\(total_cost\)"
        ) as captured:
            client.properties.historical_transaction_history(
                query=requested, purchase=True
            )
    finally:
        transport.close()

    evidence = captured.value.billing_evidence
    assert evidence.purchase_requested is True
    assert evidence.scope_fingerprint == requested.scope_fingerprint
    assert evidence.total_cost is None
    assert evidence.result_count == 2
    assert evidence.total_result_count == 3
    assert not hasattr(captured.value, "records")
    assert len(requests) == 1


def test_default_preview_quotes_bounded_rows_without_requiring_returned_records() -> (
    None
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "resultCount": 2,
                "totalResultCount": 3,
                "totalCost": "1.00",
                "quantityFreeRemaining": 99,
            },
        )

    client, transport = make_client(handler)
    try:
        quote = client.properties.historical_transaction_history(query=query())
    finally:
        transport.close()

    assert isinstance(quote, HistoricalTransactionQuote)
    assert quote.result_count == 2
    assert quote.total_result_count == 3
    assert quote.total_cost == Decimal("1.00")
    assert quote.truncated is True
    assert quote.purchase_requested is False
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert request.url.path == "/v1/properties/P-SYNTHETIC/transactions"
    assert dict(request.url.params) == {
        "Fields": ",".join(HISTORICAL_TRANSACTION_FIELDS),
        "Purchase": "0",
        "Filter": "All",
        "RecDate": "from: 01/01/2023 to: 12/31/2024",
        "Limit": "2",
        "DocType": "GRT,WRT",
        "DocGroup": "Deed",
    }


def test_explicit_paid_selection_retains_multiple_rows_and_exact_query_scope() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"RadarID": "P-SYNTHETIC", "DocumentID": "D-SYNTHETIC-1"},
                    {"RadarID": "P-SYNTHETIC", "DocumentID": "D-SYNTHETIC-2"},
                ],
                "resultCount": 2,
                "totalResultCount": 3,
                "totalCost": "1.00",
            },
        )

    requested = query()
    client, transport = make_client(handler, allow_charges=True)
    try:
        result = client.properties.historical_transaction_history(
            query=requested, purchase=True
        )
    finally:
        transport.close()

    assert isinstance(result, HistoricalTransactionResult)
    assert len(result.records) == 2
    assert result.total_cost == Decimal("1.00")
    assert result.scope_fingerprint == requested.scope_fingerprint
    assert result.truncated is True
    assert result.purchase_requested is True
    assert len(requests) == 1
    assert requests[0].url.params["Purchase"] == "1"


@pytest.mark.parametrize("purchase", [1, 0, "true", None])
def test_non_boolean_purchase_is_rejected_before_transport(purchase: object) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    client, transport = make_client(handler, allow_charges=True)
    try:
        with pytest.raises(TypeError, match="purchase"):
            client.properties.historical_transaction_history(
                query=query(),
                purchase=purchase,  # type: ignore[call-overload]
            )
    finally:
        transport.close()
    assert not requests


def test_invalid_query_is_rejected_before_transport() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    client, transport = make_client(handler)
    try:
        with pytest.raises(TypeError, match="query"):
            client.properties.historical_transaction_history(query=object())  # type: ignore[call-overload]
    finally:
        transport.close()
    assert not requests


def test_paid_selection_requires_client_opt_in_before_transport() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    client, transport = make_client(handler)
    try:
        with pytest.raises(ChargeNotAllowedError):
            client.properties.historical_transaction_history(
                query=query(), purchase=True
            )
    finally:
        transport.close()
    assert not requests


def test_paid_selection_never_retries_a_server_failure() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503, json={"message": "synthetic failure"})

    client, transport = make_client(handler, allow_charges=True)
    try:
        with pytest.raises(ServerError):
            client.properties.historical_transaction_history(
                query=query(), purchase=True
            )
    finally:
        transport.close()
    assert len(requests) == 1


def test_partial_paid_response_retains_safe_billing_evidence_without_retry() -> None:
    requests: list[httpx.Request] = []
    requested = query()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [{"RadarID": "P-SYNTHETIC"}],
                "resultCount": 2,
                "totalResultCount": 2,
                "totalCost": "0.75",
            },
        )

    client, transport = make_client(handler, allow_charges=True)
    try:
        with pytest.raises(HistoricalTransactionResponseError) as captured:
            client.properties.historical_transaction_history(
                query=requested, purchase=True
            )
    finally:
        transport.close()

    evidence = captured.value.billing_evidence
    assert evidence.purchase_requested is True
    assert evidence.scope_fingerprint == requested.scope_fingerprint
    assert evidence.total_cost == Decimal("0.75")
    assert evidence.result_count == 2
    assert evidence.total_result_count == 2
    assert "P-SYNTHETIC" not in repr(evidence)
    assert not hasattr(captured.value, "records")
    assert not hasattr(captured.value, "envelope")
    traceback = captured.value.__traceback__
    while traceback is not None:
        frame = traceback.tb_frame
        if frame.f_code.co_name == "historical_transaction_history":
            assert "envelope" not in frame.f_locals
            assert "query" not in frame.f_locals
        traceback = traceback.tb_next
    assert len(requests) == 1
