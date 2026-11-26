from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal
from typing import cast

import httpx
import pytest

import property_radar
from property_radar import (
    BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT,
    BUYER_TRANSFER_MATCH_CONTRACT,
    HISTORICAL_TRANSACTION_CONTRACT,
    HISTORICAL_TRANSACTION_FIELDS,
    TRANSACTION_HISTORY_CONTRACT,
    TRANSACTION_HISTORY_FIELDS,
    HistoricalTransactionDateRange,
    HistoricalTransactionField,
    HistoricalTransactionQuery,
    HistoricalTransactionRecord,
    HistoricalTransactionResponseError,
    InvalidResponseError,
    PropertyRadarClient,
    ServerError,
    TransactionHistoryRecord,
    _record_scalars,
    parse_historical_transaction_result,
    parse_transaction_history,
)


class StringSubclass(str):
    pass


class IntSubclass(int):
    pass


class FloatSubclass(float):
    pass


HISTORICAL_FIELD_TYPE_ERROR = (
    r"^PropertyRadar returned invalid historical transactions \(record_field_type\)\.$"
)
OLDER_FIELD_TYPE_ERROR = (
    r"^PropertyRadar returned invalid transaction history \(record_field_type\)\.$"
)
RECORD_NUMBER_POLICY = (
    "finite_float_decimal_repr_plain_form_absolute_value_maximum_64_characters_signed"
)
RECORD_VALUE_BASIS = (
    "spec_declares_strings_live_integers_observed_floats_booleans_nulls_tolerated"
)
# 0.4.3 changes neither buyer-transfer contract.
BUYER_TRANSFER_MATCH_CONTRACT_FINGERPRINT = (
    # pragma: allowlist nextline secret
    "580b955265f3f7928ea1bddba03e7244ceaff8f27fd6844343e05d6ae81bc01c"
)
BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT_FINGERPRINT = (
    # pragma: allowlist nextline secret
    "61ab6cc9e609ad3082124e1bc520c9578760a75ddff0ba989c714c72dcbfc906"
)

# One synthetic row with every field both parsers share, in field order.
SHARED_ROW: dict[str, object] = {
    "DocTypeUI": "Synthetic Deed",
    "Status": "original",
    "Purpose": "Synthetic Market",
    "LoanPosition": "1",
    "DocNumber": "SYNTHETIC-0001",
    "RecDate": "2020-06-12",
    "Grantor": "SYNTHETIC SELLER LLC",
    "Grantee": "SYNTHETIC BUYER LLC",
    "Amount": "250000",
    "LTVorDown": "80",
    "hasDocumentImage": "0",
    "isFirstCurrentOwnerRecord": "1",
    "isParentType": "1",
    "DocumentID": "D-SYNTHETIC-1",
}
HISTORICAL_ROW: dict[str, object] = {
    **SHARED_ROW,
    "RadarID": "P-SYNTHETIC",
    "DocType": "GRT",
    "DocGroup": "Deed",
}
OLDER_ATTRIBUTES = {
    "DocTypeUI": "document_type_ui",
    "Status": "status",
    "Purpose": "purpose",
    "LoanPosition": "loan_position",
    "DocNumber": "document_number",
    "RecDate": "recording_date",
    "Grantor": "grantor_display",
    "Grantee": "grantee_display",
    "Amount": "amount",
    "LTVorDown": "ltv_or_down",
    "hasDocumentImage": "has_document_image",
    "isFirstCurrentOwnerRecord": "is_first_current_owner_record",
    "isParentType": "is_parent_type",
    "DocumentID": "document_id",
}
HISTORICAL_PROPERTIES = {
    "DocTypeUI": "document_type_ui",
    "Status": "status",
    "RecDate": "recording_date",
    "Grantor": "grantor_display",
    "Grantee": "grantee_display",
    "Amount": "amount",
    "DocumentID": "document_id",
    "RadarID": "radar_id",
    "DocType": "document_type",
    "DocGroup": "doc_group",
}

