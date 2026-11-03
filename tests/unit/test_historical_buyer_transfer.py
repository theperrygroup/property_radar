from __future__ import annotations

import hashlib
import json
import traceback
from collections.abc import Callable, Mapping
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from types import MappingProxyType

import httpx
import pytest

from property_radar import (
    BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT,
    BUYER_TRANSFER_MATCH_CONTRACT,
    BUYER_TRANSFER_PROPERTY_FIELDS,
    BuyerTransferMatchCriteria,
    BuyerTransferRecordingDateRange,
    ChargeNotAllowedError,
    InvalidResponseError,
    PropertyRadarClient,
    ServerError,
    build_buyer_transfer_match_criteria,
    buyer_transfer_scope_fingerprint,
    parse_buyer_transfer_match,
)


class DateSubclass(date):
    pass


def historical_criteria(**changes: object) -> BuyerTransferMatchCriteria:
    values: dict[str, object] = {
        "buyer_name": "Synthetic Historical Buyer",
        "radar_id": "P-SYNTHETIC-HISTORY",
        "state_code": "UT",
        "county_fips": "49035",
        "publication_window": None,
        "recording_date_range": BuyerTransferRecordingDateRange(
            start=date(2023, 1, 2), end=date(2023, 10, 31)
        ),
    }
    values.update(changes)
    return BuyerTransferMatchCriteria(**values)  # type: ignore[arg-type]


def historical_envelope(*, purchase: bool = False) -> dict[str, object]:
    result: dict[str, object] = {
        "results": [{"RadarID": "P-SYNTHETIC-HISTORY", "FIPS": "49035"}],
        "totalCost": "0.50",
        "resultCount": 1,
        "totalResultCount": 1,
    }
    if not purchase:
        result["quantityFreeRemaining"] = 99
    return result


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    allow_charges: bool = False,
    max_retries: int = 0,
) -> tuple[PropertyRadarClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PropertyRadarClient(
        api_key="synthetic-token",  # pragma: allowlist secret
        http_client=http_client,
        allow_charges=allow_charges,
        max_retries=max_retries,
    )
    return client, http_client


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2023, 5, 6), date(2023, 5, 6)),
        (date(2024, 1, 1), date(2024, 12, 31)),
        (date(2023, 1, 1), date(2024, 1, 1)),
        (date(2023, 1, 1), date(2024, 1, 2)),
        (date(2020, 1, 1), date(2025, 12, 31)),
        (date.min, date.max),
    ],
)
def test_recording_range_accepts_any_finite_ordered_date_boundaries(
    start: date, end: date
) -> None:
    value = BuyerTransferRecordingDateRange(start=start, end=end)

    assert value.start == start
    assert value.end == end


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (None, date(2023, 1, 2)),
        (date(2023, 1, 2), None),
        ("2023-01-01", date(2023, 1, 2)),
        (date(2023, 1, 1), "2023-01-02"),
        (datetime(2023, 1, 1), date(2023, 1, 2)),
        (date(2023, 1, 1), datetime(2023, 1, 2)),
        (DateSubclass(2023, 1, 1), date(2023, 1, 2)),
        (date(2023, 1, 1), DateSubclass(2023, 1, 2)),
        (True, date(2023, 1, 2)),
        (date(2023, 1, 1), 20230102),
        (date(2023, 1, 2), date(2023, 1, 1)),
    ],
)
def test_recording_range_rejects_invalid_open_or_reversed_boundaries(
    start: object, end: object
) -> None:
    with pytest.raises(ValueError):
        BuyerTransferRecordingDateRange(start=start, end=end)  # type: ignore[arg-type]


