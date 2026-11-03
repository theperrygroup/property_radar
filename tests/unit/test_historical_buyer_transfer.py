from __future__ import annotations

import hashlib
import json
import traceback
from collections.abc import Callable, Mapping
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType

import httpx
import pytest

from property_radar import (
    BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT,
    BUYER_TRANSFER_MATCH_CONTRACT,
    BUYER_TRANSFER_PROPERTY_FIELDS,
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


class DateSubclass(date):
    pass


class StringSubclass(str):
    pass


class IntegerSubclass(int):
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
    assert contract["api_version"] == "5.3.1.0"
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
    "record",
    [
        {},
        {"RadarID": "P-SYNTHETIC-HISTORY", "FIPS": "49049"},
        {"RadarID": "P-SYNTHETIC-HISTORY", "FIPS": "synthetic-private-fips"},
        {"RadarID": "P-SYNTHETIC-HISTORY", "PType": "Undocumented"},
        {"RadarID": "P-SYNTHETIC-HISTORY", "Unknown": "synthetic-private-value"},
    ],
)
def test_historical_parser_rejects_missing_or_inconsistent_property_identity(
    record: dict[str, object],
) -> None:
    payload = {**historical_envelope(), "results": [record]}
    with pytest.raises(InvalidResponseError) as caught:
        parse_historical_buyer_transfer_match(payload, criteria=historical_criteria())
    assert "synthetic-private" not in str(caught.value)


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
        return httpx.Response(200, json=historical_envelope())

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
