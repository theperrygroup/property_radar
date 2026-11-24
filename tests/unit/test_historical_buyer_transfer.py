from __future__ import annotations

import hashlib
import json
import re
import socket
import traceback
from collections.abc import Callable, Iterator, Mapping
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import NoReturn

import httpx
import pytest

from property_radar import (
    BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT,
    BUYER_TRANSFER_MATCH_CONTRACT,
    BUYER_TRANSFER_PROPERTY_FIELDS,
    BuyerTransferBillingEvidence,
    BuyerTransferMatchCriteria,
    BuyerTransferMatchResult,
    BuyerTransferRecordingDateRange,
    ChargeNotAllowedError,
    HistoricalBuyerTransferLinkage,
    HistoricalBuyerTransferMatchResult,
    HistoricalBuyerTransferProperty,
    InvalidResponseError,
    PropertyRadarClient,
    ServerError,
    build_buyer_transfer_match_criteria,
    buyer_transfer_scope_fingerprint,
    parse_buyer_transfer_match,
    parse_historical_buyer_transfer_match,
)
from property_radar.buyer_transfer import (
    BUYER_TRANSFER_PREVIEW_FIELDS,
    BUYER_TRANSFER_RESIDENTIAL_PTYPE_CODES,
    BuyerTransferResponseError,
)
from property_radar.types import Criterion

# The 0.4.1 values that theperrygroup pins until it adopts 0.4.2.
RECENT_CONTRACT_FINGERPRINT_0_4_1 = (
    # pragma: allowlist nextline secret
    "299cfaba5ddfc8337a290352433969f1f1363fa1a545080773761c2c99d2c8be"
)
HISTORICAL_CONTRACT_FINGERPRINT_0_4_1 = (
    # pragma: allowlist nextline secret
    "5fae2c3bd113264a7fbed5bdd7c80278787acd279f567e0f629c09f0ef58ee52"
)
# The branch values that sent PropertyType on paid requests too (before D4).
HISTORICAL_CONTRACT_FINGERPRINT_PAID_PROPERTY_TYPE = (
    # pragma: allowlist nextline secret
    "ba879d4c9cf0e6c6ce662cd7bb04c7bf6d794435c5e0e98285ac14732bd47bb2"
)
RECENT_CONTRACT_FINGERPRINT_PAID_PROPERTY_TYPE = (
    # pragma: allowlist nextline secret
    "0406f8ca5636c36eb834b273a4bc401293d52a91d34854874ad790a6edb12eeb"
)
HISTORICAL_SCOPE_FINGERPRINT_PAID_PROPERTY_TYPE = (
    # pragma: allowlist nextline secret
    "53ab93b32c9db877a650f3fb8af8ea2c2a0d928a1ba8997de84b763a16f34423"
)
RECENT_MOST_RECENT_SCOPE_FINGERPRINT_PAID_PROPERTY_TYPE = (
    # pragma: allowlist nextline secret
    "c7fcc5dcf0b151c8713b78887cf6452f32ebbc078a91ba54f73abab938db63b9"
)
# The current values: one scope fingerprint covers the preview and paid parse.
HISTORICAL_CONTRACT_FINGERPRINT = (
    # pragma: allowlist nextline secret
    "61ab6cc9e609ad3082124e1bc520c9578760a75ddff0ba989c714c72dcbfc906"
)
RECENT_CONTRACT_FINGERPRINT = (
    # pragma: allowlist nextline secret
    "580b955265f3f7928ea1bddba03e7244ceaff8f27fd6844343e05d6ae81bc01c"
)
HISTORICAL_SCOPE_FINGERPRINT = (
    # pragma: allowlist nextline secret
    "2825e8747b930e40b374194bf7d475031ca181d04e2cc928f7c4d9c40c9f9000"
)
RECENT_MOST_RECENT_SCOPE_FINGERPRINT = (
    # pragma: allowlist nextline secret
    "6ebdcd5a7e03b1afefbbfcac1f180f56b1f5eb5c9f05cf9b41a31f84df29e8de"
)
PROPERTY_TYPE_CRITERION: Criterion = {
    "name": "PropertyType",
    "value": [{"name": "PType", "value": ["SFR", "CND", "MFR", "APT", "RES"]}],
}
RESIDENTIAL_PROPERTY_TYPES = (
    "Single Family",
    "Condominium",
    "Multi-Family 2-4",
    "Multi-Family 5+",
    "Other Res.",
)
NON_RESIDENTIAL_PROPERTY_TYPES = (
    "Commercial",
    "Industrial",
    "Agricultural",
    "Land",
    "Government",
    "Recreation",
    "Transport",
    "Utility",
    "Other",
    "Unknown",
)
FIELDS_WITHOUT_PROPERTY_TYPE = tuple(
    field_name for field_name in BUYER_TRANSFER_PROPERTY_FIELDS if field_name != "PType"
)
DOCUMENTED_NON_RESIDENTIAL_PROPERTY_TYPES = tuple(
    name for name in NON_RESIDENTIAL_PROPERTY_TYPES if name != "Unknown"
)
# The 0.4.1 historical query: paid requests send no PropertyType criterion.
HISTORICAL_PAID_CRITERIA: tuple[Criterion, ...] = (
    {"name": "State", "value": ["UT"]},
    {"name": "County", "value": [49035]},
    {"name": "Buyer", "value": ["Synthetic Historical Buyer"]},
    {"name": "TransferRecDate", "value": ["from: 1/2/2023 to: 10/31/2023"]},
    {"name": "RadarID", "value": ["P-SYNTHETIC-HISTORY"]},
)
HISTORICAL_PREVIEW_CRITERIA: tuple[Criterion, ...] = (
    *HISTORICAL_PAID_CRITERIA[:-1],
    PROPERTY_TYPE_CRITERION,
    HISTORICAL_PAID_CRITERIA[-1],
)
HISTORICAL_CRITERION_ORDER = (
    "State",
    "County",
    "Buyer",
    "TransferRecDate",
    "isMostRecentMarketTransfer",
    "RadarID",
)
HISTORICAL_PREVIEW_CRITERION_ORDER = (
    *HISTORICAL_CRITERION_ORDER[:-1],
    "PropertyType",
    "RadarID",
)
RECORD_REJECTION_REASONS = (
    "property_type",
    "property_snapshot",
    "property_key_type",
    "undocumented_property_fields",
    "missing_radar_id",
    "radar_id",
    "radar_id_mismatch",
    "fips",
    "fips_mismatch",
    "property_type_outside_criterion",
    "address",
    "city",
    "state",
    "zip_five",
    "county",
    "apn",
    "latitude",
    "longitude",
)
RESIDENTIAL_CLASSIFICATION_POLICY = {
    "preview": {
        "property_type_returned": {
            "residential_basis": "property_type",
            "allowed_values": RESIDENTIAL_PROPERTY_TYPES,
            "is_residential": True,
            "outside_criterion_reason": "property_type_outside_criterion",
        },
        "property_type_not_returned": {
            "residential_basis": "property_type_criterion",
            "is_residential": True,
        },
    },
    "charged_or_unknown": {
        "property_type_returned": {
            "residential_basis": "property_type",
            "residential_values": RESIDENTIAL_PROPERTY_TYPES,
            "non_residential_values": DOCUMENTED_NON_RESIDENTIAL_PROPERTY_TYPES,
            "unknown_values": ("Unknown",),
            "outside_criterion_reason": None,
        },
        "property_type_not_returned": {
            "residential_basis": None,
            "is_residential": None,
        },
    },
}
FAILURE_BILLING_EVIDENCE_POLICY = {
    "error_type": "BuyerTransferResponseError",
    "error_base_type": "InvalidResponseError",
    "attribute": "billing_evidence",
    "attribute_type": "BuyerTransferBillingEvidence",
    "built_before_record": (
        "envelope_fields",
        "counts",
        "quantity_free_remaining",
        "total_cost",
    ),
    "carried_by": "every_record_rejection",
    "record_rejection_reasons": RECORD_REJECTION_REASONS,
    "earlier_rejection_type": "InvalidResponseError",
    "message": "reason_code_only",
}
# Provider and caller values that no error text or traceback may carry.
PRIVATE_VALUES = (
    "Synthetic Historical Buyer",
    "P-SYNTHETIC-HISTORY",
    "P-SYNTHETIC-DIFFERENT",
    "1 Synthetic Way",
    "Synthetic City",
    "Synthetic County",
    "SYNTHETIC-PARCEL",
    "49A35",
    "49049",
    "Spaceship",
    "PRIVATE",
)