# SPEC.md accept table: both parsers keep each value as this exact text.
ACCEPTED = [
    pytest.param("Amount", 250000, "250000", id="int-amount"),
    pytest.param("Amount", -5, "-5", id="int-negative"),
    pytest.param("Amount", 0, "0", id="int-zero"),
    pytest.param("Amount", 10**64 - 1, "9" * 64, id="int-64-digits"),
    pytest.param("Amount", -(10**64 - 1), "-" + "9" * 64, id="int-negative-64-digits"),
    pytest.param("LTVorDown", 80, "80", id="int-ltv"),
    pytest.param("LTVorDown", 80.0, "80.0", id="float-whole"),
    pytest.param("LTVorDown", 80.5, "80.5", id="float-half"),
    pytest.param("LTVorDown", 80.25, "80.25", id="float-quarter"),
    pytest.param("LTVorDown", 1e16, "10000000000000000", id="float-1e16-plain"),
    pytest.param("LTVorDown", 1e-7, "0.0000001", id="float-1e-7-plain"),
    pytest.param("LTVorDown", 1e63, "1" + "0" * 63, id="float-1e63-64-characters"),
    pytest.param(
        "LTVorDown", 1e-62, "0." + "0" * 61 + "1", id="float-1e-62-64-characters"
    ),
    pytest.param("LTVorDown", -1.5, "-1.5", id="float-negative"),
    pytest.param("LTVorDown", 0.0, "0.0", id="float-zero"),
    pytest.param("isFirstCurrentOwnerRecord", 1, "1", id="flag-int-one"),
    pytest.param("isFirstCurrentOwnerRecord", 0, "0", id="flag-int-zero"),
    pytest.param("isFirstCurrentOwnerRecord", True, "1", id="flag-true"),
    pytest.param("isFirstCurrentOwnerRecord", False, "0", id="flag-false"),
    pytest.param("isParentType", "1", "1", id="flag-string-one"),
    pytest.param("hasDocumentImage", True, "1", id="flag-true-document-image"),
    pytest.param("hasDocumentImage", 1.0, "1.0", id="flag-float"),
    pytest.param("DocumentID", 123, "123", id="int-document-id"),
    pytest.param("Grantor", 7, "7", id="int-grantor"),
    pytest.param("DocTypeUI", "S" * 100, "S" * 100, id="string-unbounded"),
]
# SPEC.md reject table: both parsers fail with record_field_type.
REJECTED = [
    pytest.param("LTVorDown", math.nan, id="float-nan"),
    pytest.param("LTVorDown", math.inf, id="float-infinity"),
    pytest.param("LTVorDown", -math.inf, id="float-negative-infinity"),
    pytest.param("LTVorDown", -0.0, id="float-negative-zero"),
    pytest.param("Amount", 10**64, id="int-65-digits"),
    pytest.param("Amount", -(10**64), id="int-negative-65-digits"),
    pytest.param("LTVorDown", 1e64, id="float-1e64-65-characters"),
    pytest.param("LTVorDown", -1e64, id="float-negative-1e64"),
    pytest.param("LTVorDown", 1e-63, id="float-1e-63-65-characters"),
    pytest.param("LTVorDown", 5e-324, id="float-smallest-subnormal"),
    pytest.param("Amount", 10**4300, id="int-4301-digits"),
    pytest.param("Amount", {}, id="empty-object"),
    pytest.param("Amount", {"a": 1}, id="object"),
    pytest.param("Amount", [1], id="array"),
    pytest.param("Amount", (1,), id="tuple"),
    pytest.param("Amount", Decimal("1"), id="decimal"),
    pytest.param("Amount", b"1", id="bytes"),
    pytest.param("DocumentID", StringSubclass("D-SYNTHETIC"), id="str-subclass"),
    pytest.param("Amount", IntSubclass(1), id="int-subclass"),
    pytest.param("LTVorDown", FloatSubclass(1.5), id="float-subclass"),
    pytest.param("Amount", True, id="true-in-amount"),
    pytest.param("DocumentID", True, id="true-in-document-id"),
    pytest.param("Status", 1, id="int-in-status"),
    pytest.param("Status", True, id="true-in-status"),
    pytest.param("Status", 1.5, id="float-in-status"),
    pytest.param("RecDate", None, id="null-recording-date"),
    pytest.param("RecDate", 20200612, id="int-recording-date"),
    pytest.param("RecDate", 2020.5, id="float-recording-date"),
    pytest.param("RecDate", True, id="true-recording-date"),
]
HISTORICAL_ONLY_REJECTED = [
    pytest.param("DocGroup", 1, id="int-in-doc-group"),
    pytest.param("DocGroup", True, id="true-in-doc-group"),
]
OLDER_ONLY_REJECTED = [
    pytest.param("RecDate", ["2020-06-12"], id="recording-date-list"),
]
# One value table for the parity test, sent through every shared field.
PARITY_VALUES = [
    pytest.param("original", id="string"),
    pytest.param(250000, id="int"),
    pytest.param(-5, id="int-negative"),
    pytest.param(0, id="int-zero"),
    pytest.param(1, id="int-one"),
    pytest.param(10**64 - 1, id="int-64-digits"),
    pytest.param(10**64, id="int-65-digits"),
    pytest.param(10**4300, id="int-4301-digits"),
    pytest.param(80.0, id="float-whole"),
    pytest.param(80.25, id="float-quarter"),
    pytest.param(1e-7, id="float-1e-7"),
    pytest.param(1e63, id="float-1e63"),
    pytest.param(1e64, id="float-1e64"),
    pytest.param(1e-62, id="float-1e-62"),
    pytest.param(1e-63, id="float-1e-63"),
    pytest.param(-1.5, id="float-negative"),
    pytest.param(0.0, id="float-zero"),
    pytest.param(-0.0, id="float-negative-zero"),
    pytest.param(math.nan, id="float-nan"),
    pytest.param(math.inf, id="float-infinity"),
    pytest.param(-math.inf, id="float-negative-infinity"),
    pytest.param(5e-324, id="float-smallest-subnormal"),
    pytest.param(True, id="true"),
    pytest.param(False, id="false"),
    pytest.param(None, id="null"),
    pytest.param(Decimal("1"), id="decimal"),
    pytest.param(b"1", id="bytes"),
    pytest.param({}, id="object"),
    pytest.param(StringSubclass("original"), id="str-subclass"),
    pytest.param(IntSubclass(1), id="int-subclass"),
    pytest.param(FloatSubclass(1.5), id="float-subclass"),
]
SHARED_FIELDS = [pytest.param(name, id=name) for name in TRANSACTION_HISTORY_FIELDS]

