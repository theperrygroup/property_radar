from __future__ import annotations

import hashlib
import json
import traceback
from collections.abc import Iterator, Mapping
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import cast

import pytest

from property_radar.buyer_transfer import BUYER_TRANSFER_MATCH_CONTRACT
from property_radar.exceptions import InvalidResponseError
from property_radar.historical_transaction import (
    HISTORICAL_TRANSACTION_CONTRACT,
    HISTORICAL_TRANSACTION_FIELDS,
    HistoricalTransactionDateRange,
    HistoricalTransactionField,
    HistoricalTransactionQuery,
    HistoricalTransactionQuote,
    HistoricalTransactionRecord,
    HistoricalTransactionResult,
    parse_historical_transaction_quote,
    parse_historical_transaction_result,
)
from property_radar.transaction_history import (
    TRANSACTION_HISTORY_CONTRACT,
    TRANSACTION_HISTORY_FIELDS,
    parse_transaction_history,
)


class StringSubclass(str):
    pass


class IntSubclass(int):
    pass


class FailingSnapshotMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise RuntimeError("SYNTHETIC_PRIVATE_SNAPSHOT")

    def __iter__(self) -> Iterator[str]:
        return iter(("totalCost", "resultCount", "totalResultCount"))

    def __len__(self) -> int:
        return 3


class HostileDict(dict[str, object]):
    def __iter__(self) -> Iterator[str]:
        raise RuntimeError("SYNTHETIC_PRIVATE_ITERATOR")

    def __getitem__(self, key: str) -> object:
        raise RuntimeError("SYNTHETIC_PRIVATE_ITEM")


class HostileList(list[object]):
    def __iter__(self) -> Iterator[object]:
        raise RuntimeError("SYNTHETIC_PRIVATE_LIST")


class MutatingRecord(Mapping[str, object]):
    def __init__(self, earlier_dates: list[str]) -> None:
        self.earlier_dates = earlier_dates

    def __getitem__(self, key: str) -> object:
        self.earlier_dates.append("SYNTHETIC_LATER_MUTATION")
        return "D-SYNTHETIC-2"

    def __iter__(self) -> Iterator[str]:
        return iter(("DocumentID",))

    def __len__(self) -> int:
        return 1


def query(**changes: object) -> HistoricalTransactionQuery:
    values: dict[str, object] = {
        "radar_id": "P-SYNTHETIC",
        "recording_dates": HistoricalTransactionDateRange(
            date(2020, 1, 1), date(2020, 12, 31)
        ),
        "limit": 2,
        "doc_types": ("GRT", "WRT"),
        "doc_groups": ("Deed",),
    }
    values.update(changes)
    return HistoricalTransactionQuery(**values)  # type: ignore[arg-type]


def row(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "DocumentID": "D-SYNTHETIC-1",
        "RadarID": "P-SYNTHETIC",
        "DocTypeUI": "Synthetic Deed",
        "DocType": "GRT",
        "DocGroup": "Deed",
        "Status": "original",
        "RecDate": "2020-06-12",
        "Grantor": "SYNTHETIC_PRIVATE_GRANTOR",
        "Grantee": "SYNTHETIC_PRIVATE_GRANTEE",
        "Amount": "$123,456",
    }
    values.update(changes)
    return values


def quote_payload(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "totalCost": "0.0000001",
        "resultCount": 2,
        "totalResultCount": 5,
    }
    values.update(changes)
    return values


def paid_payload(**changes: object) -> dict[str, object]:
    values = quote_payload()
    values["results"] = [row(), row(DocumentID="D-SYNTHETIC-2")]
    values.update(changes)
    return values


def parsed_quote(**changes: object) -> HistoricalTransactionQuote:
    return parse_historical_transaction_quote(quote_payload(**changes), query=query())


def parsed_result(**changes: object) -> HistoricalTransactionResult:
    return parse_historical_transaction_result(paid_payload(**changes), query=query())


def typed_row(values: Mapping[str, object]) -> HistoricalTransactionRecord:
    return HistoricalTransactionRecord(
        cast(Mapping[HistoricalTransactionField, str | tuple[str, ...]], values)
    )