@pytest.fixture(autouse=True)
def _deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> NoReturn:
        raise AssertionError("synthetic tests must not open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


class DateSubclass(date):
    pass


class StringSubclass(str):
    pass


class IntegerSubclass(int):
    pass


def live_bare_zero_hit_preview() -> dict[str, object]:
    # Exact live 0-hit POST /v1/properties?Purchase=0 body: no metadata at all.
    return {"results": []}


def live_one_hit_radar_id_only_preview() -> dict[str, object]:
    # Live 1-hit Fields=RadarID preview shape with a synthetic RadarID.
    return {
        "results": [{"RadarID": "P-SYNTHETIC-HISTORY"}],
        "totalCost": 0,
        "resultCount": 0,
        "totalResultCount": 1,
    }


def live_withheld_record_preview() -> dict[str, object]:
    # Live 1-hit preview that asked for paid fields: the record is withheld.
    return {
        "results": [],
        "totalCost": 0,
        "resultCount": 0,
        "totalResultCount": 1,
        "quantityFreeRemaining": 9866,
    }


def historical_paid_envelope(total_cost: object = 1) -> dict[str, object]:
    return {
        "results": [
            {
                "RadarID": "P-SYNTHETIC-HISTORY",
                "PType": "Condominium",
                "ZipFive": "00501",
                "FIPS": "49035",
            }
        ],
        "totalCost": total_cost,
        "resultCount": 1,
        "totalResultCount": 1,
    }


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


def historical_property(**changes: object) -> HistoricalBuyerTransferProperty:
    values: dict[str, object] = {
        "returned_fields": BUYER_TRANSFER_PROPERTY_FIELDS,
        "radar_id": "P-SYNTHETIC-HISTORY",
        "property_type": "Single Family",
        "address": "1 Synthetic Way",
        "city": "Synthetic City",
        "state": "Utah",
        "zip_five": "00501",
        "county": "Synthetic County",
        "fips": "49035",
        "apn": "SYNTHETIC-PARCEL",
        "latitude": Decimal("1.1"),
        "longitude": Decimal("2.2"),
    }
    values.update(changes)
    return HistoricalBuyerTransferProperty(**values)  # type: ignore[arg-type]


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


class FailingRecordMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise RuntimeError(f"SYNTHETIC PRIVATE VALUE FOR {key}")

    def __iter__(self) -> Iterator[str]:
        return iter(("RadarID", "FIPS"))

    def __len__(self) -> int:
        return 2


def historical_record(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "RadarID": "P-SYNTHETIC-HISTORY",
        "PType": "Condominium",
        "Address": "1 Synthetic Way",
        "City": "Synthetic City",
        "State": "Utah",
        "ZipFive": "00501",
        "County": "Synthetic County",
        "FIPS": "49035",
        "APN": "SYNTHETIC-PARCEL",
        "Latitude": 1.1,
        "Longitude": 2.2,
    }
    values.update(changes)
    return values


def historical_record_without_property_type() -> dict[str, object]:
    record = historical_record()
    del record["PType"]
    return record


def historical_rejection_envelope(
    record: object, purchase_requested: bool | None
) -> dict[str, object]:
    # One returned record with valid counts, quantity and cost for the mode.
    payload: dict[str, object] = {
        "results": [record],
        "totalCost": "2.50" if purchase_requested is True else "0.50",
        "resultCount": 1,
        "totalResultCount": 1,
    }
    if purchase_requested is not True:
        payload["quantityFreeRemaining"] = 99
    return payload


def historical_rejection_evidence(
    purchase_requested: bool | None,
) -> BuyerTransferBillingEvidence:
    # The billing evidence that historical_rejection_envelope() parses to.
    if purchase_requested is True:
        return BuyerTransferBillingEvidence(
            purchase_requested=True,
            status="charged",
            total_cost=Decimal("2.50"),
            currency=None,
            quantity_free_remaining=None,
            result_count=1,
            total_result_count=1,
        )
    if purchase_requested is False:
        return BuyerTransferBillingEvidence(
            purchase_requested=False,
            status="preview",
            total_cost=Decimal("0.50"),
            currency=None,
            quantity_free_remaining=99,
            result_count=1,
            total_result_count=1,
        )
    return BuyerTransferBillingEvidence(
        purchase_requested=None,
        status="unknown",
        total_cost=Decimal("0.50"),
        currency=None,
        quantity_free_remaining=99,
        result_count=1,
        total_result_count=1,
    )


def live_one_hit_preview_evidence() -> BuyerTransferBillingEvidence:
    return BuyerTransferBillingEvidence(
        purchase_requested=False,
        status="preview",
        total_cost=Decimal("0"),
        currency=None,
        quantity_free_remaining=None,
        result_count=0,
        total_result_count=1,
    )


def assert_record_rejection(
    error: BaseException,
    reason: str,
    billing_evidence: BuyerTransferBillingEvidence,
) -> None:
    message = f"PropertyRadar returned invalid buyer-transfer match ({reason})."
    assert type(error) is BuyerTransferResponseError
    assert isinstance(error, InvalidResponseError)
    assert str(error) == message
    assert error.args == (message,)
    assert error.status_code is None
    assert error.request_id is None
    assert error.retry_after is None
    assert type(error.billing_evidence) is BuyerTransferBillingEvidence
    assert error.billing_evidence == billing_evidence
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    assert error.__context__ is None
    rendered = "\n".join(
        (
            repr(error),
            repr(error.billing_evidence),
            "".join(traceback.format_exception(error)),
        )
    )
    for private_value in PRIVATE_VALUES:
        assert private_value not in rendered


def assert_earlier_rejection(error: BaseException, reason: str) -> None:
    message = f"PropertyRadar returned invalid buyer-transfer match ({reason})."
    assert type(error) is InvalidResponseError
    assert not isinstance(error, BuyerTransferResponseError)
    assert not hasattr(error, "billing_evidence")
    assert str(error) == message
    assert error.args == (message,)
    assert error.__cause__ is None


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

    result = parse_historical_buyer_transfer_match(
        historical_envelope(), criteria=value
    )
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
    # The default (paid) query is the 0.4.1 list: no PropertyType criterion.
    assert build_buyer_transfer_match_criteria(historical_criteria()) == (
        {"name": "State", "value": ["UT"]},
        {"name": "County", "value": [49035]},
        {"name": "Buyer", "value": ["Synthetic Historical Buyer"]},
        {"name": "TransferRecDate", "value": ["from: 1/2/2023 to: 10/31/2023"]},
        {"name": "RadarID", "value": ["P-SYNTHETIC-HISTORY"]},
    )
    assert (
        build_buyer_transfer_match_criteria(historical_criteria(), preview=False)
        == HISTORICAL_PAID_CRITERIA
    )
    # Only the preview adds the residential criterion, just before RadarID.
    assert build_buyer_transfer_match_criteria(historical_criteria(), preview=True) == (
        {"name": "State", "value": ["UT"]},
        {"name": "County", "value": [49035]},
        {"name": "Buyer", "value": ["Synthetic Historical Buyer"]},
        {"name": "TransferRecDate", "value": ["from: 1/2/2023 to: 10/31/2023"]},
        {
            "name": "PropertyType",
            "value": [{"name": "PType", "value": ["SFR", "CND", "MFR", "APT", "RES"]}],
        },
        {"name": "RadarID", "value": ["P-SYNTHETIC-HISTORY"]},
    )
    most_recent_criteria = historical_criteria(
        most_recent_change_of_ownership_only=True
    )
    most_recent = build_buyer_transfer_match_criteria(most_recent_criteria)
    assert most_recent[3] == {
        "name": "TransferRecDate",
        "value": ["from: 1/2/2023 to: 10/31/2023"],
    }
    assert most_recent[-2] == {"name": "isMostRecentMarketTransfer", "value": [1]}
    assert most_recent[-1] == {"name": "RadarID", "value": ["P-SYNTHETIC-HISTORY"]}
    assert [item["name"] for item in most_recent] == list(HISTORICAL_CRITERION_ORDER)
    preview = build_buyer_transfer_match_criteria(most_recent_criteria, preview=True)
    assert preview[3] == most_recent[3]
    assert preview[-3] == {"name": "isMostRecentMarketTransfer", "value": [1]}
    assert preview[-2] == PROPERTY_TYPE_CRITERION
    assert preview[-1] == {"name": "RadarID", "value": ["P-SYNTHETIC-HISTORY"]}
    assert (*preview[:-2], preview[-1]) == most_recent
    assert [item["name"] for item in preview] == list(
        HISTORICAL_PREVIEW_CRITERION_ORDER
    )
    for query in (most_recent, preview):
        assert all(item["name"] != "TransferPublishedDate" for item in query)


@pytest.mark.parametrize("preview", [1, 0, None, "true", 1.0])
def test_historical_builder_preview_flag_must_be_an_exact_boolean(
    preview: object,
) -> None:
    with pytest.raises(TypeError, match=r"^preview must be a boolean$"):
        build_buyer_transfer_match_criteria(
            historical_criteria(),
            preview=preview,  # type: ignore[arg-type]
        )


def test_historical_builder_inserts_a_fresh_property_type_item_per_preview() -> None:
    first = build_buyer_transfer_match_criteria(historical_criteria(), preview=True)
    first_item = first[-2]
    assert first_item["name"] == "PropertyType"
    values = first_item["value"]
    assert isinstance(values, list)
    subcriterion = values[0]
    assert isinstance(subcriterion, dict)
    codes = subcriterion["value"]
    assert isinstance(codes, list)
    codes.clear()
    first_item["name"] = "Changed"

    second = build_buyer_transfer_match_criteria(historical_criteria(), preview=True)
    assert second == HISTORICAL_PREVIEW_CRITERIA
    assert second[-2] is not first_item
    assert build_buyer_transfer_match_criteria(historical_criteria()) == (
        HISTORICAL_PAID_CRITERIA
    )
    assert buyer_transfer_scope_fingerprint(historical_criteria()) == (
        HISTORICAL_SCOPE_FINGERPRINT
    )


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
    for preview in (False, True):
        assert build_buyer_transfer_match_criteria(value, preview=preview)[3] == {
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
    # One scope covers both requests: the paid (0.4.1) criteria list and the
    # PropertyType item that only the preview adds.
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
        "preview_property_type_criterion": PROPERTY_TYPE_CRITERION,
        "fields": BUYER_TRANSFER_PROPERTY_FIELDS,
        "preview_fields": ("RadarID",),
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
    assert buyer_transfer_scope_fingerprint(historical_criteria()) == (
        HISTORICAL_SCOPE_FINGERPRINT
    )
    assert HISTORICAL_SCOPE_FINGERPRINT != (
        HISTORICAL_SCOPE_FINGERPRINT_PAID_PROPERTY_TYPE
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
    # No historical keys: the recent payload is the paid (0.4.1) criteria list
    # plus the PropertyType item that only the preview adds.
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
        "preview_property_type_criterion": PROPERTY_TYPE_CRITERION,
        "fields": BUYER_TRANSFER_PROPERTY_FIELDS,
        "preview_fields": ("RadarID",),
        "limit": 1,
        "start": 0,
    }
    encoded = json.dumps(
        expected_payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    assert (
        buyer_transfer_scope_fingerprint(value) == hashlib.sha256(encoded).hexdigest()
    )
    assert buyer_transfer_scope_fingerprint(value) == (
        RECENT_MOST_RECENT_SCOPE_FINGERPRINT
    )
    assert RECENT_MOST_RECENT_SCOPE_FINGERPRINT != (
        RECENT_MOST_RECENT_SCOPE_FINGERPRINT_PAID_PROPERTY_TYPE
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
    assert contract["api_version"] == "5.3.1.0"
    assert contract["mode"] == "historical_recording_range"
    assert contract["publication_window_values"] == ()
    assert contract["recording_window_values"] == ()
    assert contract["ordered_fields"] == BUYER_TRANSFER_PROPERTY_FIELDS
    criterion_order = contract["criterion_order"]
    assert isinstance(criterion_order, tuple)
    assert "TransferPublishedDate" not in criterion_order
    # Paid requests keep the 0.4.1 order; only previews add PropertyType.
    assert criterion_order == (
        "State",
        "County",
        "Buyer",
        "TransferRecDate",
        "isMostRecentMarketTransfer",
        "RadarID",
    )
    assert criterion_order == HISTORICAL_CRITERION_ORDER
    preview_criterion_order = contract["preview_criterion_order"]
    assert isinstance(preview_criterion_order, tuple)
    assert preview_criterion_order == (
        "State",
        "County",
        "Buyer",
        "TransferRecDate",
        "isMostRecentMarketTransfer",
        "PropertyType",
        "RadarID",
    )
    assert preview_criterion_order == HISTORICAL_PREVIEW_CRITERION_ORDER
    assert contract["preview_fields"] == ("RadarID",)
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
    assert fingerprint == HISTORICAL_CONTRACT_FINGERPRINT
    assert fingerprint != HISTORICAL_CONTRACT_FINGERPRINT_PAID_PROPERTY_TYPE
    assert fingerprint != HISTORICAL_CONTRACT_FINGERPRINT_0_4_1


def test_historical_contract_keeps_every_value_the_theperrygroup_adapter_checks() -> (
    None
):
    contract = BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT
    assert type(contract) is MappingProxyType
    assert contract["operation"] == "properties.search"
    assert contract["method"] == "POST"
    assert contract["path"] == "/v1/properties"
    assert contract["relationship"] == "provider_buyer_criterion_property_match"
    assert contract["contract_version"] == 1
    assert contract["mode"] == "historical_recording_range"
    assert contract["publication_window_values"] == ()
    assert contract["recording_window_values"] == ()
    assert contract["scope_fingerprint_policy"] == (
        "bind_mode_contract_and_recording_boundaries"
    )
    limitations = contract["provider_limitations"]
    assert type(limitations) is MappingProxyType
    assert limitations["matched_transaction_identifier"] is None
    assert limitations["matched_structured_grantees"] is None
    assert limitations["transaction_party_boundaries"] is None
    assert limitations["scalar_grantor_grantee_parsing"] is False
    date_contract = contract["recording_date_range"]
    assert type(date_contract) is MappingProxyType
    assert date_contract["criterion"] == "TransferRecDate"
    assert date_contract["boundary_type"] == "date"
    assert date_contract["inclusive"] is True
    assert date_contract["minimum_date"] == date.min.isoformat()
    assert date_contract["maximum_date"] == date.max.isoformat()
    assert date_contract["span_limit"] == "caller_authorization_policy"
    assert date_contract["open_ended"] is False
    criterion = contract["property_type_criterion"]
    assert type(criterion) is MappingProxyType
    assert criterion["purchase_0_live_probed"] is False
    assert criterion["requests"] == ("preview",)
    assert criterion["position"] == "immediately_before_radar_id"
    assert json.loads(json.dumps(thaw(criterion["shape"]))) == PROPERTY_TYPE_CRITERION
    assert criterion["codes"] == BUYER_TRANSFER_RESIDENTIAL_PTYPE_CODES
    assert tuple(criterion["code_property_types"].values()) == (
        RESIDENTIAL_PROPERTY_TYPES
    )
    recent = BUYER_TRANSFER_MATCH_CONTRACT["property_type_criterion"]
    assert type(recent) is MappingProxyType
    assert criterion["codes"] == recent["codes"]
    assert thaw(criterion["code_property_types"]) == thaw(recent["code_property_types"])
    billing = contract["billing"]
    assert type(billing) is MappingProxyType
    assert billing["total_cost"]["accepted_json_types"] == (
        "string",
        "integer",
        "number",
    )
    policy = contract["parser_policy"]
    assert type(policy) is MappingProxyType
    assert policy["bare_preview_envelope"]["provider_metadata_omitted"] is True
    assert policy["count_rules"]["preview"]["withheld_record_reason"] == (
        "preview_record_withheld"
    )
    # Only a preview sends the criterion, so only a preview enforces it.
    within_criterion = policy["returned_property_type_must_be_within_criterion"]
    assert type(within_criterion) is MappingProxyType
    assert thaw(within_criterion) == {"preview": True, "charged_or_unknown": False}
    classification = policy["residential_classification"]
    assert type(classification) is MappingProxyType
    assert thaw(classification) == RESIDENTIAL_CLASSIFICATION_POLICY
    failure_evidence = policy["failure_billing_evidence"]
    assert type(failure_evidence) is MappingProxyType
    assert thaw(failure_evidence) == FAILURE_BILLING_EVIDENCE_POLICY
    assert failure_evidence["error_type"] == BuyerTransferResponseError.__name__
    assert failure_evidence["error_base_type"] == InvalidResponseError.__name__
    assert failure_evidence["attribute_type"] == BuyerTransferBillingEvidence.__name__
    recent_policy = BUYER_TRANSFER_MATCH_CONTRACT["parser_policy"]
    assert type(recent_policy) is MappingProxyType
    for name in (
        "returned_property_type_must_be_within_criterion",
        "residential_classification",
        "failure_billing_evidence",
    ):
        assert thaw(policy[name]) == thaw(recent_policy[name])
    assert thaw(criterion) == thaw(recent)


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
    # The positional default is the paid (0.4.1) list; a preview adds the
    # PropertyType item just before RadarID.
    assert build_buyer_transfer_match_criteria(value)[6:] == (
        {"name": "RadarID", "value": ["P-SYNTHETIC-HISTORY"]},
    )
    preview_query = build_buyer_transfer_match_criteria(value, preview=True)
    assert preview_query[3:6] == build_buyer_transfer_match_criteria(value)[3:6]
    assert preview_query[6:] == (
        PROPERTY_TYPE_CRITERION,
        {"name": "RadarID", "value": ["P-SYNTHETIC-HISTORY"]},
    )
    assert BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"] == (
        RECENT_CONTRACT_FINGERPRINT
    )
    assert (
        BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"]
        != RECENT_CONTRACT_FINGERPRINT_PAID_PROPERTY_TYPE
    )
    assert (
        BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"]
        != RECENT_CONTRACT_FINGERPRINT_0_4_1
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
    result = parse_historical_buyer_transfer_match(
        payload, criteria=value, purchase_requested=False
    )
    assert type(result) is HistoricalBuyerTransferMatchResult
    assert result.matched is matched
    assert (
        result.contract_fingerprint
        == (BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT["contract_fingerprint"])
    )
    assert result.scope_fingerprint == buyer_transfer_scope_fingerprint(value)
    assert result.billing.status == "preview"
    if matched:
        assert result.linkage is not None
        assert type(result.linkage) is HistoricalBuyerTransferLinkage
        assert type(result.linkage.property) is HistoricalBuyerTransferProperty
        assert result.linkage.scope_fingerprint == result.scope_fingerprint
        assert result.linkage.matched_transaction_identifier is None
        assert result.linkage.matched_grantees is None


def test_historical_parser_retains_exact_target_and_private_error_contract() -> None:
    payload = historical_envelope()
    payload["results"] = [{"RadarID": "P-SYNTHETIC-UNEXPECTED"}]
    with pytest.raises(InvalidResponseError) as caught:
        parse_historical_buyer_transfer_match(payload, criteria=historical_criteria())

    formatted = "".join(traceback.format_exception(caught.value))
    assert "P-SYNTHETIC-UNEXPECTED" not in formatted
    assert "Synthetic Historical Buyer" not in formatted
    assert caught.value.__cause__ is None
    assert_record_rejection(
        caught.value, "radar_id_mismatch", historical_rejection_evidence(None)
    )


@pytest.mark.parametrize(
    ("purchase_requested", "status"), [(True, "charged"), (None, "unknown")]
)
def test_historical_billing_does_not_guess_purchase_state(
    purchase_requested: bool | None, status: str
) -> None:
    result = parse_historical_buyer_transfer_match(
        historical_envelope(purchase=True),
        criteria=historical_criteria(),
        purchase_requested=purchase_requested,
    )
    assert result.billing.purchase_requested is purchase_requested
    assert result.billing.status == status
    assert result.billing.quantity_free_remaining is None


def test_historical_charged_response_rejects_preview_only_metadata() -> None:
    with pytest.raises(InvalidResponseError):
        parse_historical_buyer_transfer_match(
            historical_envelope(),
            criteria=historical_criteria(),
            purchase_requested=True,
        )


@pytest.mark.parametrize(
    ("changes", "field_name"),
    [
        ({"returned_fields": list(BUYER_TRANSFER_PROPERTY_FIELDS)}, "returned_fields"),
        ({"returned_fields": ("Address", "RadarID")}, "returned_fields"),
        ({"returned_fields": ("RadarID", "RadarID")}, "returned_fields"),
        ({"returned_fields": ("RadarID", "SyntheticUnknown")}, "returned_fields"),
        ({"returned_fields": BUYER_TRANSFER_PROPERTY_FIELDS[1:]}, "RadarID"),
        ({"returned_fields": ("RadarID",)}, "returned_fields"),
        ({"radar_id": ""}, "radar_id"),
        ({"radar_id": 42}, "radar_id"),
        ({"property_type": "Synthetic Undocumented Type"}, "property_type"),
        ({"address": 1}, "address"),
        ({"zip_five": 501}, "zip_five"),
        ({"zip_five": "0501"}, "zip_five"),
        ({"fips": "SYNTHETIC-PRIVATE-FIPS"}, "fips"),
        ({"latitude": Decimal("91")}, "latitude"),
        ({"longitude": Decimal("NaN")}, "longitude"),
    ],
)
def test_historical_property_constructor_enforces_shape_without_value_leaks(
    changes: dict[str, object], field_name: str
) -> None:
    with pytest.raises(ValueError, match=field_name) as caught:
        historical_property(**changes)
    assert "SYNTHETIC-PRIVATE-FIPS" not in str(caught.value)
    assert "Synthetic Undocumented Type" not in str(caught.value)


@pytest.mark.parametrize(
    ("property_type", "residential"),
    [("Single Family", True), ("Commercial", False), ("Unknown", None)],
)
def test_historical_property_reports_only_documented_residential_classification(
    property_type: str, residential: bool | None
) -> None:
    value = historical_property(property_type=property_type)
    assert value.residential_basis is None
    assert value.is_residential is residential
    assert "SYNTHETIC-PARCEL" not in repr(value)
    assert "1 Synthetic Way" not in repr(value)


@pytest.mark.parametrize(
    ("changes", "field_name"),
    [
        ({"scope_fingerprint": "synthetic-invalid-hash"}, "scope_fingerprint"),
        ({"scope_fingerprint": 42}, "scope_fingerprint"),
        ({"property": object()}, "property"),
        ({"relationship": "synthetic-document-grantee-match"}, "relationship"),
        ({"matched_transaction_identifier": "synthetic-record"}, "unavailable"),
        ({"matched_grantees": ("Synthetic Person",)}, "unavailable"),
    ],
)
def test_historical_linkage_constructor_rejects_unproved_or_malformed_evidence(
    changes: dict[str, object], field_name: str
) -> None:
    linkage = HistoricalBuyerTransferLinkage(
        scope_fingerprint=buyer_transfer_scope_fingerprint(historical_criteria()),
        property=historical_property(),
    )
    with pytest.raises(ValueError, match=field_name) as caught:
        replace(linkage, **changes)  # type: ignore[arg-type]
    assert "synthetic-record" not in str(caught.value)
    assert "Synthetic Person" not in str(caught.value)


def test_historical_result_requires_matching_scope_billing_and_linkage_presence() -> (
    None
):
    result = parse_historical_buyer_transfer_match(
        historical_envelope(), criteria=historical_criteria()
    )
    assert result.linkage is not None
    with pytest.raises(ValueError, match="scope_fingerprint"):
        replace(result, scope_fingerprint="synthetic-invalid-hash")
    with pytest.raises(ValueError, match="exact scope"):
        replace(result, linkage=replace(result.linkage, scope_fingerprint="0" * 64))
    with pytest.raises(ValueError, match="billing"):
        replace(result, billing=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="presence"):
        replace(result, linkage=None)
    with pytest.raises(ValueError, match="presence"):
        replace(
            result,
            billing=replace(result.billing, result_count=0, total_result_count=0),
        )


def test_historical_models_reject_recent_property_and_linkage_types() -> None:
    criteria = historical_criteria()
    current = parse_historical_buyer_transfer_match(
        historical_envelope(), criteria=criteria
    )
    recent = parse_buyer_transfer_match(
        historical_envelope(),
        criteria=replace(
            criteria, publication_window="Last 7 Days", recording_date_range=None
        ),
    )
    assert current.linkage is not None
    assert recent.linkage is not None
    with pytest.raises(ValueError, match="property"):
        replace(current.linkage, property=recent.linkage.property)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="linkage"):
        replace(current, linkage=recent.linkage)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("record", "reason"),
    [
        ({}, "missing_radar_id"),
        ({"RadarID": "P-SYNTHETIC-HISTORY", "FIPS": "49049"}, "fips_mismatch"),
        (
            {"RadarID": "P-SYNTHETIC-HISTORY", "FIPS": "synthetic-private-fips"},
            "fips",
        ),
        ({"RadarID": "P-SYNTHETIC-HISTORY", "PType": "Undocumented"}, "property_type"),
        (
            {"RadarID": "P-SYNTHETIC-HISTORY", "Unknown": "synthetic-private-value"},
            "undocumented_property_fields",
        ),
    ],
)
def test_historical_parser_rejects_missing_or_inconsistent_property_identity(
    record: dict[str, object], reason: str
) -> None:
    payload = {**historical_envelope(), "results": [record]}
    with pytest.raises(InvalidResponseError) as caught:
        parse_historical_buyer_transfer_match(payload, criteria=historical_criteria())
    assert "synthetic-private" not in str(caught.value)
    assert "synthetic-private" not in "".join(traceback.format_exception(caught.value))
    # A detached (unknown) parse still carries the evidence it parsed.
    assert_record_rejection(caught.value, reason, historical_rejection_evidence(None))


@pytest.mark.parametrize(
    "changes",
    [
        {"results": [{"RadarID": "P-SYNTHETIC-HISTORY"}] * 2},
        {"results": {}},
        {"results": [None]},
        {"resultCount": 0},
        {"totalResultCount": 0},
        {"resultCount": 2, "totalResultCount": 2},
    ],
)
def test_historical_parser_rejects_ambiguous_or_inconsistent_result_envelopes(
    changes: dict[str, object],
) -> None:
    with pytest.raises(InvalidResponseError):
        parse_historical_buyer_transfer_match(
            {**historical_envelope(), **changes}, criteria=historical_criteria()
        )


def test_historical_entrypoints_reject_invalid_types_before_transport() -> None:
    with pytest.raises(InvalidResponseError, match="criteria_type"):
        parse_historical_buyer_transfer_match(
            historical_envelope(),
            criteria=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(InvalidResponseError, match="purchase_requested"):
        parse_historical_buyer_transfer_match(
            historical_envelope(),
            criteria=historical_criteria(),
            purchase_requested=1,  # type: ignore[arg-type]
        )
    with pytest.raises(InvalidResponseError, match="required_envelope_fields"):
        parse_historical_buyer_transfer_match({}, criteria=historical_criteria())

    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=historical_envelope())

    client, http_client = make_client(handler)
    try:
        with pytest.raises(TypeError, match="criteria"):
            client.properties.historical_buyer_transfer_match(
                criteria=object()  # type: ignore[arg-type]
            )
        with pytest.raises(TypeError, match="criteria"):
            client.properties.buyer_transfer_match(
                criteria=object()  # type: ignore[arg-type]
            )
    finally:
        http_client.close()
    assert calls == 0


def test_historical_zip_preserves_five_ascii_digits_and_leading_zero() -> None:
    payload = historical_envelope()
    payload["results"] = [
        {"RadarID": "P-SYNTHETIC-HISTORY", "FIPS": "49035", "ZipFive": "00501"}
    ]
    result = parse_historical_buyer_transfer_match(
        payload, criteria=historical_criteria()
    )

    assert result.linkage is not None
    property_value = result.linkage.property
    assert property_value.zip_five == "00501"
    assert type(property_value.zip_five) is str
    assert "ZipFive" in property_value.returned_fields
    assert "00501" not in repr(property_value)
    with pytest.raises(FrozenInstanceError):
        property_value.zip_five = "12345"  # type: ignore[misc]

    absent = parse_historical_buyer_transfer_match(
        historical_envelope(), criteria=historical_criteria()
    )
    assert absent.linkage is not None
    assert absent.linkage.property.zip_five is None


@pytest.mark.parametrize(
    "zip_five",
    [
        501,
        12345,
        None,
        True,
        "",
        "0501",
        "000501",
        "00501 ",
        " 00501",
        "00-01",
        "\uff11\uff12\uff13\uff14\uff15",
        "١٢٣٤٥",
        StringSubclass("00501"),
    ],
)
def test_historical_zip_rejects_integers_and_nonexact_string_shapes(
    zip_five: object,
) -> None:
    payload = historical_envelope()
    payload["results"] = [{"RadarID": "P-SYNTHETIC-HISTORY", "ZipFive": zip_five}]
    with pytest.raises(InvalidResponseError):
        parse_historical_buyer_transfer_match(payload, criteria=historical_criteria())


@pytest.mark.parametrize(
    "metadata",
    [
        {"facets": {}},
        {"nextPageToken": ""},
        {"maxDistanceMiles": 0},
        {"maxDistanceMiles": 1},
        {"maxDistanceMiles": 250},
        {"facets": {}, "nextPageToken": "", "maxDistanceMiles": 250},
    ],
)
@pytest.mark.parametrize("matched", [False, True])
def test_historical_parser_validates_and_discards_empty_metadata(
    metadata: dict[str, object], matched: bool
) -> None:
    payload = historical_envelope()
    if not matched:
        payload.update(results=[], resultCount=0, totalResultCount=0)
    expected = parse_historical_buyer_transfer_match(
        payload, criteria=historical_criteria()
    )
    result = parse_historical_buyer_transfer_match(
        {**payload, **metadata}, criteria=historical_criteria()
    )
    assert result == expected
    for field_name in ("facets", "nextPageToken", "maxDistanceMiles"):
        assert not hasattr(result, field_name)


@pytest.mark.parametrize(
    "metadata",
    [
        {"facets": [{}]},
        {"facets": [{"name": "State", "value": "UT"}]},
        {"facets": {"State": {"UT": 1}}},
        {"facets": []},
        {"facets": ()},
        {"facets": ""},
        {"facets": None},
        {"facets": False},
        {"nextPageToken": "synthetic-next-page"},
        {"nextPageToken": " "},
        {"nextPageToken": None},
        {"nextPageToken": 0},
        {"nextPageToken": False},
        {"nextPageToken": []},
        {"nextPageToken": StringSubclass("")},
        {"maxDistanceMiles": -1},
        {"maxDistanceMiles": 251},
        {"maxDistanceMiles": 0.0},
        {"maxDistanceMiles": 250.0},
        {"maxDistanceMiles": True},
        {"maxDistanceMiles": False},
        {"maxDistanceMiles": None},
        {"maxDistanceMiles": "0"},
        {"maxDistanceMiles": IntegerSubclass(0)},
        {"unknownMetadata": "synthetic-value"},
    ],
)
def test_historical_parser_rejects_nonempty_or_malformed_metadata(
    metadata: dict[str, object],
) -> None:
    with pytest.raises(InvalidResponseError):
        parse_historical_buyer_transfer_match(
            {**historical_envelope(), **metadata}, criteria=historical_criteria()
        )


@pytest.mark.parametrize(
    "metadata", [{"facets": {}}, {"nextPageToken": ""}, {"maxDistanceMiles": 0}]
)
def test_recent_parser_still_rejects_historical_response_metadata(
    metadata: dict[str, object],
) -> None:
    recent = replace(
        historical_criteria(),
        publication_window="Last 7 Days",
        recording_date_range=None,
    )
    with pytest.raises(InvalidResponseError):
        parse_buyer_transfer_match(
            {**historical_envelope(), **metadata}, criteria=recent
        )


def test_recent_parser_keeps_integer_zip_and_rejects_string_zip() -> None:
    recent = replace(
        historical_criteria(),
        publication_window="Last 7 Days",
        recording_date_range=None,
    )
    payload = historical_envelope()
    payload["results"] = [{"RadarID": "P-SYNTHETIC-HISTORY", "ZipFive": 501}]
    result = parse_buyer_transfer_match(payload, criteria=recent)
    assert type(result) is BuyerTransferMatchResult
    assert result.linkage is not None
    assert result.linkage.property.zip_five == 501
    assert type(result.linkage.property.zip_five) is int

    payload["results"] = [{"RadarID": "P-SYNTHETIC-HISTORY", "ZipFive": "00501"}]
    with pytest.raises(InvalidResponseError):
        parse_buyer_transfer_match(payload, criteria=recent)


def test_versioned_parsers_reject_the_other_criteria_mode() -> None:
    historical = historical_criteria()
    recent = replace(
        historical, publication_window="Last 7 Days", recording_date_range=None
    )
    with pytest.raises(InvalidResponseError):
        parse_buyer_transfer_match(historical_envelope(), criteria=historical)
    with pytest.raises(InvalidResponseError):
        parse_historical_buyer_transfer_match(historical_envelope(), criteria=recent)


def test_versioned_results_reject_the_other_contract_fingerprint() -> None:
    historical = historical_criteria()
    recent = replace(
        historical, publication_window="Last 7 Days", recording_date_range=None
    )
    historical_result = parse_historical_buyer_transfer_match(
        historical_envelope(), criteria=historical
    )
    recent_result = parse_buyer_transfer_match(historical_envelope(), criteria=recent)
    with pytest.raises(ValueError, match="contract_fingerprint"):
        replace(
            historical_result,
            contract_fingerprint=str(
                BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"]
            ),
        )
    with pytest.raises(ValueError, match="contract_fingerprint"):
        replace(
            recent_result,
            contract_fingerprint=str(
                BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT["contract_fingerprint"]
            ),
        )


def test_versioned_resources_reject_other_mode_before_transport() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=historical_envelope())

    historical = historical_criteria()
    recent = replace(
        historical, publication_window="Last 7 Days", recording_date_range=None
    )
    client, http_client = make_client(handler)
    try:
        with pytest.raises((ValueError, InvalidResponseError)):
            client.properties.buyer_transfer_match(criteria=historical)
        with pytest.raises((ValueError, InvalidResponseError)):
            client.properties.historical_buyer_transfer_match(criteria=recent)
    finally:
        http_client.close()
    assert calls == 0


def test_historical_preview_makes_one_bounded_mock_request() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=live_one_hit_radar_id_only_preview())

    client, http_client = make_client(handler)
    try:
        result = client.properties.historical_buyer_transfer_match(
            criteria=historical_criteria()
        )
    finally:
        http_client.close()

    assert (
        result.contract_fingerprint
        == (BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT["contract_fingerprint"])
    )
    assert result.billing.status == "preview"
    assert result.matched is True
    assert result.linkage is not None
    assert result.linkage.property.residential_basis == "property_type_criterion"
    assert result.linkage.property.is_residential is True
    assert result.scope_fingerprint == HISTORICAL_SCOPE_FINGERPRINT
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/v1/properties"
    assert request.url.params.multi_items() == [
        ("Fields", "RadarID"),
        ("Limit", "1"),
        ("Start", "0"),
        ("Purchase", "0"),
    ]
    assert request.url.params["Fields"] == ",".join(BUYER_TRANSFER_PREVIEW_FIELDS)
    body = json.loads(request.content)
    # The preview sends the residential PropertyType criterion before RadarID.
    assert body == {"Criteria": list(HISTORICAL_PREVIEW_CRITERIA)}
    assert body == {
        "Criteria": list(
            build_buyer_transfer_match_criteria(historical_criteria(), preview=True)
        )
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
            client.properties.historical_buyer_transfer_match(
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
            client.properties.historical_buyer_transfer_match(
                criteria=historical_criteria(), purchase=True
            )
    finally:
        http_client.close()
    assert calls == 1


def test_historical_paid_request_sends_every_field_and_the_0_4_1_criteria() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=historical_paid_envelope())

    client, http_client = make_client(handler, allow_charges=True)
    try:
        result = client.properties.historical_buyer_transfer_match(
            criteria=historical_criteria(), purchase=True
        )
    finally:
        http_client.close()

    assert type(result) is HistoricalBuyerTransferMatchResult
    assert result.billing.status == "charged"
    assert result.billing.total_cost == Decimal("1")
    assert result.linkage is not None
    assert result.linkage.property.residential_basis == "property_type"
    assert result.linkage.property.is_residential is True
    assert result.scope_fingerprint == HISTORICAL_SCOPE_FINGERPRINT
    assert len(captured) == 1
    assert captured[0].url.params.multi_items() == [
        ("Fields", ",".join(BUYER_TRANSFER_PROPERTY_FIELDS)),
        ("Limit", "1"),
        ("Start", "0"),
        ("Purchase", "1"),
    ]
    body = json.loads(captured[0].content)
    # The paid request keeps the 0.4.1 criteria: no PropertyType criterion.
    assert body == {"Criteria": list(HISTORICAL_PAID_CRITERIA)}
    assert body == {
        "Criteria": list(build_buyer_transfer_match_criteria(historical_criteria()))
    }
    assert b"PropertyType" not in captured[0].content


def test_historical_paid_record_rejection_propagates_with_evidence_once() -> None:
    calls = 0
    payload = historical_rejection_envelope(
        historical_record(RadarID="P-SYNTHETIC-DIFFERENT"), True
    )

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=payload)

    client, http_client = make_client(handler, allow_charges=True, max_retries=3)
    try:
        with pytest.raises(BuyerTransferResponseError) as caught:
            client.properties.historical_buyer_transfer_match(
                criteria=historical_criteria(), purchase=True
            )
    finally:
        http_client.close()

    assert calls == 1
    assert_record_rejection(
        caught.value, "radar_id_mismatch", historical_rejection_evidence(True)
    )