# Live-shaped synthetic wire row: int Amount, int LTVorDown, int flag, string
# flag, LoanPosition and hasDocumentImage omitted, and a null Purpose.
WIRE_ROW = (
    '{"DocTypeUI":"Synthetic Deed","Status":"original","Purpose":null,'
    '"DocNumber":"SYNTHETIC-0001","RecDate":"2020-06-12",'
    '"Grantor":"SYNTHETIC SELLER LLC","Grantee":"SYNTHETIC BUYER LLC",'
    '"Amount":250000,"LTVorDown":80,"isFirstCurrentOwnerRecord":1,'
    '"isParentType":"1","DocumentID":"D-SYNTHETIC-1"}'
)
WIRE_BODY = (
    '{"results":['
    + WIRE_ROW
    + '],"resultCount":1,"totalResultCount":1,"totalCost":0.25}'
)
WIRE_TEXT = {
    "DocTypeUI": "Synthetic Deed",
    "Status": "original",
    "DocNumber": "SYNTHETIC-0001",
    "RecDate": "2020-06-12",
    "Grantor": "SYNTHETIC SELLER LLC",
    "Grantee": "SYNTHETIC BUYER LLC",
    "Amount": "250000",
    "LTVorDown": "80",
    "isFirstCurrentOwnerRecord": "1",
    "isParentType": "1",
    "DocumentID": "D-SYNTHETIC-1",
}
WIRE_MISSING = ("Purpose", "LoanPosition", "hasDocumentImage")