def test_recording_range_requires_both_boundaries() -> None:
    with pytest.raises(TypeError):
        BuyerTransferRecordingDateRange(start=date(2023, 1, 1))  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        BuyerTransferRecordingDateRange(end=date(2023, 1, 1))  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "change",
    [
        {"publication_window": "Last 7 Days"},
        {"publication_window": "Last 30 Days"},
        {"recording_window": "Last 30 Days"},
        {"recording_window": "Last 7 Days"},
        {"recording_date_range": (date(2023, 1, 1), date(2023, 2, 1))},
        {"recording_date_range": {"start": "2023-01-01", "end": "2023-02-01"}},
        {"recording_date_range": "from: 1/1/2023 to: 2/1/2023"},
        {"recording_date_range": None},
    ],
)
def test_historical_criteria_reject_mixed_or_missing_date_modes(
    change: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        historical_criteria(**change)


def test_historical_range_and_criteria_are_frozen_and_redacted() -> None:
    value = historical_criteria()
    date_range = value.recording_date_range
    assert date_range is not None

    with pytest.raises(FrozenInstanceError):
        date_range.start = date(2023, 2, 2)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        date_range.end = date(2023, 11, 1)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        value.recording_date_range = None  # type: ignore[misc]

    result = parse_buyer_transfer_match(historical_envelope(), criteria=value)
    for rendered in (repr(date_range), repr(value), repr(result), repr(result.linkage)):
        for private_value in (
            "Synthetic Historical Buyer",
            "P-SYNTHETIC-HISTORY",
            "49035",
            "2023",
            "1/2/2023",
            "10/31/2023",
            buyer_transfer_scope_fingerprint(value),
        ):
            assert private_value not in rendered


def test_historical_query_uses_exact_dates_and_omits_publication_filter() -> None:
    assert build_buyer_transfer_match_criteria(historical_criteria()) == (
        {"name": "State", "value": ["UT"]},
        {"name": "County", "value": [49035]},
        {"name": "Buyer", "value": ["Synthetic Historical Buyer"]},
        {"name": "TransferRecDate", "value": ["from: 1/2/2023 to: 10/31/2023"]},
        {"name": "RadarID", "value": ["P-SYNTHETIC-HISTORY"]},
    )
    most_recent = build_buyer_transfer_match_criteria(
        historical_criteria(most_recent_change_of_ownership_only=True)
    )
    assert most_recent[-2] == {"name": "isMostRecentMarketTransfer", "value": [1]}
    assert all(item["name"] != "TransferPublishedDate" for item in most_recent)


@pytest.mark.parametrize(
    ("start", "end", "provider_value"),
    [
        (date(2023, 5, 6), date(2023, 5, 6), "from: 5/6/2023 to: 5/6/2023"),
        (date.min, date.max, "from: 1/1/0001 to: 12/31/9999"),
    ],
)
def test_historical_query_preserves_full_inclusive_range(
    start: date, end: date, provider_value: str
) -> None:
    value = historical_criteria(
        recording_date_range=BuyerTransferRecordingDateRange(start=start, end=end)
    )
    assert build_buyer_transfer_match_criteria(value)[3] == {
        "name": "TransferRecDate",
        "value": [provider_value],
    }


def test_historical_scope_fingerprint_binds_each_date_boundary_and_mode() -> None:
    original = historical_criteria()
    earlier_start = replace(
        original,
        recording_date_range=BuyerTransferRecordingDateRange(
            start=date(2023, 1, 1), end=date(2023, 10, 31)
        ),
    )
    later_end = replace(
        original,
        recording_date_range=BuyerTransferRecordingDateRange(
            start=date(2023, 1, 2), end=date(2023, 11, 1)
        ),
    )
    recent = replace(
        original, publication_window="Last 7 Days", recording_date_range=None
    )
    assert (
        len(
            {
                buyer_transfer_scope_fingerprint(value)
                for value in (original, earlier_start, later_end, recent)
            }
        )
        == 4
    )
    assert buyer_transfer_scope_fingerprint(original) == (
        buyer_transfer_scope_fingerprint(historical_criteria())
    )


def test_historical_scope_hashes_mode_contract_and_iso_recording_boundaries() -> None:
    expected_payload = {
        "operation": "properties.search",
        "criteria": [
            {"name": "State", "value": ["UT"]},
            {"name": "County", "value": [49035]},
            {"name": "Buyer", "value": ["Synthetic Historical Buyer"]},
            {
                "name": "TransferRecDate",
                "value": ["from: 1/2/2023 to: 10/31/2023"],
            },
            {"name": "RadarID", "value": ["P-SYNTHETIC-HISTORY"]},
        ],
        "fields": BUYER_TRANSFER_PROPERTY_FIELDS,
        "limit": 1,
        "start": 0,
        "mode": "historical_recording_range",
        "contract_fingerprint": BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT[
            "contract_fingerprint"
        ],
        "recording_date_range": {"start": "2023-01-02", "end": "2023-10-31"},
    }
    encoded = json.dumps(
        expected_payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    assert buyer_transfer_scope_fingerprint(historical_criteria()) == (
        hashlib.sha256(encoded).hexdigest()
    )


def test_recent_scope_hashes_only_the_original_canonical_payload() -> None:
    value = BuyerTransferMatchCriteria(
        buyer_name="Synthetic Historical Buyer",
        radar_id="P-SYNTHETIC-HISTORY",
        state_code="UT",
        county_fips="49035",
        publication_window="Last 7 Days",
        recording_window="Last 30 Days",
        most_recent_change_of_ownership_only=True,
    )
    expected_payload = {
        "operation": "properties.search",
        "criteria": [
            {"name": "State", "value": ["UT"]},
            {"name": "County", "value": [49035]},
            {"name": "Buyer", "value": ["Synthetic Historical Buyer"]},
            {"name": "TransferPublishedDate", "value": ["Last 7 Days"]},
            {"name": "TransferRecDate", "value": ["Last 30 Days"]},
            {"name": "isMostRecentMarketTransfer", "value": [1]},
            {"name": "RadarID", "value": ["P-SYNTHETIC-HISTORY"]},
        ],
        "fields": BUYER_TRANSFER_PROPERTY_FIELDS,
        "limit": 1,
        "start": 0,
    }
    encoded = json.dumps(
        expected_payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    assert (
        buyer_transfer_scope_fingerprint(value) == hashlib.sha256(encoded).hexdigest()
    )


def thaw(value: object) -> object:
    if isinstance(value, Mapping):
        assert isinstance(value, MappingProxyType)
        return {key: thaw(nested) for key, nested in value.items()}
    if isinstance(value, tuple):
        return tuple(thaw(nested) for nested in value)
    assert not isinstance(value, list)
    return value


def test_historical_contract_is_versioned_immutable_and_independently_hashed() -> None:
    contract = BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT
    assert contract["contract_version"] == 1
    assert contract["mode"] == "historical_recording_range"
    assert contract["publication_window_values"] == ()
    assert contract["recording_window_values"] == ()
    assert contract["ordered_fields"] == BUYER_TRANSFER_PROPERTY_FIELDS
    criterion_order = contract["criterion_order"]
    assert isinstance(criterion_order, tuple)
    assert "TransferPublishedDate" not in criterion_order
    date_contract = contract["recording_date_range"]
    assert isinstance(date_contract, Mapping)
    assert date_contract["criterion"] == "TransferRecDate"
    assert date_contract["boundary_type"] == "date"
    assert date_contract["inclusive"] is True
    assert date_contract["format"] == "from: M/D/YYYY to: M/D/YYYY"
    assert date_contract["open_ended"] is False
    assert "maximum_days" not in date_contract
    source = thaw(contract)
    assert isinstance(source, dict)
    fingerprint = source.pop("contract_fingerprint")
    encoded = json.dumps(
        source, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    assert fingerprint == hashlib.sha256(encoded).hexdigest()
    assert fingerprint != BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"]


def test_recent_contract_and_positional_criteria_remain_compatible() -> None:
    value = BuyerTransferMatchCriteria(
        "Synthetic Historical Buyer",
        "P-SYNTHETIC-HISTORY",
        "UT",
        "49035",
        "Last 7 Days",
        "Last 30 Days",
        True,
    )
    assert value.recording_date_range is None
    assert build_buyer_transfer_match_criteria(value)[3:6] == (
        {"name": "TransferPublishedDate", "value": ["Last 7 Days"]},
        {"name": "TransferRecDate", "value": ["Last 30 Days"]},
        {"name": "isMostRecentMarketTransfer", "value": [1]},
    )
    assert BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"] == (
        # pragma: allowlist nextline secret
        "299cfaba5ddfc8337a290352433969f1f1363fa1a545080773761c2c99d2c8be"
    )
    result = parse_buyer_transfer_match(historical_envelope(), criteria=value)
    assert (
        result.contract_fingerprint
        == (BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"])
    )


@pytest.mark.parametrize("matched", [True, False])
def test_historical_parser_identifies_contract_for_match_and_no_match(
    matched: bool,
) -> None:
    payload = historical_envelope()
    if not matched:
        payload.update(results=[], resultCount=0, totalResultCount=0)
    value = historical_criteria()
    result = parse_buyer_transfer_match(
        payload, criteria=value, purchase_requested=False
    )
    assert result.matched is matched
    assert (
        result.contract_fingerprint
        == (BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT["contract_fingerprint"])
    )
    assert result.scope_fingerprint == buyer_transfer_scope_fingerprint(value)
    assert result.billing.status == "preview"
    if matched:
        assert result.linkage is not None
        assert result.linkage.scope_fingerprint == result.scope_fingerprint
        assert result.linkage.matched_transaction_identifier is None
        assert result.linkage.matched_grantees is None


def test_historical_parser_retains_exact_target_and_private_error_contract() -> None:
    payload = historical_envelope()
    payload["results"] = [{"RadarID": "P-SYNTHETIC-UNEXPECTED"}]
    with pytest.raises(InvalidResponseError) as caught:
        parse_buyer_transfer_match(payload, criteria=historical_criteria())

    formatted = "".join(traceback.format_exception(caught.value))
    assert "P-SYNTHETIC-UNEXPECTED" not in formatted
    assert "Synthetic Historical Buyer" not in formatted
    assert caught.value.__cause__ is None


def test_historical_preview_makes_one_bounded_mock_request() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=historical_envelope())

    client, http_client = make_client(handler)
    try:
        result = client.properties.buyer_transfer_match(criteria=historical_criteria())
    finally:
        http_client.close()

    assert (
        result.contract_fingerprint
        == (BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT["contract_fingerprint"])
    )
    assert result.billing.status == "preview"
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/v1/properties"
    assert request.url.params.multi_items() == [
        ("Fields", ",".join(BUYER_TRANSFER_PROPERTY_FIELDS)),
        ("Limit", "1"),
        ("Start", "0"),
        ("Purchase", "0"),
    ]
    assert json.loads(request.content) == {
        "Criteria": list(build_buyer_transfer_match_criteria(historical_criteria()))
    }


@pytest.mark.parametrize("purchase", [True, 1, 0, None, "true"])
def test_historical_purchase_preflight_never_reaches_transport(
    purchase: object,
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=historical_envelope(purchase=True))

    client, http_client = make_client(handler)
    try:
        error = ChargeNotAllowedError if purchase is True else TypeError
        with pytest.raises(error):
            client.properties.buyer_transfer_match(
                criteria=historical_criteria(),
                purchase=purchase,  # type: ignore[arg-type]
            )
    finally:
        http_client.close()
    assert calls == 0


def test_historical_paid_request_is_never_automatically_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["Purchase"] == "1"
        return httpx.Response(503, json={"message": "synthetic failure"})

    client, http_client = make_client(handler, allow_charges=True, max_retries=3)
    try:
        with pytest.raises(ServerError):
            client.properties.buyer_transfer_match(
                criteria=historical_criteria(), purchase=True
            )
    finally:
        http_client.close()
    assert calls == 1