def test_historical_preview_outside_the_criterion_propagates_its_evidence() -> None:
    payload = {
        **live_one_hit_radar_id_only_preview(),
        "results": [{"RadarID": "P-SYNTHETIC-HISTORY", "PType": "Commercial"}],
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client, http_client = make_client(handler)
    try:
        with pytest.raises(BuyerTransferResponseError) as caught:
            client.properties.historical_buyer_transfer_match(
                criteria=historical_criteria()
            )
    finally:
        http_client.close()

    assert_record_rejection(
        caught.value,
        "property_type_outside_criterion",
        live_one_hit_preview_evidence(),
    )


def test_historical_paid_resource_classifies_a_commercial_record() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=historical_rejection_envelope(
                historical_record(PType="Commercial"), True
            ),
        )

    client, http_client = make_client(handler, allow_charges=True)
    try:
        result = client.properties.historical_buyer_transfer_match(
            criteria=historical_criteria(), purchase=True
        )
    finally:
        http_client.close()

    assert result.matched is True
    assert result.linkage is not None
    assert result.linkage.property.property_type == "Commercial"
    assert result.linkage.property.residential_basis == "property_type"
    assert result.linkage.property.is_residential is False
    assert result.billing == historical_rejection_evidence(True)


def test_historical_live_bare_zero_hit_preview_is_a_no_match() -> None:
    value = historical_criteria()
    result = parse_historical_buyer_transfer_match(
        live_bare_zero_hit_preview(), criteria=value, purchase_requested=False
    )

    assert type(result) is HistoricalBuyerTransferMatchResult
    assert result.matched is False
    assert result.linkage is None
    assert (
        result.contract_fingerprint
        == (BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT["contract_fingerprint"])
    )
    assert result.scope_fingerprint == buyer_transfer_scope_fingerprint(value)
    billing = result.billing
    assert type(billing) is BuyerTransferBillingEvidence
    assert billing.purchase_requested is False
    assert billing.status == "preview"
    assert type(billing.total_cost) is Decimal
    assert billing.total_cost == Decimal("0")
    assert billing.currency is None
    assert billing.quantity_free_remaining is None
    assert billing.result_count == 0
    assert billing.total_result_count == 0
    assert billing.provider_metadata_omitted is True