def test_contract_has_current_provenance_and_distinct_stable_fingerprint() -> None:
    contract = HISTORICAL_TRANSACTION_CONTRACT
    assert isinstance(contract, MappingProxyType)
    assert contract["contract_version"] == "1.0"
    assert contract["api_version"] == "5.3.1.0"
    assert (
        contract["spec_source"] == "https://developers.propertyradar.com/_spec/api.json"
    )
    assert contract["spec_source_sha256"] == (
        # pragma: allowlist nextline secret
        "9feadf6a8fade0530045f4d6f14db69f520144078a71637ef6c999aea8493c14"
    )
    assert contract["ordered_fields"] == HISTORICAL_TRANSACTION_FIELDS
    assert contract["record_fields_required_by_provider"] == ()
    assert contract["provider_limit_maximum"] is None
    assert contract["currency"] is None
    assert contract["automatic_retries"] is False
    assert "unspecified" in str(contract["recording_dates"])
    source = dict(contract)
    fingerprint = source.pop("contract_fingerprint")
    encoded = json.dumps(
        source, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    assert fingerprint == hashlib.sha256(encoded).hexdigest()
    assert fingerprint != TRANSACTION_HISTORY_CONTRACT["contract_fingerprint"]
    assert fingerprint != BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"]
    with pytest.raises(TypeError):
        contract["api_version"] = "changed"  # type: ignore[index]


def test_explicit_date_range_and_query_encode_bounded_provider_parameters() -> None:
    request = query(filter="CurrentOwner")
    expected = {
        "Fields": ",".join(
            (*TRANSACTION_HISTORY_FIELDS, "RadarID", "DocType", "DocGroup")
        ),
        "Purchase": 0,
        "Filter": "CurrentOwner",
        "RecDate": "from: 01/01/2020 to: 12/31/2020",
        "Limit": 2,
        "DocType": "GRT,WRT",
        "DocGroup": "Deed",
    }
    assert request.params(purchase=False) == expected
    assert request.params(purchase=True) == {**expected, "Purchase": 1}
    assert len(HISTORICAL_TRANSACTION_FIELDS) == 17
    assert len(set(HISTORICAL_TRANSACTION_FIELDS)) == 17
    assert query(doc_types=(), doc_groups=()).params(purchase=False) == {
        key: value
        for key, value in expected.items()
        if key not in {"DocType", "DocGroup"}
    } | {"Filter": "All"}
    assert HistoricalTransactionDateRange(
        date(1, 1, 1), date(1, 1, 1)
    ).as_provider_value() == ("from: 01/01/0001 to: 01/01/0001")


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2020, 2, 1), date(2020, 1, 1)),
        (datetime(2020, 1, 1), date(2020, 1, 1)),
        (date(2020, 1, 1), datetime(2020, 1, 1)),
        ("2020-01-01", date(2020, 1, 1)),
        (date(2020, 1, 1), None),
    ],
)
def test_date_range_requires_exact_complete_ordered_dates(
    start: object, end: object
) -> None:
    with pytest.raises(ValueError, match="recording date"):
        HistoricalTransactionDateRange(start, end)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"radar_id": ""},
        {"radar_id": "P" * 129},
        {"radar_id": "P/unsafe"},
        {"radar_id": " P-SYNTHETIC"},
        {"radar_id": StringSubclass("P-SYNTHETIC")},
        {"radar_id": None},
        {"recording_dates": (date(2020, 1, 1), date(2020, 2, 1))},
        {"recording_dates": None},
        {"limit": 0},
        {"limit": 501},
        {"limit": True},
        {"limit": IntSubclass(2)},
        {"limit": 2.0},
        {"filter": "currentowner"},
        {"filter": StringSubclass("All")},
        {"doc_types": ["GRT"]},
        {"doc_types": ("GRT", "GRT")},
        {"doc_types": ("grt",)},
        {"doc_types": ("GRT,WRT",)},
        {"doc_types": (StringSubclass("GRT"),)},
        {
            "doc_types": tuple(
                f"A{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(51)
            )
        },
        {"doc_groups": ["Deed"]},
        {"doc_groups": ("Deed", "Deed")},
        {"doc_groups": ("Assignment",)},
        {"doc_groups": (StringSubclass("Deed"),)},
    ],
)
def test_query_rejects_unbounded_or_ambiguous_inputs(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        query(**changes)


@pytest.mark.parametrize("purchase", [0, 1, "false", None])
def test_query_requires_explicit_boolean_purchase_mode(purchase: object) -> None:
    with pytest.raises(ValueError, match="exact boolean"):
        query().params(purchase=purchase)  # type: ignore[arg-type]


@pytest.mark.parametrize("limit", [1, 500])
def test_local_limit_boundaries_are_accepted(limit: int) -> None:
    assert query(limit=limit).params(purchase=False)["Limit"] == limit


def test_date_range_representation_does_not_expose_requested_dates() -> None:
    bounded = HistoricalTransactionDateRange(date(2020, 1, 1), date(2020, 12, 31))
    assert repr(bounded) == "HistoricalTransactionDateRange(bounded=True)"
    with pytest.raises(FrozenInstanceError):
        bounded.start = date(2021, 1, 1)  # type: ignore[misc]


def test_parser_query_preflight_happens_before_reading_an_envelope() -> None:
    invalid_query = cast(HistoricalTransactionQuery, None)
    with pytest.raises(ValueError, match="query must be"):
        parse_historical_transaction_quote(
            FailingSnapshotMapping(), query=invalid_query
        )
    with pytest.raises(ValueError, match="query must be"):
        parse_historical_transaction_result(
            FailingSnapshotMapping(), query=invalid_query
        )


def test_scope_fingerprint_binds_each_request_axis_and_retains_exact_order() -> None:
    original = query()
    variants = [
        query(radar_id="P-SYNTHETIC-OTHER"),
        query(
            recording_dates=HistoricalTransactionDateRange(
                date(2020, 1, 2), date(2020, 12, 31)
            )
        ),
        query(
            recording_dates=HistoricalTransactionDateRange(
                date(2020, 1, 1), date(2020, 12, 30)
            )
        ),
        query(limit=3),
        query(filter="CurrentOwner"),
        query(doc_types=("WRT", "GRT")),
        query(doc_groups=("Deed", "Notice")),
        query(doc_types=()),
        query(doc_groups=()),
    ]
    fingerprints = {value.scope_fingerprint for value in [original, *variants]}
    assert len(fingerprints) == 1 + len(variants)
    assert len(original.scope_fingerprint) == 64
    assert original.scope_fingerprint == query().scope_fingerprint
    assert "P-SYNTHETIC" not in repr(original)
    assert "GRT" not in repr(original)
    detached_params = original.params(purchase=False)
    detached_params["Limit"] = 500
    assert original.limit == 2
    assert original.scope_fingerprint == query().scope_fingerprint
    with pytest.raises(FrozenInstanceError):
        original.limit = 500  # type: ignore[misc]


def test_quote_and_multirow_paid_selection_have_separate_billing_semantics() -> None:
    preview = parsed_quote(quantityFreeRemaining=99)
    paid = parsed_result()
    assert isinstance(preview, HistoricalTransactionQuote)
    assert isinstance(paid, HistoricalTransactionResult)
    assert preview.purchase_requested is False
    assert preview.billing_status == "preview"
    assert preview.quantity_free_remaining == 99
    assert paid.purchase_requested is True
    assert paid.billing_status == "charged"
    assert preview.result_count == paid.result_count == len(paid.records) == 2
    assert preview.total_result_count == paid.total_result_count == 5
    assert preview.total_cost == paid.total_cost == Decimal("0.0000001")
    assert (
        preview.scope_fingerprint == paid.scope_fingerprint == query().scope_fingerprint
    )
    assert preview.truncated is paid.truncated is True
    assert preview.currency is paid.currency is None
    assert not hasattr(preview, "records")
    assert not hasattr(paid, "quantity_free_remaining")
    assert [record.document_id for record in paid.records] == [
        "D-SYNTHETIC-1",
        "D-SYNTHETIC-2",
    ]


@pytest.mark.parametrize("remaining", [None, 0, 100])
def test_quotes_accept_absent_or_valid_optional_credit_count(
    remaining: int | None,
) -> None:
    payload = quote_payload(results=[])
    if remaining is not None:
        payload["quantityFreeRemaining"] = remaining
    assert (
        parse_historical_transaction_quote(
            payload, query=query()
        ).quantity_free_remaining
        == remaining
    )


def test_zero_results_are_success_only_with_explicit_zero_counts_and_cost() -> None:
    preview = parsed_quote(resultCount=0, totalResultCount=0, totalCost="0.00")
    paid = parsed_result(results=[], resultCount=0, totalResultCount=0, totalCost="0")
    assert preview.total_cost == paid.total_cost == 0
    assert paid.records == ()
    assert preview.truncated is paid.truncated is False
    assert parsed_quote(resultCount=2, totalResultCount=2).truncated is False
    assert parsed_result(resultCount=2, totalResultCount=2).truncated is False


@pytest.mark.parametrize(
    "cost", ["0", "0.00", "000.0100", "0.0000001", "9" * 64, "0." + "0" * 61 + "1"]
)
def test_decimal_costs_preserve_fine_scale_without_rounding(cost: str) -> None:
    preview = parsed_quote(totalCost=cost)
    paid = parsed_result(totalCost=cost)
    assert preview.total_cost.as_tuple() == Decimal(cost).as_tuple()
    assert paid.total_cost.as_tuple() == Decimal(cost).as_tuple()


@pytest.mark.parametrize(
    "cost",
    [
        None,
        True,
        1,
        1.25,
        Decimal("1.25"),
        "",
        "-1",
        "-0",
        "+1",
        "1e-7",
        "NaN",
        "Infinity",
        ".5",
        "1.",
        " 1.00",
        "1.00 ",
        "1,000",
        "$1.00",
        "\u0661.\u0660",
        "1" * 65,
        "0." + "0" * 62 + "1",
        StringSubclass("0.50"),
    ],
)
def test_both_parsers_reject_invalid_cost_without_coercion(cost: object) -> None:
    with pytest.raises(InvalidResponseError, match="total_cost"):
        parsed_quote(totalCost=cost)
    with pytest.raises(InvalidResponseError, match="total_cost"):
        parsed_result(totalCost=cost)


@pytest.mark.parametrize("field", ["resultCount", "totalResultCount"])
@pytest.mark.parametrize("count", [None, True, -1, 2.0, "2", IntSubclass(2)])
def test_both_parsers_require_exact_nonnegative_counts(
    field: str, count: object
) -> None:
    with pytest.raises(InvalidResponseError, match="count_type"):
        parsed_quote(**{field: count})
    with pytest.raises(InvalidResponseError, match="count_type"):
        parsed_result(**{field: count})


@pytest.mark.parametrize("remaining", [True, -1, "3", 3.0, IntSubclass(3)])
def test_quote_rejects_invalid_credit_counts(remaining: object) -> None:
    with pytest.raises(InvalidResponseError, match="count_type"):
        parsed_quote(quantityFreeRemaining=remaining)


@pytest.mark.parametrize(
    "changes",
    [
        {"resultCount": 1, "totalResultCount": 5},
        {"resultCount": 3, "totalResultCount": 5},
        {"resultCount": 2, "totalResultCount": 1},
        {"resultCount": 0, "totalResultCount": 0, "totalCost": "0.01"},
    ],
)
def test_both_parsers_reject_incomplete_or_contradictory_count_evidence(
    changes: dict[str, object],
) -> None:
    with pytest.raises(InvalidResponseError, match="quote_selection"):
        parsed_quote(**changes)
    with pytest.raises(InvalidResponseError, match="paid_selection"):
        parsed_result(**changes)


@pytest.mark.parametrize("records", [[row()], None, (), "omitted", HostileList()])
def test_quotes_never_accept_returned_rows_or_unknown_container_shapes(
    records: object,
) -> None:
    with pytest.raises(InvalidResponseError, match="quote_results_not_omitted"):
        parsed_quote(results=records)


@pytest.mark.parametrize(
    "records", [None, (), "rows", {}, HostileList(), [row()], [row(), row(), row()]]
)
def test_paid_results_require_every_selected_row_in_an_exact_array(
    records: object,
) -> None:
    with pytest.raises(InvalidResponseError):
        parsed_result(results=records)


def test_paid_results_cannot_be_missing_or_contain_preview_metadata() -> None:
    with pytest.raises(InvalidResponseError, match="paid_results_missing"):
        parse_historical_transaction_result(quote_payload(), query=query())
    with pytest.raises(InvalidResponseError, match="paid_preview_metadata"):
        parsed_result(quantityFreeRemaining=0)


@pytest.mark.parametrize("field", ["totalCost", "resultCount", "totalResultCount"])
def test_required_envelope_evidence_cannot_be_assumed(field: str) -> None:
    preview = quote_payload()
    paid = paid_payload()
    del preview[field]
    del paid[field]
    with pytest.raises(InvalidResponseError, match="missing_envelope_fields"):
        parse_historical_transaction_quote(preview, query=query())
    with pytest.raises(InvalidResponseError, match="missing_envelope_fields"):
        parse_historical_transaction_result(paid, query=query())


@pytest.mark.parametrize(
    "extra", [{"unknown": "private"}, {"currency": "USD"}, {"Purchase": 0}]
)
def test_unknown_envelope_fields_cannot_change_request_or_billing_semantics(
    extra: dict[str, object],
) -> None:
    with pytest.raises(InvalidResponseError, match="undocumented_envelope_fields"):
        parsed_quote(**extra)
    with pytest.raises(InvalidResponseError, match="undocumented_envelope_fields"):
        parsed_result(**extra)


@pytest.mark.parametrize("payload", [None, [], "unknown", 0])
def test_nonmapping_envelopes_remain_invalid(payload: object) -> None:
    with pytest.raises(InvalidResponseError, match="envelope_type"):
        parse_historical_transaction_quote(payload, query=query())  # type: ignore[arg-type]
    with pytest.raises(InvalidResponseError, match="envelope_type"):
        parse_historical_transaction_result(payload, query=query())  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_key", [1, StringSubclass("totalCost")])
def test_envelopes_reject_nonexact_string_keys(bad_key: object) -> None:
    payload = cast(dict[object, object], quote_payload())
    payload.pop("totalCost")
    payload[bad_key] = "0.50"
    with pytest.raises(InvalidResponseError, match="envelope_key_type"):
        parse_historical_transaction_quote(
            cast(Mapping[str, object], payload), query=query()
        )


def test_records_preserve_opaque_values_and_report_missing_fields() -> None:
    result = parsed_result()
    record = result.records[0]
    assert record.document_id == "D-SYNTHETIC-1"
    assert record.radar_id == "P-SYNTHETIC"
    assert record.document_type == "GRT"
    assert record.document_type_ui == "Synthetic Deed"
    assert record.doc_group == "Deed"
    assert record.status == "original"
    assert record.grantor_display == "SYNTHETIC_PRIVATE_GRANTOR"
    assert record.grantee_display == "SYNTHETIC_PRIVATE_GRANTEE"
    assert record.amount == "$123,456"
    assert record.recording_date == "2020-06-12"
    assert record.recording_date_status == "scalar_unverified"
    assert record.unverified_recording_dates is None
    assert "Purpose" in record.missing_fields
    assert "DocumentID" not in record.missing_fields
    assert not hasattr(record, "buyer")
    assert not hasattr(record, "parties")
    empty = typed_row({})
    assert empty.missing_fields == HISTORICAL_TRANSACTION_FIELDS
    assert empty.document_id is empty.radar_id is empty.recording_date is None
    assert empty.document_type is empty.document_type_ui is empty.doc_group is None
    assert (
        empty.status
        is empty.grantor_display
        is empty.grantee_display
        is empty.amount
        is None
    )
    assert empty.recording_date_status == "missing"
    assert empty.unverified_recording_dates is None
    assert typed_row({"Grantor": "  ", "Amount": ""}).grantor_display == "  "


@pytest.mark.parametrize(
    "dates",
    [[], ["2020-06-12"], ["Today", "from: 01/01/2020 to: 12/31/2020"], ("Yesterday",)],
)
def test_recording_date_arrays_are_preserved_as_ambiguous_not_parsed(
    dates: list[str] | tuple[str, ...],
) -> None:
    record = typed_row({"RecDate": dates})
    assert record.recording_date_status == "ambiguous_array"
    assert record.recording_date is None
    assert record.unverified_recording_dates == tuple(dates)
    assert record.fields["RecDate"] == tuple(dates)


@pytest.mark.parametrize(
    "scalar", ["", "not-a-date", "2020-06-12", "2020-06-12/2020-06-14"]
)
def test_scalar_recording_dates_remain_unverified_even_when_they_look_parseable(
    scalar: str,
) -> None:
    record = typed_row({"RecDate": scalar})
    assert record.recording_date == scalar
    assert record.recording_date_status == "scalar_unverified"
    assert record.unverified_recording_dates is None


def test_wire_recording_dates_require_json_arrays_but_model_accepts_frozen_tuples() -> (
    None
):
    dates = ("Today",)
    assert typed_row({"RecDate": dates}).unverified_recording_dates == dates
    with pytest.raises(InvalidResponseError, match="recording_date_array"):
        parsed_result(results=[row(RecDate=dates), row(DocumentID="D-SYNTHETIC-2")])


@pytest.mark.parametrize(
    "changes",
    [
        {"unknown": "SYNTHETIC_PRIVATE_VALUE"},
        {"Status": "unknown"},
        {"DocGroup": "Assignment"},
        {"RecDate": None},
        {"RecDate": [None]},
        {"RecDate": [["2020-06-12"]]},
        {"RecDate": [StringSubclass("2020-06-12")]},
        {"RecDate": HostileList(["Today"])},
        {"Amount": 123456},
        {"Grantor": ["Synthetic", "Party"]},
        {"DocumentID": StringSubclass("D-SYNTHETIC")},
    ],
)
def test_records_reject_unknown_or_incompatible_shapes(
    changes: dict[str, object],
) -> None:
    with pytest.raises(InvalidResponseError):
        parsed_result(results=[row(**changes), row(DocumentID="D-SYNTHETIC-2")])


@pytest.mark.parametrize(
    "record", [None, [], "row", {1: "value"}, FailingSnapshotMapping()]
)
def test_invalid_record_containers_do_not_become_missing_records(
    record: object,
) -> None:
    with pytest.raises(InvalidResponseError):
        parsed_result(results=[record, row(DocumentID="D-SYNTHETIC-2")])


def test_paid_result_rejects_mismatched_property_and_duplicate_document_evidence() -> (
    None
):
    with pytest.raises(InvalidResponseError, match="paid_selection"):
        parsed_result(
            results=[row(RadarID="P-SYNTHETIC-OTHER"), row(DocumentID="D-SYNTHETIC-2")]
        )
    with pytest.raises(InvalidResponseError, match="paid_selection"):
        parsed_result(results=[row(), row()])
    # Missing identifiers are unavailable evidence, not fabricated duplicates.
    assert len(parsed_result(results=[{}, {}]).records) == 2
    assert (
        len(parsed_result(results=[{"DocumentID": ""}, {"DocumentID": ""}]).records)
        == 2
    )


def test_parsed_values_are_detached_deeply_immutable_and_redacted() -> None:
    dates = ["Today", "Yesterday"]
    first = row(RecDate=dates)
    rows: list[object] = [first, row(DocumentID="D-SYNTHETIC-2")]
    source = paid_payload(results=rows)
    result = parse_historical_transaction_result(source, query=query())
    dates.append("Tomorrow")
    first["Grantor"] = "SYNTHETIC_CHANGED"
    rows.clear()
    source["totalCost"] = "99"
    assert len(result.records) == 2
    assert result.total_cost == Decimal("0.0000001")
    assert result.records[0].unverified_recording_dates == ("Today", "Yesterday")
    assert result.records[0].grantor_display == "SYNTHETIC_PRIVATE_GRANTOR"
    assert isinstance(result.records[0].fields, MappingProxyType)
    for value in (result, parsed_quote(), result.records[0]):
        display = repr(value)
        assert "P-SYNTHETIC" not in display
        assert "D-SYNTHETIC" not in display
        assert "SYNTHETIC_PRIVATE" not in display
    with pytest.raises(FrozenInstanceError):
        result.total_cost = Decimal("99")  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.records[0].fields = {}  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.records[0].fields["Grantor"] = "changed"  # type: ignore[index]


def test_each_record_snapshot_detaches_date_arrays_before_later_mapping_callbacks() -> (
    None
):
    dates = ["Today"]
    result = parsed_result(results=[row(RecDate=dates), MutatingRecord(dates)])
    assert dates == ["Today", "SYNTHETIC_LATER_MUTATION"]
    assert result.records[0].unverified_recording_dates == ("Today",)


def test_hostile_dict_snapshot_errors_are_sanitized() -> None:
    with pytest.raises(InvalidResponseError, match="envelope_snapshot") as caught:
        parse_historical_transaction_quote(HostileDict(quote_payload()), query=query())
    assert "SYNTHETIC_PRIVATE" not in "".join(traceback.format_exception(caught.value))
    with pytest.raises(InvalidResponseError, match="record_snapshot") as caught:
        parsed_result(results=[HostileDict(row()), row(DocumentID="D-SYNTHETIC-2")])
    assert "SYNTHETIC_PRIVATE" not in "".join(traceback.format_exception(caught.value))


def test_snapshot_failures_and_selection_errors_are_sanitized() -> None:
    for source in (
        FailingSnapshotMapping(),
        paid_payload(results=[FailingSnapshotMapping(), {}]),
    ):
        with pytest.raises(InvalidResponseError) as caught:
            parse_historical_transaction_result(source, query=query())
        assert "SYNTHETIC_PRIVATE" not in str(caught.value)
        assert "SYNTHETIC_PRIVATE" not in "".join(
            traceback.format_exception(caught.value)
        )
        assert caught.value.__cause__ is None
    with pytest.raises(InvalidResponseError) as caught:
        parsed_result(results=[row(), row(RadarID="P-SYNTHETIC-OTHER")])
    assert "P-SYNTHETIC" not in str(caught.value)
    assert "SYNTHETIC_PRIVATE" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize(
    "changes",
    [
        {"query": None},
        {"result_count": True},
        {"total_result_count": -1},
        {"result_count": 1},
        {"total_cost": 1.0},
        {"total_cost": Decimal("NaN")},
        {"total_cost": Decimal("Infinity")},
        {"total_cost": Decimal("-1")},
        {"total_cost": Decimal("1e1000000")},
        {"total_cost": Decimal("1e-1000000")},
        {"total_cost": Decimal("9" * 65)},
        {"quantity_free_remaining": True},
        {"quantity_free_remaining": -1},
    ],
)
def test_direct_quote_construction_cannot_bypass_safety_invariants(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        replace(parsed_quote(), **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize("records", [[], ({},), (typed_row({}),)])
def test_direct_paid_construction_requires_immutable_complete_typed_records(
    records: object,
) -> None:
    with pytest.raises(ValueError):
        replace(parsed_result(), records=records)  # type: ignore[arg-type]


def test_legacy_transaction_and_buyer_contracts_are_unchanged() -> None:
    assert TRANSACTION_HISTORY_CONTRACT["api_version"] == "5.2.0.0"
    assert TRANSACTION_HISTORY_CONTRACT["contract_fingerprint"] == (
        # pragma: allowlist nextline secret
        "d750039019a93bbfc0449b6eecdb47ea8f064e18a7dcfcbd01c3ec30c4e057a8"
    )
    assert BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"] == (
        # pragma: allowlist nextline secret
        "299cfaba5ddfc8337a290352433969f1f1363fa1a545080773761c2c99d2c8be"
    )
    legacy = parse_transaction_history(
        {"results": [{"RecDate": "2020-06-12"}], "resultCount": 1, "totalCost": "0.25"},
        purchase_requested=True,
    )
    assert legacy.records[0].recording_date == "2020-06-12"
    assert legacy.billing.status == "charged"
    with pytest.raises(InvalidResponseError):
        parse_transaction_history(quote_payload(), purchase_requested=False)
