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