def historical_query() -> HistoricalTransactionQuery:
    return HistoricalTransactionQuery(
        radar_id="P-SYNTHETIC",
        recording_dates=HistoricalTransactionDateRange(
            start=date(2020, 1, 1), end=date(2020, 12, 31)
        ),
        limit=1,
    )


def paid_envelope(row: Mapping[str, object]) -> dict[str, object]:
    """Return a Purchase=1 envelope that both parsers accept around one row."""
    return {
        "results": [dict(row)],
        "resultCount": 1,
        "totalResultCount": 1,
        "totalCost": "0.25",
    }


def historical_record(field: str, value: object) -> HistoricalTransactionRecord:
    result = parse_historical_transaction_result(
        paid_envelope({**HISTORICAL_ROW, field: value}), query=historical_query()
    )
    (record,) = result.records
    return record


def older_record(field: str, value: object) -> TransactionHistoryRecord:
    history = parse_transaction_history(
        paid_envelope({**SHARED_ROW, field: value}), purchase_requested=True
    )
    (record,) = history.records
    return record


def historical_fields(record: HistoricalTransactionRecord) -> Mapping[str, object]:
    return cast(Mapping[str, object], record.fields)


def older_texts(record: TransactionHistoryRecord) -> dict[str, object]:
    return {
        name: getattr(record, OLDER_ATTRIBUTES[name]) for name in record.returned_fields
    }


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


def test_both_parsers_share_fourteen_fields_and_the_fixtures_cover_them() -> None:
    assert len(TRANSACTION_HISTORY_FIELDS) == 14
    assert HISTORICAL_TRANSACTION_FIELDS[:14] == TRANSACTION_HISTORY_FIELDS
    assert tuple(SHARED_ROW) == TRANSACTION_HISTORY_FIELDS
    assert tuple(HISTORICAL_ROW) == HISTORICAL_TRANSACTION_FIELDS
    assert tuple(OLDER_ATTRIBUTES) == TRANSACTION_HISTORY_FIELDS
    assert set(HISTORICAL_PROPERTIES) <= set(HISTORICAL_TRANSACTION_FIELDS)


def test_shared_module_publishes_the_exact_rule_constants() -> None:
    assert _record_scalars.RECORD_FLAG_FIELDS == (
        "hasDocumentImage",
        "isFirstCurrentOwnerRecord",
        "isParentType",
    )
    assert _record_scalars.RECORD_ENUM_FIELDS == ("Status", "DocGroup")
    assert _record_scalars.RECORD_VALUE_TYPES == (
        "string",
        "integer",
        "number",
        "boolean",
        "null",
    )
    assert _record_scalars.RECORD_STRING_POLICY == "exact_str_preserved"
    assert _record_scalars.RECORD_NULL_POLICY == "omitted_preserved_as_unavailable"
    assert _record_scalars.RECORD_BOOLEAN_POLICY == "flag_fields_only_true_1_false_0"
    assert _record_scalars.RECORD_INTEGER_POLICY == (
        "exact_int_absolute_value_maximum_64_digits_signed_decimal_text"
    )
    assert _record_scalars.RECORD_NUMBER_POLICY == RECORD_NUMBER_POLICY
    assert _record_scalars.RECORD_ENUM_POLICY == "exact_str_or_null_only"
    assert _record_scalars.RECORD_VALUE_BASIS == RECORD_VALUE_BASIS


def test_shared_module_stays_private() -> None:
    public_names = set(property_radar.__all__)
    assert "_record_scalars" not in public_names
    assert "record_scalar_text" not in public_names
    assert "record_value_omitted" not in public_names