@pytest.mark.parametrize("purchase_requested", [True, None])
def test_historical_live_bare_zero_hit_envelope_needs_metadata_unless_preview(
    purchase_requested: bool | None,
) -> None:
    with pytest.raises(InvalidResponseError, match=r"\(required_envelope_fields\)"):
        parse_historical_buyer_transfer_match(
            live_bare_zero_hit_preview(),
            criteria=historical_criteria(),
            purchase_requested=purchase_requested,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"results": [], "facets": {}},
        {"results": [], "nextPageToken": ""},
        {"results": [], "maxDistanceMiles": 0},
        {"results": [], "totalCost": 0},
        {"results": [{"RadarID": "P-SYNTHETIC-HISTORY"}]},
        {"results": None},
    ],
)
def test_historical_other_partial_preview_envelopes_still_fail_closed(
    payload: dict[str, object],
) -> None:
    with pytest.raises(InvalidResponseError, match=r"\(required_envelope_fields\)"):
        parse_historical_buyer_transfer_match(
            payload, criteria=historical_criteria(), purchase_requested=False
        )


def test_historical_live_one_hit_radar_id_only_preview_is_matched() -> None:
    value = historical_criteria()
    result = parse_historical_buyer_transfer_match(
        live_one_hit_radar_id_only_preview(),
        criteria=value,
        purchase_requested=False,
    )

    assert type(result) is HistoricalBuyerTransferMatchResult
    assert result.matched is True
    assert result.linkage is not None
    assert type(result.linkage) is HistoricalBuyerTransferLinkage
    property_value = result.linkage.property
    assert type(property_value) is HistoricalBuyerTransferProperty
    assert property_value.radar_id == "P-SYNTHETIC-HISTORY"
    assert property_value.returned_fields == ("RadarID",)
    assert property_value.fips is None
    assert property_value.zip_five is None
    assert property_value.property_type is None
    assert property_value.is_residential is True
    assert property_value.residential_basis == "property_type_criterion"
    assert result.scope_fingerprint == buyer_transfer_scope_fingerprint(value)
    assert result.linkage.scope_fingerprint == result.scope_fingerprint
    billing = result.billing
    assert billing.purchase_requested is False
    assert billing.status == "preview"
    assert billing.total_cost == Decimal("0")
    assert billing.currency is None
    assert billing.quantity_free_remaining is None
    assert billing.result_count == 0
    assert billing.total_result_count == 1
    assert billing.provider_metadata_omitted is False
    rendered = repr(result)
    assert "P-SYNTHETIC-HISTORY" not in rendered
    assert "Synthetic Historical Buyer" not in rendered