def test_both_contracts_publish_the_shared_module_rule() -> None:
    historical = HISTORICAL_TRANSACTION_CONTRACT
    assert historical["record_value_types"] == _record_scalars.RECORD_VALUE_TYPES
    assert historical["record_value_string"] == _record_scalars.RECORD_STRING_POLICY
    assert historical["record_value_null"] == _record_scalars.RECORD_NULL_POLICY
    assert historical["record_value_boolean"] == _record_scalars.RECORD_BOOLEAN_POLICY
    assert historical["record_value_boolean_fields"] == (
        _record_scalars.RECORD_FLAG_FIELDS
    )
    assert historical["record_value_integer"] == _record_scalars.RECORD_INTEGER_POLICY
    assert historical["record_value_number"] == _record_scalars.RECORD_NUMBER_POLICY
    assert historical["record_value_enum_fields"] == (
        _record_scalars.RECORD_ENUM_FIELDS
    )
    assert historical["record_value_enum"] == _record_scalars.RECORD_ENUM_POLICY
    assert historical["record_value_basis"] == _record_scalars.RECORD_VALUE_BASIS
    parser_policy = cast(
        Mapping[str, object], TRANSACTION_HISTORY_CONTRACT["parser_policy"]
    )
    older = cast(Mapping[str, object], parser_policy["record_scalars"])
    assert older["string"] == _record_scalars.RECORD_STRING_POLICY
    assert older["null"] == _record_scalars.RECORD_NULL_POLICY
    assert older["boolean"] == _record_scalars.RECORD_BOOLEAN_POLICY
    assert older["boolean_fields"] == _record_scalars.RECORD_FLAG_FIELDS
    assert older["integer"] == _record_scalars.RECORD_INTEGER_POLICY
    assert older["number"] == _record_scalars.RECORD_NUMBER_POLICY
    assert older["enum"] == _record_scalars.RECORD_ENUM_POLICY
    assert older["basis"] == _record_scalars.RECORD_VALUE_BASIS


def test_buyer_transfer_fingerprints_stay_unchanged() -> None:
    assert BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"] == (
        BUYER_TRANSFER_MATCH_CONTRACT_FINGERPRINT
    )
    assert BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT["contract_fingerprint"] == (
        BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT_FINGERPRINT
    )


@pytest.mark.parametrize(("field", "value", "text"), ACCEPTED)
def test_record_scalar_text_gives_the_exact_text_of_each_accepted_value(
    field: str, value: object, text: str
) -> None:
    result = _record_scalars.record_scalar_text(field, value)
    assert type(result) is str
    assert result == text
    omitted = _record_scalars.record_value_omitted(field, value)
    assert omitted is False


@pytest.mark.parametrize(
    ("field", "value"), [*REJECTED, *HISTORICAL_ONLY_REJECTED, *OLDER_ONLY_REJECTED]
)
def test_record_scalar_text_gives_none_for_each_rejected_value(
    field: str, value: object
) -> None:
    # The result is checked on its own, so no failure text reprs the value.
    result = _record_scalars.record_scalar_text(field, value)
    assert result is None
    omitted = _record_scalars.record_value_omitted(field, value)
    assert omitted is False


@pytest.mark.parametrize(
    "field", [pytest.param(name, id=name) for name in HISTORICAL_TRANSACTION_FIELDS]
)
def test_record_value_omitted_only_for_a_null_outside_the_recording_date(
    field: str,
) -> None:
    assert _record_scalars.record_value_omitted(field, None) is (field != "RecDate")
    assert _record_scalars.record_scalar_text(field, None) is None
    not_null: tuple[object, ...] = ("", "null", 0, 0.0, False, (), [], {})
    for value in not_null:
        assert _record_scalars.record_value_omitted(field, value) is False


@pytest.mark.parametrize(("field", "value", "text"), ACCEPTED)
def test_historical_parser_keeps_each_accepted_value_as_exact_text(
    field: str, value: object, text: str
) -> None:
    record = historical_record(field, value)
    kept = historical_fields(record)[field]
    assert type(kept) is str
    assert kept == text
    assert record.missing_fields == ()
    if field in HISTORICAL_PROPERTIES:
        assert getattr(record, HISTORICAL_PROPERTIES[field]) == text


@pytest.mark.parametrize(("field", "value", "text"), ACCEPTED)
def test_older_parser_keeps_each_accepted_value_as_exact_text(
    field: str, value: object, text: str
) -> None:
    record = older_record(field, value)
    kept = getattr(record, OLDER_ATTRIBUTES[field])
    assert type(kept) is str
    assert kept == text
    assert record.returned_fields == TRANSACTION_HISTORY_FIELDS


@pytest.mark.parametrize(
    "field",
    [
        pytest.param(name, id=f"null-{name}")
        for name in HISTORICAL_TRANSACTION_FIELDS
        if name != "RecDate"
    ],
)
def test_historical_parser_omits_a_null_outside_the_recording_date(
    field: str,
) -> None:
    record = historical_record(field, None)
    kept = historical_fields(record)
    assert field not in kept
    assert record.missing_fields == (field,)
    assert all(type(value) is str for value in kept.values())
    if field in HISTORICAL_PROPERTIES:
        assert getattr(record, HISTORICAL_PROPERTIES[field]) is None


@pytest.mark.parametrize(
    "field",
    [
        pytest.param(name, id=f"null-{name}")
        for name in TRANSACTION_HISTORY_FIELDS
        if name != "RecDate"
    ],
)
def test_older_parser_omits_a_null_outside_the_recording_date(field: str) -> None:
    record = older_record(field, None)
    assert record.returned_fields == tuple(
        name for name in TRANSACTION_HISTORY_FIELDS if name != field
    )
    assert getattr(record, OLDER_ATTRIBUTES[field]) is None
    assert all(type(value) is str for value in older_texts(record).values())


@pytest.mark.parametrize(("field", "value"), [*REJECTED, *HISTORICAL_ONLY_REJECTED])
def test_historical_parser_rejects_each_value_outside_the_rule(
    field: str, value: object
) -> None:
    with pytest.raises(
        HistoricalTransactionResponseError, match=HISTORICAL_FIELD_TYPE_ERROR
    ) as caught:
        historical_record(field, value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    evidence = caught.value.billing_evidence
    assert evidence.purchase_requested is True
    assert evidence.total_cost == Decimal("0.25")
    assert evidence.result_count == 1
    assert evidence.total_result_count == 1


@pytest.mark.parametrize(("field", "value"), [*REJECTED, *HISTORICAL_ONLY_REJECTED])
def test_historical_record_rejects_each_value_outside_the_rule_directly(
    field: str, value: object
) -> None:
    values = cast(
        Mapping[HistoricalTransactionField, str | tuple[str, ...]],
        {**HISTORICAL_ROW, field: value},
    )
    with pytest.raises(
        InvalidResponseError, match=HISTORICAL_FIELD_TYPE_ERROR
    ) as caught:
        HistoricalTransactionRecord(values)
    assert type(caught.value) is InvalidResponseError
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(("field", "value"), [*REJECTED, *OLDER_ONLY_REJECTED])
def test_older_parser_rejects_each_value_outside_the_rule(
    field: str, value: object
) -> None:
    with pytest.raises(InvalidResponseError, match=OLDER_FIELD_TYPE_ERROR) as caught:
        older_record(field, value)
    assert type(caught.value) is InvalidResponseError
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_historical_recording_date_arrays_keep_their_unchanged_rule() -> None:
    record = historical_record("RecDate", ["2020-06-12", "2020-06-14"])
    assert historical_fields(record)["RecDate"] == ("2020-06-12", "2020-06-14")
    assert record.recording_date_status == "ambiguous_array"
    with pytest.raises(
        HistoricalTransactionResponseError, match=r"\(recording_date_array\)\.$"
    ):
        historical_record("RecDate", [20200612])


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"SyntheticExtra": None}, id="null-under-undocumented-key"),
        pytest.param({"SyntheticExtra": 1}, id="number-under-undocumented-key"),
        pytest.param(
            {"SyntheticExtra": None, "Amount": True, "RecDate": None},
            id="undocumented-key-is-checked-first",
        ),
    ],
)
def test_both_parsers_still_check_undocumented_keys_first(
    changes: dict[str, object],
) -> None:
    with pytest.raises(
        HistoricalTransactionResponseError, match=r"\(undocumented_record_fields\)\.$"
    ):
        parse_historical_transaction_result(
            paid_envelope({**HISTORICAL_ROW, **changes}), query=historical_query()
        )
    with pytest.raises(
        InvalidResponseError, match=r"\(undocumented_record_fields\)\.$"
    ):
        parse_transaction_history(
            paid_envelope({**SHARED_ROW, **changes}), purchase_requested=True
        )