def test_historical_ci_smoke_shapes_keep_their_results() -> None:
    # The CI and release smoke tests read item [3] of the historical query
    # and parse these preview shapes.
    value = historical_criteria()
    transfer_recording_date = {
        "name": "TransferRecDate",
        "value": ["from: 1/2/2023 to: 10/31/2023"],
    }
    one_hit = parse_historical_buyer_transfer_match(
        {
            "results": [{"RadarID": "P-SYNTHETIC-HISTORY"}],
            "totalCost": 0,
            "quantityFreeRemaining": 100,
            "resultCount": 0,
            "totalResultCount": 1,
        },
        criteria=value,
        purchase_requested=False,
    )
    bare = parse_historical_buyer_transfer_match(
        {"results": []}, criteria=value, purchase_requested=False
    )

    assert build_buyer_transfer_match_criteria(value)[3] == transfer_recording_date
    assert (
        build_buyer_transfer_match_criteria(value, preview=True)[3]
        == transfer_recording_date
    )
    assert one_hit.matched is True
    assert one_hit.linkage is not None
    assert one_hit.linkage.property.is_residential is True
    assert one_hit.linkage.property.residential_basis == "property_type_criterion"
    assert one_hit.billing.status == "preview"
    assert one_hit.billing.total_cost == Decimal("0")
    assert one_hit.billing.quantity_free_remaining == 100
    assert one_hit.billing.result_count == 0
    assert one_hit.billing.total_result_count == 1
    assert bare.matched is False
    assert bare.linkage is None
    assert bare.billing.provider_metadata_omitted is True