@pytest.mark.parametrize("value", PARITY_VALUES)
@pytest.mark.parametrize("field", SHARED_FIELDS)
def test_both_parsers_follow_the_shared_rule_for_every_shared_field(
    field: str, value: object
) -> None:
    omitted = _record_scalars.record_value_omitted(field, value)
    text = _record_scalars.record_scalar_text(field, value)
    if omitted:
        historical = historical_record(field, value)
        older = older_record(field, value)
        assert field not in historical_fields(historical)
        assert historical.missing_fields == (field,)
        assert field not in older.returned_fields
        assert getattr(older, OLDER_ATTRIBUTES[field]) is None
    elif text is None:
        with pytest.raises(
            HistoricalTransactionResponseError, match=HISTORICAL_FIELD_TYPE_ERROR
        ) as historical_failure:
            historical_record(field, value)
        with pytest.raises(
            InvalidResponseError, match=OLDER_FIELD_TYPE_ERROR
        ) as older_failure:
            older_record(field, value)
        for failure in (historical_failure.value, older_failure.value):
            assert failure.__cause__ is None
            assert failure.__context__ is None
    else:
        historical_text = historical_fields(historical_record(field, value))[field]
        older_text = getattr(older_record(field, value), OLDER_ATTRIBUTES[field])
        assert type(historical_text) is str
        assert type(older_text) is str
        assert historical_text == text
        assert older_text == text


def test_wire_body_decodes_to_the_live_json_types() -> None:
    envelope = json.loads(WIRE_BODY)
    (row,) = envelope["results"]
    assert type(row["Amount"]) is int
    assert type(row["LTVorDown"]) is int
    assert type(row["isFirstCurrentOwnerRecord"]) is int
    assert type(row["isParentType"]) is str
    assert row["Purpose"] is None
    assert "LoanPosition" not in row
    assert "hasDocumentImage" not in row
    assert type(envelope["totalCost"]) is float


def test_raw_transactions_keep_the_decoded_json_for_both_parsers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(WIRE_BODY)

    client, transport = make_client(handler, allow_charges=True)
    try:
        envelope = client.properties.transactions(
            "P-SYNTHETIC", fields=TRANSACTION_HISTORY_FIELDS, purchase=True
        )
    finally:
        transport.close()

    assert envelope == json.loads(WIRE_BODY)
    assert len(requests) == 1
    assert requests[0].url.params["Purchase"] == "1"
    older = parse_transaction_history(envelope, purchase_requested=True)
    historical = parse_historical_transaction_result(envelope, query=historical_query())
    assert older_texts(older.records[0]) == WIRE_TEXT
    assert dict(historical_fields(historical.records[0])) == WIRE_TEXT
    # Neither parser changes the caller's decoded envelope.
    assert envelope == json.loads(WIRE_BODY)