@pytest.mark.parametrize("purchase_requested", [True, None])
def test_historical_live_one_hit_preview_counts_fail_paid_and_unknown_parses(
    purchase_requested: bool | None,
) -> None:
    with pytest.raises(InvalidResponseError, match=r"\(result_count_mismatch\)"):
        parse_historical_buyer_transfer_match(
            live_one_hit_radar_id_only_preview(),
            criteria=historical_criteria(),
            purchase_requested=purchase_requested,
        )


def test_historical_live_withheld_record_preview_fails_closed() -> None:
    with pytest.raises(
        InvalidResponseError, match=r"\(preview_record_withheld\)"
    ) as caught:
        parse_historical_buyer_transfer_match(
            live_withheld_record_preview(),
            criteria=historical_criteria(),
            purchase_requested=False,
        )
    assert "9866" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("purchase_requested", [True, None])
def test_historical_live_withheld_record_shape_fails_paid_and_unknown_parses(
    purchase_requested: bool | None,
) -> None:
    payload = live_withheld_record_preview()
    if purchase_requested is True:
        del payload["quantityFreeRemaining"]
    with pytest.raises(InvalidResponseError, match=r"\(ambiguous_total_result_count\)"):
        parse_historical_buyer_transfer_match(
            payload,
            criteria=historical_criteria(),
            purchase_requested=purchase_requested,
        )


@pytest.mark.parametrize("with_record", [True, False])
@pytest.mark.parametrize("purchase_requested", [False, True, None])
def test_historical_live_total_result_count_two_preview_fails_closed(
    with_record: bool, purchase_requested: bool | None
) -> None:
    payload: dict[str, object] = {
        "results": [{"RadarID": "P-SYNTHETIC-HISTORY"}] if with_record else [],
        "totalCost": 0,
        "resultCount": 0,
        "totalResultCount": 2,
    }
    with pytest.raises(InvalidResponseError, match=r"\(total_result_count\)"):
        parse_historical_buyer_transfer_match(
            payload,
            criteria=historical_criteria(),
            purchase_requested=purchase_requested,
        )


@pytest.mark.parametrize(
    ("total_cost", "expected"),
    [
        (0, Decimal("0")),
        (3, Decimal("3")),
        (10**64 - 1, Decimal(10**64 - 1)),
        (0.0, Decimal("0.0")),
        (0.1, Decimal("0.1")),
        (1.5, Decimal("1.5")),
        (2.5, Decimal("2.5")),
        (0.30000000000000004, Decimal("0.30000000000000004")),
        (1e16, Decimal("1E+16")),
        ("0", Decimal("0")),
        ("0.50", Decimal("0.50")),
        ("1" * 64, Decimal("1" * 64)),
    ],
)
@pytest.mark.parametrize("purchase_requested", [False, True, None])
def test_historical_live_total_cost_json_int_float_and_decimal_string_are_accepted(
    total_cost: object, expected: Decimal, purchase_requested: bool | None
) -> None:
    payload = {
        **historical_envelope(purchase=purchase_requested is True),
        "totalCost": total_cost,
    }
    result = parse_historical_buyer_transfer_match(
        payload, criteria=historical_criteria(), purchase_requested=purchase_requested
    )

    assert type(result.billing.total_cost) is Decimal
    assert result.billing.total_cost == expected


# D9 adds no totalCost rejection. The parser sees the JSON number as decoded:
# an integer is always exact, and a number with at most 15 significant digits
# keeps its written value. A longer number with a fraction or an exponent is
# already a rounded float, so its Decimal follows that float.
@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("0.1", Decimal("0.1")),
        ("1.5", Decimal("1.5")),
        ("0.30000000000000004", Decimal("0.30000000000000004")),
        ("123456789012.345", Decimal("123456789012.345")),
        ("12345678901234567890", Decimal("12345678901234567890")),
        ("1.23456789012345678", Decimal("1.2345678901234567")),
        ("1.0000000000000000001", Decimal("1.0")),
        ("2.5e3", Decimal("2500.0")),
    ],
)
@pytest.mark.parametrize("purchase_requested", [False, True, None])
def test_historical_total_cost_follows_the_json_number_as_decoded(
    number: str, expected: Decimal, purchase_requested: bool | None
) -> None:
    payload = {
        **historical_envelope(purchase=purchase_requested is True),
        "totalCost": json.loads(number),
    }
    result = parse_historical_buyer_transfer_match(
        payload, criteria=historical_criteria(), purchase_requested=purchase_requested
    )

    assert type(result.billing.total_cost) is Decimal
    assert result.billing.total_cost.as_tuple() == expected.as_tuple()


@pytest.mark.parametrize(
    "total_cost",
    [
        True,
        False,
        None,
        float("nan"),
        float("inf"),
        -1,
        -0.0,
        -2.5,
        10**64,
        1e64,
        1e-63,
        "-1.00",
        "1" * 65,
        "1e3",
        Decimal("0"),
        IntegerSubclass(1),
        StringSubclass("0"),
        [0],
    ],
)
@pytest.mark.parametrize("purchase_requested", [False, True, None])
def test_historical_live_total_cost_rejects_bool_non_finite_negative_and_overlong(
    total_cost: object, purchase_requested: bool | None
) -> None:
    payload = {
        **historical_envelope(purchase=purchase_requested is True),
        "totalCost": total_cost,
    }
    with pytest.raises(InvalidResponseError, match=r"\(total_cost\)"):
        parse_historical_buyer_transfer_match(
            payload,
            criteria=historical_criteria(),
            purchase_requested=purchase_requested,
        )


@pytest.mark.parametrize("property_type", RESIDENTIAL_PROPERTY_TYPES)
@pytest.mark.parametrize("purchase_requested", [False, True, None])
def test_historical_returned_residential_property_type_records_its_basis(
    property_type: str, purchase_requested: bool | None
) -> None:
    payload = {
        **historical_envelope(purchase=purchase_requested is True),
        "results": [{"RadarID": "P-SYNTHETIC-HISTORY", "PType": property_type}],
    }
    result = parse_historical_buyer_transfer_match(
        payload, criteria=historical_criteria(), purchase_requested=purchase_requested
    )

    assert result.linkage is not None
    assert result.linkage.property.property_type == property_type
    assert result.linkage.property.is_residential is True
    assert result.linkage.property.residential_basis == "property_type"


@pytest.mark.parametrize("property_type", NON_RESIDENTIAL_PROPERTY_TYPES)
def test_historical_preview_property_type_outside_the_criterion_fails_closed(
    property_type: str,
) -> None:
    payload = historical_rejection_envelope(
        historical_record(PType=property_type), False
    )
    with pytest.raises(
        InvalidResponseError, match=r"\(property_type_outside_criterion\)"
    ) as caught:
        parse_historical_buyer_transfer_match(
            payload, criteria=historical_criteria(), purchase_requested=False
        )
    assert property_type not in str(caught.value)
    assert_record_rejection(
        caught.value,
        "property_type_outside_criterion",
        historical_rejection_evidence(False),
    )


@pytest.mark.parametrize("property_type", ["Commercial", "Unknown"])
def test_historical_live_one_hit_preview_outside_the_criterion_has_evidence(
    property_type: str,
) -> None:
    payload = {
        **live_one_hit_radar_id_only_preview(),
        "results": [{"RadarID": "P-SYNTHETIC-HISTORY", "PType": property_type}],
    }
    with pytest.raises(BuyerTransferResponseError) as caught:
        parse_historical_buyer_transfer_match(
            payload, criteria=historical_criteria(), purchase_requested=False
        )

    assert_record_rejection(
        caught.value,
        "property_type_outside_criterion",
        live_one_hit_preview_evidence(),
    )


@pytest.mark.parametrize(
    ("property_type", "residential"),
    [
        *((name, True) for name in RESIDENTIAL_PROPERTY_TYPES),
        *((name, False) for name in DOCUMENTED_NON_RESIDENTIAL_PROPERTY_TYPES),
        ("Unknown", None),
    ],
)
@pytest.mark.parametrize("purchase_requested", [True, None])
def test_historical_paid_and_detached_parses_classify_the_returned_property_type(
    property_type: str, residential: bool | None, purchase_requested: bool | None
) -> None:
    value = historical_criteria()
    payload = historical_rejection_envelope(
        historical_record(PType=property_type), purchase_requested
    )
    result = parse_historical_buyer_transfer_match(
        payload, criteria=value, purchase_requested=purchase_requested
    )

    assert result.matched is True
    assert result.linkage is not None
    property_value = result.linkage.property
    assert property_value.property_type == property_type
    assert property_value.residential_basis == "property_type"
    assert property_value.is_residential is residential
    assert result.billing == historical_rejection_evidence(purchase_requested)
    assert result.scope_fingerprint == buyer_transfer_scope_fingerprint(value)
    assert result.linkage.scope_fingerprint == result.scope_fingerprint


@pytest.mark.parametrize(
    "record",
    [
        pytest.param({"RadarID": "P-SYNTHETIC-HISTORY"}, id="radar_id_only"),
        pytest.param(historical_record_without_property_type(), id="all_but_ptype"),
    ],
)
@pytest.mark.parametrize("purchase_requested", [True, None])
def test_historical_paid_and_detached_parses_without_a_ptype_leave_it_unknown(
    record: dict[str, object], purchase_requested: bool | None
) -> None:
    payload = historical_rejection_envelope(record, purchase_requested)
    result = parse_historical_buyer_transfer_match(
        payload, criteria=historical_criteria(), purchase_requested=purchase_requested
    )

    assert result.linkage is not None
    property_value = result.linkage.property
    assert property_value.property_type is None
    assert property_value.residential_basis is None
    assert property_value.is_residential is None


@pytest.mark.parametrize(
    "record",
    [
        pytest.param({"RadarID": "P-SYNTHETIC-HISTORY"}, id="radar_id_only"),
        pytest.param(historical_record_without_property_type(), id="all_but_ptype"),
    ],
)
def test_historical_preview_without_a_ptype_follows_the_residential_criterion(
    record: dict[str, object],
) -> None:
    payload = historical_rejection_envelope(record, False)
    result = parse_historical_buyer_transfer_match(
        payload, criteria=historical_criteria(), purchase_requested=False
    )

    assert result.linkage is not None
    property_value = result.linkage.property
    assert property_value.property_type is None
    assert property_value.residential_basis == "property_type_criterion"
    assert property_value.is_residential is True


def test_historical_property_type_criterion_basis_classifies_without_a_ptype() -> None:
    value = historical_property(
        returned_fields=FIELDS_WITHOUT_PROPERTY_TYPE,
        property_type=None,
        residential_basis="property_type_criterion",
    )

    assert value.is_residential is True
    rendered = repr(value)
    assert re.search(r"residential_basis='?property_type_criterion'?[,)]", rendered)
    assert "SYNTHETIC-PARCEL" not in rendered
    assert historical_property(residential_basis="property_type").is_residential


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"residential_basis": "property_type_criterion"},
            "residential_basis property_type_criterion requires no PType",
        ),
        (
            {
                "returned_fields": FIELDS_WITHOUT_PROPERTY_TYPE,
                "property_type": None,
                "residential_basis": "property_type",
            },
            "residential_basis property_type requires a documented PType",
        ),
        (
            {"residential_basis": "synthetic_guess"},
            "residential_basis is not a documented classification basis",
        ),
        (
            {"residential_basis": False},
            "residential_basis is not a documented classification basis",
        ),
    ],
)
def test_historical_residential_basis_rejects_contradictory_manual_states(
    changes: dict[str, object], message: str
) -> None:
    # Without a basis the same values are a valid 0.4.1 direct construction,
    # so only the residential_basis rule can raise below.
    historical_property(**{**changes, "residential_basis": None})
    with pytest.raises(ValueError) as caught:
        historical_property(**changes)
    assert str(caught.value) == message
    assert "SYNTHETIC-PARCEL" not in str(caught.value)
    assert "P-SYNTHETIC-HISTORY" not in str(caught.value)


@pytest.mark.parametrize(
    ("property_type", "residential"),
    [
        *((name, True) for name in RESIDENTIAL_PROPERTY_TYPES),
        *((name, False) for name in DOCUMENTED_NON_RESIDENTIAL_PROPERTY_TYPES),
        ("Unknown", None),
    ],
)
def test_historical_property_type_basis_accepts_every_documented_property_type(
    property_type: str, residential: bool | None
) -> None:
    # A paid result records basis property_type for any documented PType.
    value = historical_property(
        property_type=property_type, residential_basis="property_type"
    )

    assert value.residential_basis == "property_type"
    assert value.is_residential is residential
    assert "SYNTHETIC-PARCEL" not in repr(value)