def test_paid_transaction_history_keeps_live_json_scalars_as_exact_text() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(WIRE_BODY)

    client, transport = make_client(handler, allow_charges=True)
    try:
        history = client.properties.transaction_history("P-SYNTHETIC", purchase=True)
    finally:
        transport.close()

    assert history.billing_status == "charged"
    assert history.purchase_requested is True
    assert type(history.total_cost) is Decimal
    assert history.total_cost.as_tuple() == Decimal("0.25").as_tuple()
    assert history.quantity_free_remaining is None
    assert len(history.records) == 1
    assert history.records_withheld is False
    assert history.truncated is False
    assert history.result_count == 1
    assert history.billing.total_result_count == 1
    assert history.total_result_count == 1
    (record,) = history.records
    assert record.amount == "250000"
    assert record.ltv_or_down == "80"
    assert record.is_first_current_owner_record == "1"
    assert record.is_parent_type == "1"
    texts = older_texts(record)
    assert texts == WIRE_TEXT
    assert all(type(value) is str for value in texts.values())
    assert record.returned_fields == tuple(
        name for name in TRANSACTION_HISTORY_FIELDS if name not in WIRE_MISSING
    )
    for name in WIRE_MISSING:
        assert getattr(record, OLDER_ATTRIBUTES[name]) is None
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/v1/properties/P-SYNTHETIC/transactions"
    assert requests[0].url.params["Purchase"] == "1"
    assert requests[0].url.params["Fields"] == ",".join(TRANSACTION_HISTORY_FIELDS)


def test_paid_historical_transactions_keep_live_json_scalars_as_exact_text() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(WIRE_BODY)

    client, transport = make_client(handler, allow_charges=True)
    try:
        result = client.properties.historical_transaction_history(
            query=historical_query(), purchase=True
        )
    finally:
        transport.close()

    assert result.billing_status == "charged"
    assert type(result.total_cost) is Decimal
    assert result.total_cost.as_tuple() == Decimal("0.25").as_tuple()
    assert result.result_count == 1
    assert result.total_result_count == 1
    (record,) = result.records
    kept = historical_fields(record)
    assert dict(kept) == WIRE_TEXT
    assert all(type(value) is str for value in kept.values())
    assert record.missing_fields == (*WIRE_MISSING, "RadarID", "DocType", "DocGroup")
    assert record.amount == "250000"
    assert len(requests) == 1
    assert requests[0].url.path == "/v1/properties/P-SYNTHETIC/transactions"
    assert requests[0].url.params["Purchase"] == "1"
    assert requests[0].url.params["Fields"] == ",".join(HISTORICAL_TRANSACTION_FIELDS)


@pytest.mark.parametrize(
    "token",
    [
        pytest.param('"Amount":true', id="true-amount"),
        pytest.param('"Amount":1e64', id="number-over-64-characters"),
        pytest.param('"Amount":{}', id="object-amount"),
    ],
)
def test_a_rejected_live_scalar_fails_each_paid_request_once(token: str) -> None:
    body = WIRE_BODY.replace('"Amount":250000', token)
    assert body != WIRE_BODY
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(body)

    client, transport = make_client(handler, allow_charges=True)
    try:
        with pytest.raises(InvalidResponseError, match=OLDER_FIELD_TYPE_ERROR) as older:
            client.properties.transaction_history("P-SYNTHETIC", purchase=True)
        assert len(requests) == 1
        with pytest.raises(
            HistoricalTransactionResponseError, match=HISTORICAL_FIELD_TYPE_ERROR
        ) as historical:
            client.properties.historical_transaction_history(
                query=historical_query(), purchase=True
            )
        assert len(requests) == 2
    finally:
        transport.close()

    for caught in (older.value, historical.value):
        assert caught.__cause__ is None
        assert caught.__context__ is None
    assert historical.value.billing_evidence.total_cost == Decimal("0.25")
    assert all(request.url.params["Purchase"] == "1" for request in requests)


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(
            lambda client: client.properties.transaction_history(
                "P-SYNTHETIC", purchase=True
            ),
            id="transaction-history",
        ),
        pytest.param(
            lambda client: client.properties.historical_transaction_history(
                query=historical_query(), purchase=True
            ),
            id="historical-transaction-history",
        ),
    ],
)
def test_paid_live_scalar_requests_are_never_retried(
    call: Callable[[PropertyRadarClient], object],
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503, json={"message": "synthetic failure"})
        return json_response(WIRE_BODY)

    client, transport = make_client(handler, allow_charges=True)
    try:
        with pytest.raises(ServerError):
            call(client)
    finally:
        transport.close()
    assert len(requests) == 1
    assert requests[0].url.params["Purchase"] == "1"