def test_historical_preview_and_paid_results_bind_the_same_scope_fingerprint() -> None:
    value = historical_criteria()
    expected = buyer_transfer_scope_fingerprint(value)
    preview = parse_historical_buyer_transfer_match(
        live_one_hit_radar_id_only_preview(),
        criteria=value,
        purchase_requested=False,
    )
    paid = parse_historical_buyer_transfer_match(
        historical_paid_envelope(), criteria=value, purchase_requested=True
    )
    bare = parse_historical_buyer_transfer_match(
        live_bare_zero_hit_preview(), criteria=value, purchase_requested=False
    )

    for result in (preview, paid):
        assert result.scope_fingerprint == expected
        assert result.linkage is not None
        assert result.linkage.scope_fingerprint == expected
    assert bare.scope_fingerprint == expected
    assert expected == HISTORICAL_SCOPE_FINGERPRINT
    assert preview.linkage is not None
    assert preview.linkage.property.residential_basis == "property_type_criterion"
    assert paid.linkage is not None
    assert paid.linkage.property.residential_basis == "property_type"
    assert paid.linkage.property.zip_five == "00501"


def test_historical_preview_invariants_follow_the_returned_record() -> None:
    preview = parse_historical_buyer_transfer_match(
        live_one_hit_radar_id_only_preview(),
        criteria=historical_criteria(),
        purchase_requested=False,
    )
    bare = parse_historical_buyer_transfer_match(
        live_bare_zero_hit_preview(),
        criteria=historical_criteria(),
        purchase_requested=False,
    )
    assert preview.linkage is not None

    with pytest.raises(ValueError, match="presence"):
        replace(preview, linkage=None)
    with pytest.raises(ValueError, match="presence"):
        replace(bare, linkage=preview.linkage)
    # A preview count of 1 is valid without the marker; with it, it is not.
    replace(bare.billing, provider_metadata_omitted=False, total_result_count=1)
    with pytest.raises(ValueError):
        replace(bare.billing, total_result_count=1)


def test_historical_contract_no_longer_matches_the_0_4_1_fingerprint() -> None:
    result = parse_historical_buyer_transfer_match(
        live_one_hit_radar_id_only_preview(),
        criteria=historical_criteria(),
        purchase_requested=False,
    )

    with pytest.raises(ValueError, match="contract_fingerprint"):
        replace(result, contract_fingerprint=HISTORICAL_CONTRACT_FINGERPRINT_0_4_1)


# Every rejection of the returned record, with the reason it reports. The
# preview-only property_type_outside_criterion has its own tests above.
HISTORICAL_RECORD_REJECTIONS = [
    pytest.param("P-SYNTHETIC-HISTORY", "property_type", id="non_object_record"),
    pytest.param(FailingRecordMapping(), "property_snapshot", id="property_snapshot"),
    pytest.param(
        {1: "P-SYNTHETIC-HISTORY"}, "property_key_type", id="property_key_type"
    ),
    pytest.param(
        {**historical_record(), "Owner": "PRIVATE"},
        "undocumented_property_fields",
        id="undocumented_property_fields",
    ),
    pytest.param(
        {"Address": "1 Synthetic Way"}, "missing_radar_id", id="missing_radar_id"
    ),
    pytest.param(historical_record(RadarID=""), "radar_id", id="radar_id"),
    pytest.param(
        historical_record(RadarID="P-SYNTHETIC-DIFFERENT"),
        "radar_id_mismatch",
        id="radar_id_mismatch",
    ),
    pytest.param(historical_record(FIPS="49A35"), "fips", id="fips"),
    pytest.param(historical_record(FIPS="49049"), "fips_mismatch", id="fips_mismatch"),
    pytest.param(
        historical_record(PType="Spaceship"),
        "property_type",
        id="undocumented_property_type",
    ),
    pytest.param(historical_record(Address=1), "address", id="address"),
    pytest.param(historical_record(City=1), "city", id="city"),
    pytest.param(historical_record(State=1), "state", id="state"),
    pytest.param(historical_record(ZipFive=501), "zip_five", id="zip_five"),
    pytest.param(historical_record(County=1), "county", id="county"),
    pytest.param(historical_record(APN=1), "apn", id="apn"),
    pytest.param(historical_record(Latitude=91), "latitude", id="latitude"),
    pytest.param(
        historical_record(Longitude=float("nan")), "longitude", id="longitude"
    ),
]


@pytest.mark.parametrize(("record", "reason"), HISTORICAL_RECORD_REJECTIONS)
@pytest.mark.parametrize("purchase_requested", [True, False, None])
def test_historical_record_rejection_raises_response_error_with_evidence(
    record: object, reason: str, purchase_requested: bool | None
) -> None:
    payload = historical_rejection_envelope(record, purchase_requested)
    with pytest.raises(BuyerTransferResponseError) as caught:
        parse_historical_buyer_transfer_match(
            payload,
            criteria=historical_criteria(),
            purchase_requested=purchase_requested,
        )

    assert_record_rejection(
        caught.value, reason, historical_rejection_evidence(purchase_requested)
    )


def test_historical_record_rejection_cases_cover_every_contract_reason() -> None:
    policy = BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT["parser_policy"]
    assert type(policy) is MappingProxyType
    contract_reasons = policy["failure_billing_evidence"]["record_rejection_reasons"]
    covered = {param.values[1] for param in HISTORICAL_RECORD_REJECTIONS}

    assert "property_type_outside_criterion" not in covered
    assert covered | {"property_type_outside_criterion"} == set(contract_reasons)
    assert tuple(contract_reasons) == RECORD_REJECTION_REASONS


def test_historical_paid_rejection_evidence_holds_the_parsed_cost_and_counts() -> None:
    payload = {
        **historical_rejection_envelope(
            historical_record(FIPS="49049"), purchase_requested=True
        ),
        "totalCost": 7.25,
    }
    with pytest.raises(InvalidResponseError) as caught:
        parse_historical_buyer_transfer_match(
            payload, criteria=historical_criteria(), purchase_requested=True
        )

    error = caught.value
    assert isinstance(error, BuyerTransferResponseError)
    assert str(error) == (
        "PropertyRadar returned invalid buyer-transfer match (fips_mismatch)."
    )
    evidence = error.billing_evidence
    assert evidence.purchase_requested is True
    assert evidence.status == "charged"
    assert type(evidence.total_cost) is Decimal
    assert evidence.total_cost == Decimal("7.25")
    assert evidence.currency is None
    assert evidence.quantity_free_remaining is None
    assert evidence.result_count == 1
    assert evidence.total_result_count == 1
    assert evidence.provider_metadata_omitted is False


@pytest.mark.parametrize(
    ("payload", "purchase_requested", "reason"),
    [
        pytest.param(
            {
                **historical_rejection_envelope(
                    historical_record(RadarID="P-SYNTHETIC-DIFFERENT"), True
                ),
                "totalCost": -1,
            },
            True,
            "total_cost",
            id="total_cost_before_radar_id_mismatch",
        ),
        pytest.param(
            {
                **historical_rejection_envelope("P-SYNTHETIC-HISTORY", False),
                "totalCost": "1e3",
            },
            False,
            "total_cost",
            id="total_cost_before_non_object_record",
        ),
        pytest.param(
            {
                **historical_rejection_envelope(historical_record(FIPS="49049"), False),
                "maxDistanceMiles": 251,
            },
            False,
            "max_distance_miles",
            id="max_distance_miles_before_fips_mismatch",
        ),
        pytest.param(
            {
                **historical_rejection_envelope(FailingRecordMapping(), None),
                "nextPageToken": "synthetic-next-page",
            },
            None,
            "next_page_token",
            id="next_page_token_before_record_snapshot",
        ),
        pytest.param(
            {
                **historical_rejection_envelope(historical_record(Address=1), True),
                "facets": {"State": {"UT": 1}},
            },
            True,
            "facets",
            id="facets_before_address",
        ),
        pytest.param(
            {**historical_rejection_envelope(None, False), "results": [None, None]},
            False,
            "ambiguous_results",
            id="ambiguous_results_of_non_object_items",
        ),
        pytest.param(
            {
                **historical_rejection_envelope(None, True),
                "resultCount": 0,
                "totalResultCount": 0,
            },
            True,
            "result_count_mismatch",
            id="counts_before_non_object_record",
        ),
        pytest.param(
            {
                **historical_rejection_envelope(
                    historical_record(RadarID="P-SYNTHETIC-DIFFERENT"), True
                ),
                "quantityFreeRemaining": 99,
            },
            True,
            "charged_preview_metadata",
            id="charged_preview_metadata_before_radar_id_mismatch",
        ),
        pytest.param(
            {
                **historical_rejection_envelope(
                    historical_record(RadarID="P-SYNTHETIC-DIFFERENT"), None
                ),
                "quantityFreeRemaining": -1,
            },
            None,
            "quantity_free_remaining",
            id="quantity_free_remaining_before_radar_id_mismatch",
        ),
    ],
)
def test_historical_envelope_and_metadata_rejections_stay_plain_errors(
    payload: dict[str, object], purchase_requested: bool | None, reason: str
) -> None:
    with pytest.raises(InvalidResponseError) as caught:
        parse_historical_buyer_transfer_match(
            payload,
            criteria=historical_criteria(),
            purchase_requested=purchase_requested,
        )

    assert_earlier_rejection(caught.value, reason)
