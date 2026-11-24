from __future__ import annotations

import hashlib
import json
import re
import socket
import traceback
from collections.abc import Callable, Iterator, Mapping
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from types import MappingProxyType
from typing import NoReturn

import httpx
import pytest

from property_radar import (
    BUYER_TRANSFER_MATCH_CONTRACT,
    BUYER_TRANSFER_PROPERTY_FIELDS,
    BuyerTransferBillingEvidence,
    BuyerTransferLinkage,
    BuyerTransferMatchCriteria,
    BuyerTransferMatchResult,
    BuyerTransferProperty,
    ChargeNotAllowedError,
    InvalidResponseError,
    PropertyRadarClient,
    ServerError,
    build_buyer_transfer_match_criteria,
    buyer_transfer_scope_fingerprint,
    parse_buyer_transfer_match,
)
from property_radar.buyer_transfer import (
    BUYER_TRANSFER_PREVIEW_FIELDS,
    BUYER_TRANSFER_RESIDENTIAL_PTYPE_CODES,
    BuyerTransferResponseError,
)
from property_radar.types import Criterion

# The 0.4.1 value that theperrygroup pins until it adopts 0.4.2.
RECENT_CONTRACT_FINGERPRINT_0_4_1 = (
    # pragma: allowlist nextline secret
    "299cfaba5ddfc8337a290352433969f1f1363fa1a545080773761c2c99d2c8be"
)
# The branch value that sent PropertyType on paid requests too (before D4).
RECENT_CONTRACT_FINGERPRINT_PAID_PROPERTY_TYPE = (
    # pragma: allowlist nextline secret
    "0406f8ca5636c36eb834b273a4bc401293d52a91d34854874ad790a6edb12eeb"
)
RECENT_CONTRACT_FINGERPRINT = (
    # pragma: allowlist nextline secret
    "580b955265f3f7928ea1bddba03e7244ceaff8f27fd6844343e05d6ae81bc01c"
)
RECENT_SCOPE_FINGERPRINT = (
    # pragma: allowlist nextline secret
    "c40b4047f89fbaf84b9fe61b294289bcbd29bdc83f7dc08da2eb3459f7149b43"
)
PROPERTY_TYPE_CRITERION: Criterion = {
    "name": "PropertyType",
    "value": [{"name": "PType", "value": ["SFR", "CND", "MFR", "APT", "RES"]}],
}
# The exact 0.4.1 criteria of criteria(): paid requests send this list.
PAID_CRITERIA: tuple[Criterion, ...] = (
    {"name": "State", "value": ["UT"]},
    {"name": "County", "value": [49035]},
    {"name": "Buyer", "value": ["Synthetic Buyer"]},
    {"name": "TransferPublishedDate", "value": ["Last 7 Days"]},
    {"name": "TransferRecDate", "value": ["Last 30 Days"]},
    {"name": "RadarID", "value": ["P-SYNTHETIC"]},
)
# Previews add the residential PropertyType criterion just before RadarID.
PREVIEW_CRITERIA: tuple[Criterion, ...] = (
    *PAID_CRITERIA[:-1],
    PROPERTY_TYPE_CRITERION,
    PAID_CRITERIA[-1],
)
CRITERION_ORDER = (
    "State",
    "County",
    "Buyer",
    "TransferPublishedDate",
    "TransferRecDate",
    "isMostRecentMarketTransfer",
    "RadarID",
)
PREVIEW_CRITERION_ORDER = (*CRITERION_ORDER[:-1], "PropertyType", "RadarID")
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
# Paid and detached parses classify these documented names as not residential.
DOCUMENTED_NON_RESIDENTIAL_PROPERTY_TYPES = tuple(
    name for name in NON_RESIDENTIAL_PROPERTY_TYPES if name != "Unknown"
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
    "Synthetic Buyer",
    "P-SYNTHETIC",
    "P-DIFFERENT",
    "81 Synthetic Way",
    "Example",
    "Synthetic County",
    "SYNTHETIC-81",
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


class FailingSnapshotMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise RuntimeError(f"SYNTHETIC PRIVATE VALUE FOR {key}")

    def __iter__(self) -> Iterator[str]:
        return iter(("results", "totalCost", "resultCount", "totalResultCount"))

    def __len__(self) -> int:
        return 4


class HostileList(list[object]):
    def __iter__(self) -> Iterator[object]:
        raise RuntimeError("SYNTHETIC PRIVATE LIST")

    def __len__(self) -> int:
        raise RuntimeError("SYNTHETIC PRIVATE LENGTH")


class IntegerSubclass(int):
    pass


class StringSubclass(str):
    pass


def criteria(**changes: object) -> BuyerTransferMatchCriteria:
    values: dict[str, object] = {
        "buyer_name": "Synthetic Buyer",
        "radar_id": "P-SYNTHETIC",
        "state_code": "UT",
        "county_fips": "49035",
        "publication_window": "Last 7 Days",
        "recording_window": "Last 30 Days",
        "most_recent_change_of_ownership_only": False,
    }
    values.update(changes)
    return BuyerTransferMatchCriteria(**values)  # type: ignore[arg-type]


def property_record(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "RadarID": "P-SYNTHETIC",
        "PType": "Single Family",
        "Address": "81 Synthetic Way",
        "City": "Example",
        "State": "Utah",
        "ZipFive": 84101,
        "County": "Synthetic County",
        "FIPS": "49035",
        "APN": "SYNTHETIC-81",
        "Latitude": 40.7608,
        "Longitude": -111.891,
    }
    values.update(changes)
    return values


def envelope(
    *,
    records: list[object] | None = None,
    result_count: object | None = None,
    total_result_count: object | None = None,
    purchase: bool = False,
) -> dict[str, object]:
    selected = records if records is not None else [property_record()]
    payload: dict[str, object] = {
        "results": selected,
        "totalCost": "0.50",
        "resultCount": len(selected) if result_count is None else result_count,
        "totalResultCount": (
            len(selected) if total_result_count is None else total_result_count
        ),
    }
    if not purchase:
        payload["quantityFreeRemaining"] = 99
    return payload


def live_bare_zero_hit_preview() -> dict[str, object]:
    # Exact live 0-hit POST /v1/properties?Purchase=0 body: no metadata at all.
    return {"results": []}


def live_one_hit_radar_id_only_preview() -> dict[str, object]:
    # Live 1-hit Fields=RadarID preview shape with a synthetic RadarID.
    # resultCount counts purchased rows (0); totalResultCount counts matches.
    return {
        "results": [{"RadarID": "P-SYNTHETIC"}],
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


def total_result_count_two_preview(*, with_record: bool) -> dict[str, object]:
    return {
        "results": [{"RadarID": "P-SYNTHETIC"}] if with_record else [],
        "totalCost": 0,
        "resultCount": 0,
        "totalResultCount": 2,
    }


def paid_envelope(total_cost: object = 1) -> dict[str, object]:
    return {
        "results": [property_record()],
        "totalCost": total_cost,
        "resultCount": 1,
        "totalResultCount": 1,
    }


def radar_id_only_property(**changes: object) -> BuyerTransferProperty:
    values: dict[str, object] = {
        "returned_fields": ("RadarID",),
        "radar_id": "P-SYNTHETIC",
        "property_type": None,
        "address": None,
        "city": None,
        "state": None,
        "zip_five": None,
        "county": None,
        "fips": None,
        "apn": None,
        "latitude": None,
        "longitude": None,
    }
    values.update(changes)
    return BuyerTransferProperty(**values)  # type: ignore[arg-type]


def record_without_property_type() -> dict[str, object]:
    record = property_record()
    del record["PType"]
    return record


def rejection_envelope(
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


def rejection_evidence(
    purchase_requested: bool | None,
) -> BuyerTransferBillingEvidence:
    # The billing evidence that rejection_envelope() parses to in each mode.
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


def thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: thaw(nested) for key, nested in value.items()}
    if isinstance(value, tuple):
        return tuple(thaw(item) for item in value)
    return value


def assert_deeply_immutable(value: object) -> None:
    if isinstance(value, Mapping):
        assert isinstance(value, MappingProxyType)
        for nested in value.values():
            assert_deeply_immutable(nested)
    elif isinstance(value, tuple):
        for nested in value:
            assert_deeply_immutable(nested)
    else:
        assert not isinstance(value, (list, dict, set))


def test_contract_is_current_deeply_immutable_and_fingerprinted() -> None:
    assert BUYER_TRANSFER_MATCH_CONTRACT["api_version"] == "5.2.0.0"
    assert BUYER_TRANSFER_MATCH_CONTRACT["operation"] == "properties.search"
    assert BUYER_TRANSFER_MATCH_CONTRACT["relationship"] == (
        "provider_buyer_criterion_property_match"
    )
    assert (
        BUYER_TRANSFER_MATCH_CONTRACT["most_recent_change_of_ownership_semantics"]
        == "most_recent_ownership_change_market_or_non_market"
    )
    assert BUYER_TRANSFER_MATCH_CONTRACT["ordered_fields"] == (
        BUYER_TRANSFER_PROPERTY_FIELDS
    )
    limitations = BUYER_TRANSFER_MATCH_CONTRACT["provider_limitations"]
    assert isinstance(limitations, Mapping)
    assert limitations["transaction_party_boundaries"] is None
    assert limitations["scalar_grantor_grantee_parsing"] is False
    assert limitations["matched_transaction_identifier"] is None
    assert limitations["matched_structured_grantees"] is None
    assert_deeply_immutable(BUYER_TRANSFER_MATCH_CONTRACT)

    thawed_contract = thaw(BUYER_TRANSFER_MATCH_CONTRACT)
    assert isinstance(thawed_contract, Mapping)
    source = dict(thawed_contract)
    fingerprint = source.pop("contract_fingerprint")
    encoded = json.dumps(
        source, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    assert fingerprint == hashlib.sha256(encoded).hexdigest()
    assert fingerprint == RECENT_CONTRACT_FINGERPRINT
    assert fingerprint != RECENT_CONTRACT_FINGERPRINT_0_4_1
    assert fingerprint != RECENT_CONTRACT_FINGERPRINT_PAID_PROPERTY_TYPE


def test_recent_contract_keeps_every_value_the_theperrygroup_adapter_checks() -> None:
    contract = BUYER_TRANSFER_MATCH_CONTRACT
    assert type(contract) is MappingProxyType
    assert_deeply_immutable(contract)
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
    with pytest.raises(TypeError):
        contract["operation"] = "changed"  # type: ignore[index]


def test_recent_contract_records_the_preview_fields_and_property_type_criterion() -> (
    None
):
    contract = BUYER_TRANSFER_MATCH_CONTRACT
    # Paid requests keep the 0.4.1 order; only previews add PropertyType.
    assert contract["criterion_order"] == CRITERION_ORDER
    assert "PropertyType" not in CRITERION_ORDER
    assert contract["preview_criterion_order"] == PREVIEW_CRITERION_ORDER
    assert contract["preview_criterion_order"] == (
        "State",
        "County",
        "Buyer",
        "TransferPublishedDate",
        "TransferRecDate",
        "isMostRecentMarketTransfer",
        "PropertyType",
        "RadarID",
    )
    assert contract["preview_fields"] == ("RadarID",)
    assert contract["ordered_fields"] == BUYER_TRANSFER_PROPERTY_FIELDS
    criterion = contract["property_type_criterion"]
    assert type(criterion) is MappingProxyType
    assert criterion["requests"] == ("preview",)
    assert criterion["position"] == "immediately_before_radar_id"
    assert json.loads(json.dumps(thaw(criterion["shape"]))) == PROPERTY_TYPE_CRITERION
    assert criterion["purchase_0_live_probed"] is False
    assert criterion["codes"] == BUYER_TRANSFER_RESIDENTIAL_PTYPE_CODES
    code_property_types = criterion["code_property_types"]
    assert type(code_property_types) is MappingProxyType
    assert tuple(code_property_types) == BUYER_TRANSFER_RESIDENTIAL_PTYPE_CODES
    assert tuple(code_property_types.values()) == RESIDENTIAL_PROPERTY_TYPES
    rendered = json.dumps(thaw(criterion), sort_keys=True)
    for code in ("SFR", "CND", "MFR", "APT", "RES"):
        assert code in rendered
    for name in RESIDENTIAL_PROPERTY_TYPES:
        assert name in rendered
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
    assert len(set(RECORD_REJECTION_REASONS)) == len(RECORD_REJECTION_REASONS) == 18


def test_new_public_constants_pin_the_preview_fields_and_residential_codes() -> None:
    assert BUYER_TRANSFER_PREVIEW_FIELDS == ("RadarID",)
    assert type(BUYER_TRANSFER_PREVIEW_FIELDS) is tuple
    assert BUYER_TRANSFER_RESIDENTIAL_PTYPE_CODES == ("SFR", "CND", "MFR", "APT", "RES")
    assert type(BUYER_TRANSFER_RESIDENTIAL_PTYPE_CODES) is tuple
    assert set(BUYER_TRANSFER_PREVIEW_FIELDS) < set(BUYER_TRANSFER_PROPERTY_FIELDS)


def test_criteria_build_exact_provider_query_and_redact_identity() -> None:
    value = criteria(
        most_recent_change_of_ownership_only=True,
    )

    assert value.buyer_name == "Synthetic Buyer"
    assert "Synthetic Buyer" not in repr(value)
    assert "P-SYNTHETIC" not in repr(value)
    # The default (paid) list is exactly the 0.4.1 list: no PropertyType item.
    assert build_buyer_transfer_match_criteria(value) == (
        {"name": "State", "value": ["UT"]},
        {"name": "County", "value": [49035]},
        {"name": "Buyer", "value": ["Synthetic Buyer"]},
        {"name": "TransferPublishedDate", "value": ["Last 7 Days"]},
        {"name": "TransferRecDate", "value": ["Last 30 Days"]},
        {"name": "isMostRecentMarketTransfer", "value": [1]},
        {"name": "RadarID", "value": ["P-SYNTHETIC"]},
    )
    assert build_buyer_transfer_match_criteria(value, preview=False) == (
        build_buyer_transfer_match_criteria(value)
    )
    assert build_buyer_transfer_match_criteria(value, preview=True) == (
        {"name": "State", "value": ["UT"]},
        {"name": "County", "value": [49035]},
        {"name": "Buyer", "value": ["Synthetic Buyer"]},
        {"name": "TransferPublishedDate", "value": ["Last 7 Days"]},
        {"name": "TransferRecDate", "value": ["Last 30 Days"]},
        {"name": "isMostRecentMarketTransfer", "value": [1]},
        {
            "name": "PropertyType",
            "value": [{"name": "PType", "value": ["SFR", "CND", "MFR", "APT", "RES"]}],
        },
        {"name": "RadarID", "value": ["P-SYNTHETIC"]},
    )
    assert len(buyer_transfer_scope_fingerprint(value)) == 64


@pytest.mark.parametrize(
    ("request_criteria", "paid_names"),
    [
        (
            criteria(),
            (
                "State",
                "County",
                "Buyer",
                "TransferPublishedDate",
                "TransferRecDate",
                "RadarID",
            ),
        ),
        (
            criteria(recording_window=None),
            ("State", "County", "Buyer", "TransferPublishedDate", "RadarID"),
        ),
        (criteria(most_recent_change_of_ownership_only=True), CRITERION_ORDER),
    ],
)
def test_preview_property_type_criterion_sits_just_before_the_last_radar_id(
    request_criteria: BuyerTransferMatchCriteria, paid_names: tuple[str, ...]
) -> None:
    paid = build_buyer_transfer_match_criteria(request_criteria)
    preview = build_buyer_transfer_match_criteria(request_criteria, preview=True)

    assert tuple(item["name"] for item in paid) == paid_names
    assert "PropertyType" not in [item["name"] for item in paid]
    assert preview[-1] == {"name": "RadarID", "value": ["P-SYNTHETIC"]}
    assert preview[-2] == PROPERTY_TYPE_CRITERION
    assert [item["name"] for item in preview].count("PropertyType") == 1
    assert preview == (*paid[:-1], PROPERTY_TYPE_CRITERION, paid[-1])


@pytest.mark.parametrize("preview", [1, 0, None, "x", "true", 1.0])
def test_builder_preview_flag_must_be_an_exact_boolean(preview: object) -> None:
    with pytest.raises(TypeError, match=r"^preview must be a boolean$"):
        build_buyer_transfer_match_criteria(
            criteria(),
            preview=preview,  # type: ignore[arg-type]
        )


def test_builder_checks_criteria_first_and_takes_preview_by_keyword_only() -> None:
    with pytest.raises(
        TypeError, match=r"^criteria must be BuyerTransferMatchCriteria$"
    ):
        build_buyer_transfer_match_criteria(
            object(),  # type: ignore[arg-type]
            preview=1,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError):
        build_buyer_transfer_match_criteria(criteria(), True)  # type: ignore[call-arg]


def test_builder_inserts_a_fresh_property_type_item_on_each_preview_call() -> None:
    first = build_buyer_transfer_match_criteria(criteria(), preview=True)
    item = first[-2]
    values = item["value"]
    assert isinstance(values, list)
    subcriterion = values[0]
    assert isinstance(subcriterion, dict)
    codes = subcriterion["value"]
    assert isinstance(codes, list)
    codes.append("COM")
    subcriterion["name"] = "Changed"
    values.append({"name": "PType", "value": ["IND"]})
    item["name"] = "Changed"

    second = build_buyer_transfer_match_criteria(criteria(), preview=True)
    assert second == PREVIEW_CRITERIA
    assert second[-2] is not first[-2]
    assert build_buyer_transfer_match_criteria(criteria()) == PAID_CRITERIA
    shape = BUYER_TRANSFER_MATCH_CONTRACT["property_type_criterion"]
    assert type(shape) is MappingProxyType
    assert json.loads(json.dumps(thaw(shape["shape"]))) == PROPERTY_TYPE_CRITERION
    assert buyer_transfer_scope_fingerprint(criteria()) == RECENT_SCOPE_FINGERPRINT


def test_scope_fingerprint_changes_with_each_configurable_criterion() -> None:
    base = criteria()
    variants = (
        criteria(buyer_name="Different Synthetic Buyer"),
        criteria(radar_id="P-DIFFERENT"),
        criteria(state_code="CO", county_fips="08031"),
        criteria(county_fips="49049"),
        criteria(recording_window=None),
        criteria(most_recent_change_of_ownership_only=True),
    )

    fingerprints = {
        buyer_transfer_scope_fingerprint(request_criteria)
        for request_criteria in (base, *variants)
    }
    assert len(fingerprints) == 1 + len(variants)


def test_recent_scope_fingerprint_hashes_both_criteria_lists_and_field_sets() -> None:
    # One scope value covers the paid 0.4.1 criteria and the preview's extra
    # PropertyType item, so a preview and a paid parse share the fingerprint.
    expected_payload = {
        "operation": "properties.search",
        "criteria": [
            {"name": "State", "value": ["UT"]},
            {"name": "County", "value": [49035]},
            {"name": "Buyer", "value": ["Synthetic Buyer"]},
            {"name": "TransferPublishedDate", "value": ["Last 7 Days"]},
            {"name": "TransferRecDate", "value": ["Last 30 Days"]},
            {"name": "RadarID", "value": ["P-SYNTHETIC"]},
        ],
        "preview_property_type_criterion": PROPERTY_TYPE_CRITERION,
        "fields": list(BUYER_TRANSFER_PROPERTY_FIELDS),
        "preview_fields": ["RadarID"],
        "limit": 1,
        "start": 0,
    }
    encoded = json.dumps(
        expected_payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")

    assert buyer_transfer_scope_fingerprint(criteria()) == (
        hashlib.sha256(encoded).hexdigest()
    )
    assert buyer_transfer_scope_fingerprint(criteria()) == RECENT_SCOPE_FINGERPRINT


def test_live_preview_and_paid_parses_bind_the_same_scope_fingerprint() -> None:
    request_criteria = criteria()
    expected = buyer_transfer_scope_fingerprint(request_criteria)
    preview = parse_buyer_transfer_match(
        live_one_hit_radar_id_only_preview(),
        criteria=request_criteria,
        purchase_requested=False,
    )
    paid = parse_buyer_transfer_match(
        paid_envelope(), criteria=request_criteria, purchase_requested=True
    )
    bare = parse_buyer_transfer_match(
        live_bare_zero_hit_preview(),
        criteria=request_criteria,
        purchase_requested=False,
    )

    for result in (preview, paid):
        assert result.scope_fingerprint == expected
        assert result.linkage is not None
        assert result.linkage.scope_fingerprint == expected
    assert bare.scope_fingerprint == expected
    assert preview.billing.status == "preview"
    assert paid.billing.status == "charged"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"buyer_name": ""}, "buyer_name"),
        ({"buyer_name": None}, "buyer_name"),
        ({"buyer_name": "Synthetic\nBuyer"}, "buyer_name"),
        ({"buyer_name": "  Synthetic Buyer  "}, "buyer_name"),
        ({"radar_id": ""}, "radar_id"),
        ({"state_code": "Ut"}, "state_code"),
        ({"county_fips": "49A35"}, "county_fips"),
        ({"publication_window": "Last 30 Days"}, "publication_window"),
        ({"recording_window": "Last 7 Days"}, "recording_window"),
        ({"most_recent_change_of_ownership_only": 1}, "most_recent"),
    ],
)
def test_criteria_reject_invalid_inputs(
    change: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        criteria(**change)


def test_criteria_does_not_invent_an_undocumented_buyer_name_limit() -> None:
    buyer_name = "X" * 161
    request_criteria = criteria(buyer_name=buyer_name)

    assert build_buyer_transfer_match_criteria(request_criteria)[2] == {
        "name": "Buyer",
        "value": [buyer_name],
    }


def test_parse_match_returns_typed_location_and_billing() -> None:
    request_criteria = criteria()
    result = parse_buyer_transfer_match(
        envelope(), criteria=request_criteria, purchase_requested=False
    )

    assert result.matched is True
    assert result.linkage is not None
    assert result.linkage.relationship == "provider_buyer_criterion_property_match"
    assert result.linkage.scope_fingerprint == (
        buyer_transfer_scope_fingerprint(request_criteria)
    )
    assert result.linkage.property.radar_id == "P-SYNTHETIC"
    assert result.linkage.property.address == "81 Synthetic Way"
    assert result.linkage.property.property_type == "Single Family"
    assert result.linkage.property.is_residential is True
    assert result.linkage.property.residential_basis == "property_type"
    assert result.linkage.property.zip_five == 84101
    assert result.linkage.property.latitude == Decimal("40.7608")
    assert result.linkage.property.longitude == Decimal("-111.891")
    assert result.billing.status == "preview"
    assert result.billing.total_cost == Decimal("0.50")
    assert result.billing.quantity_free_remaining == 99
    assert result.billing.provider_metadata_omitted is False
    assert (
        result.contract_fingerprint
        == (BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"])
    )


def test_parse_no_match_and_charged_match_are_distinct() -> None:
    no_match = parse_buyer_transfer_match(
        envelope(records=[]), criteria=criteria(), purchase_requested=False
    )
    charged = parse_buyer_transfer_match(
        envelope(purchase=True), criteria=criteria(), purchase_requested=True
    )

    assert no_match.matched is False
    assert no_match.linkage is None
    assert no_match.billing.result_count == 0
    assert no_match.billing.provider_metadata_omitted is False
    assert charged.matched is True
    assert charged.billing.status == "charged"
    assert charged.billing.quantity_free_remaining is None
    assert charged.billing.provider_metadata_omitted is False


def test_live_bare_zero_hit_preview_is_a_no_match_with_omitted_metadata() -> None:
    request_criteria = criteria()
    result = parse_buyer_transfer_match(
        live_bare_zero_hit_preview(),
        criteria=request_criteria,
        purchase_requested=False,
    )

    assert type(result) is BuyerTransferMatchResult
    assert result.matched is False
    assert result.linkage is None
    assert (
        result.contract_fingerprint
        == (BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"])
    )
    assert result.scope_fingerprint == buyer_transfer_scope_fingerprint(
        request_criteria
    )
    billing = result.billing
    assert billing.purchase_requested is False
    assert billing.status == "preview"
    assert type(billing.total_cost) is Decimal
    assert billing.total_cost == Decimal("0")
    assert billing.currency is None
    assert billing.quantity_free_remaining is None
    assert billing.result_count == 0
    assert billing.total_result_count == 0
    assert billing.provider_metadata_omitted is True
    assert "provider_metadata_omitted=True" in repr(billing)


@pytest.mark.parametrize("purchase_requested", [True, None])
def test_live_bare_zero_hit_envelope_still_needs_metadata_unless_preview(
    purchase_requested: bool | None,
) -> None:
    with pytest.raises(InvalidResponseError, match=r"\(required_envelope_fields\)"):
        parse_buyer_transfer_match(
            live_bare_zero_hit_preview(),
            criteria=criteria(),
            purchase_requested=purchase_requested,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"results": [{"RadarID": "P-SYNTHETIC"}]},
        {"results": {}},
        {"results": None},
        {"results": [], "totalCost": 0},
        {"results": [], "quantityFreeRemaining": 9866},
        {"results": [], "resultCount": 0, "totalResultCount": 0},
        {"results": [], "totalCost": 0, "resultCount": 0},
        {"totalCost": 0, "resultCount": 0, "totalResultCount": 0},
    ],
)
def test_other_partial_preview_envelopes_still_fail_closed(
    payload: dict[str, object],
) -> None:
    with pytest.raises(InvalidResponseError, match=r"\(required_envelope_fields\)"):
        parse_buyer_transfer_match(
            payload, criteria=criteria(), purchase_requested=False
        )


def test_live_one_hit_radar_id_only_preview_counts_zero_purchased_rows() -> None:
    request_criteria = criteria()
    result = parse_buyer_transfer_match(
        live_one_hit_radar_id_only_preview(),
        criteria=request_criteria,
        purchase_requested=False,
    )

    assert type(result) is BuyerTransferMatchResult
    assert result.matched is True
    assert result.linkage is not None
    property_value = result.linkage.property
    assert type(property_value) is BuyerTransferProperty
    assert property_value.radar_id == "P-SYNTHETIC"
    assert property_value.returned_fields == ("RadarID",)
    assert property_value.fips is None
    assert property_value.property_type is None
    assert property_value.is_residential is True
    assert property_value.residential_basis == "property_type_criterion"
    assert result.scope_fingerprint == buyer_transfer_scope_fingerprint(
        request_criteria
    )
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
    assert "P-SYNTHETIC" not in rendered
    assert "Synthetic Buyer" not in rendered


def test_preview_result_count_may_also_equal_the_returned_record() -> None:
    result = parse_buyer_transfer_match(
        {**live_one_hit_radar_id_only_preview(), "resultCount": 1},
        criteria=criteria(),
        purchase_requested=False,
    )

    assert result.matched is True
    assert result.billing.result_count == 1
    assert result.billing.total_result_count == 1


def test_preview_with_result_count_zero_and_a_full_record_is_matched() -> None:
    result = parse_buyer_transfer_match(
        envelope(result_count=0), criteria=criteria(), purchase_requested=False
    )

    assert result.matched is True
    assert result.billing.result_count == 0
    assert result.billing.total_result_count == 1
    assert result.linkage is not None
    assert result.linkage.property.residential_basis == "property_type"


@pytest.mark.parametrize("purchase_requested", [True, None])
def test_live_one_hit_preview_counts_still_fail_paid_and_unknown_parses(
    purchase_requested: bool | None,
) -> None:
    with pytest.raises(InvalidResponseError, match=r"\(result_count_mismatch\)"):
        parse_buyer_transfer_match(
            live_one_hit_radar_id_only_preview(),
            criteria=criteria(),
            purchase_requested=purchase_requested,
        )
    with pytest.raises(InvalidResponseError, match=r"\(result_count_mismatch\)"):
        parse_buyer_transfer_match(
            envelope(result_count=0, purchase=purchase_requested is True),
            criteria=criteria(),
            purchase_requested=purchase_requested,
        )


def test_live_withheld_record_preview_fails_closed() -> None:
    with pytest.raises(
        InvalidResponseError, match=r"\(preview_record_withheld\)"
    ) as caught:
        parse_buyer_transfer_match(
            live_withheld_record_preview(),
            criteria=criteria(),
            purchase_requested=False,
        )
    assert "9866" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("purchase_requested", [True, None])
def test_live_withheld_record_shape_fails_paid_and_unknown_parses(
    purchase_requested: bool | None,
) -> None:
    payload = live_withheld_record_preview()
    if purchase_requested is True:
        del payload["quantityFreeRemaining"]
    with pytest.raises(InvalidResponseError, match=r"\(ambiguous_total_result_count\)"):
        parse_buyer_transfer_match(
            payload, criteria=criteria(), purchase_requested=purchase_requested
        )


@pytest.mark.parametrize("with_record", [True, False])
@pytest.mark.parametrize("purchase_requested", [False, True, None])
def test_live_total_result_count_two_preview_fails_closed(
    with_record: bool, purchase_requested: bool | None
) -> None:
    with pytest.raises(InvalidResponseError, match=r"\(total_result_count\)"):
        parse_buyer_transfer_match(
            total_result_count_two_preview(with_record=with_record),
            criteria=criteria(),
            purchase_requested=purchase_requested,
        )


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (
            {
                **live_one_hit_radar_id_only_preview(),
                "results": [{"RadarID": "P-SYNTHETIC"}, {"RadarID": "P-SYNTHETIC"}],
            },
            "ambiguous_results",
        ),
        (
            {**live_one_hit_radar_id_only_preview(), "totalResultCount": 0},
            "ambiguous_total_result_count",
        ),
        (
            {**live_bare_zero_hit_preview(), "totalCost": 0, "resultCount": 1}
            | {"totalResultCount": 0},
            "result_count_mismatch",
        ),
        (
            {**live_one_hit_radar_id_only_preview(), "resultCount": 2},
            "result_count",
        ),
        (
            {**live_one_hit_radar_id_only_preview(), "resultCount": -1},
            "result_count",
        ),
        (
            {**live_one_hit_radar_id_only_preview(), "totalResultCount": True},
            "total_result_count",
        ),
    ],
)
def test_preview_count_rules_fail_closed_with_exact_reasons(
    payload: dict[str, object], reason: str
) -> None:
    with pytest.raises(InvalidResponseError, match=rf"\({reason}\)"):
        parse_buyer_transfer_match(
            payload, criteria=criteria(), purchase_requested=False
        )


TOTAL_COST_ACCEPTED: list[tuple[object, Decimal]] = [
    (0, Decimal("0")),
    (7, Decimal("7")),
    (10**64 - 1, Decimal(10**64 - 1)),
    (0.0, Decimal("0.0")),
    (0.1, Decimal("0.1")),
    (0.5, Decimal("0.5")),
    (1.0, Decimal("1.0")),
    (1.5, Decimal("1.5")),
    (0.30000000000000004, Decimal("0.30000000000000004")),
    (12.75, Decimal("12.75")),
    (1e16, Decimal("1E+16")),
    (1e63, Decimal("1E+63")),
    (1e-62, Decimal("1E-62")),
    ("0", Decimal("0")),
    ("0.50", Decimal("0.50")),
    ("1" * 64, Decimal("1" * 64)),
]
TOTAL_COST_REJECTED: list[object] = [
    True,
    False,
    None,
    float("nan"),
    float("inf"),
    float("-inf"),
    -1,
    -0.0,
    -0.5,
    10**64,
    1e64,
    1e-63,
    5e-324,
    "-1.00",
    "1" * 65,
    "",
    " 0",
    "0.",
    ".5",
    "1e3",
    "NaN",
    "Infinity",
    Decimal("0"),
    IntegerSubclass(1),
    StringSubclass("0"),
    [0],
    {"amount": 0},
]


@pytest.mark.parametrize(("total_cost", "expected"), TOTAL_COST_ACCEPTED)
@pytest.mark.parametrize("purchase_requested", [False, True, None])
def test_live_total_cost_json_int_float_and_decimal_string_are_accepted(
    total_cost: object, expected: Decimal, purchase_requested: bool | None
) -> None:
    payload = {
        **envelope(purchase=purchase_requested is True),
        "totalCost": total_cost,
    }
    result = parse_buyer_transfer_match(
        payload, criteria=criteria(), purchase_requested=purchase_requested
    )

    assert type(result.billing.total_cost) is Decimal
    assert result.billing.total_cost == expected
    if type(total_cost) is float:
        assert result.billing.total_cost == Decimal(repr(total_cost))


def test_live_total_cost_float_is_converted_from_its_shortest_repr() -> None:
    result = parse_buyer_transfer_match(
        {**live_one_hit_radar_id_only_preview(), "totalCost": 0.1},
        criteria=criteria(),
        purchase_requested=False,
    )

    assert result.billing.total_cost == Decimal("0.1")
    assert result.billing.total_cost != Decimal.from_float(0.1)


def test_live_total_cost_json_int_zero_on_the_one_hit_preview() -> None:
    payload = live_one_hit_radar_id_only_preview()
    assert type(payload["totalCost"]) is int
    result = parse_buyer_transfer_match(
        payload, criteria=criteria(), purchase_requested=False
    )

    assert result.billing.total_cost == Decimal("0")


# D9 adds no totalCost rejection. The parser sees the JSON number as decoded:
# an integer is always exact, and a number with at most 15 significant digits
# keeps its written value. A longer number with a fraction or an exponent is
# already a rounded float, so its Decimal follows that float.
TOTAL_COST_DECODED_JSON_NUMBERS: list[tuple[str, Decimal]] = [
    ("0.1", Decimal("0.1")),
    ("1.5", Decimal("1.5")),
    ("0.30000000000000004", Decimal("0.30000000000000004")),
    ("123456789012.345", Decimal("123456789012.345")),
    ("12345678901234567890", Decimal("12345678901234567890")),
    ("1.23456789012345678", Decimal("1.2345678901234567")),
    ("1.0000000000000000001", Decimal("1.0")),
    ("2.5e3", Decimal("2500.0")),
]


@pytest.mark.parametrize(("number", "expected"), TOTAL_COST_DECODED_JSON_NUMBERS)
@pytest.mark.parametrize("purchase_requested", [False, True, None])
def test_total_cost_follows_the_json_number_as_decoded(
    number: str, expected: Decimal, purchase_requested: bool | None
) -> None:
    payload = {
        **envelope(purchase=purchase_requested is True),
        "totalCost": json.loads(number),
    }
    result = parse_buyer_transfer_match(
        payload, criteria=criteria(), purchase_requested=purchase_requested
    )

    assert type(result.billing.total_cost) is Decimal
    assert result.billing.total_cost.as_tuple() == expected.as_tuple()


def test_ci_smoke_preview_shapes_keep_their_results() -> None:
    # The exact preview shapes that the CI and release smoke tests parse.
    one_hit = parse_buyer_transfer_match(
        {
            "results": [{"RadarID": "P-SYNTHETIC"}],
            "totalCost": 0,
            "quantityFreeRemaining": 100,
            "resultCount": 0,
            "totalResultCount": 1,
        },
        criteria=criteria(),
        purchase_requested=False,
    )
    bare = parse_buyer_transfer_match(
        {"results": []}, criteria=criteria(), purchase_requested=False
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


@pytest.mark.parametrize("total_cost", TOTAL_COST_REJECTED)
@pytest.mark.parametrize("purchase_requested", [False, True, None])
def test_live_total_cost_rejects_bool_non_finite_negative_and_overlong_values(
    total_cost: object, purchase_requested: bool | None
) -> None:
    payload = {
        **envelope(purchase=purchase_requested is True),
        "totalCost": total_cost,
    }
    with pytest.raises(InvalidResponseError, match=r"\(total_cost\)") as caught:
        parse_buyer_transfer_match(
            payload, criteria=criteria(), purchase_requested=purchase_requested
        )
    assert "81 Synthetic Way" not in str(caught.value)


@pytest.mark.parametrize("property_type", RESIDENTIAL_PROPERTY_TYPES)
@pytest.mark.parametrize("purchase_requested", [False, True, None])
def test_returned_residential_property_type_records_the_property_type_basis(
    property_type: str, purchase_requested: bool | None
) -> None:
    payload = {
        **envelope(purchase=purchase_requested is True),
        "results": [property_record(PType=property_type)],
    }
    result = parse_buyer_transfer_match(
        payload, criteria=criteria(), purchase_requested=purchase_requested
    )

    assert result.linkage is not None
    assert result.linkage.property.property_type == property_type
    assert result.linkage.property.is_residential is True
    assert result.linkage.property.residential_basis == "property_type"


@pytest.mark.parametrize("property_type", NON_RESIDENTIAL_PROPERTY_TYPES)
def test_preview_property_type_outside_the_residential_criterion_fails_closed(
    property_type: str,
) -> None:
    payload = rejection_envelope(property_record(PType=property_type), False)
    with pytest.raises(BuyerTransferResponseError) as caught:
        parse_buyer_transfer_match(
            payload, criteria=criteria(), purchase_requested=False
        )

    assert_record_rejection(
        caught.value, "property_type_outside_criterion", rejection_evidence(False)
    )
    assert property_type not in str(caught.value)


@pytest.mark.parametrize("property_type", ["Commercial", "Unknown"])
def test_live_one_hit_preview_outside_the_criterion_carries_preview_evidence(
    property_type: str,
) -> None:
    payload = {
        **live_one_hit_radar_id_only_preview(),
        "results": [{"RadarID": "P-SYNTHETIC", "PType": property_type}],
    }
    with pytest.raises(BuyerTransferResponseError) as caught:
        parse_buyer_transfer_match(
            payload, criteria=criteria(), purchase_requested=False
        )

    assert_record_rejection(
        caught.value,
        "property_type_outside_criterion",
        BuyerTransferBillingEvidence(
            purchase_requested=False,
            status="preview",
            total_cost=Decimal("0"),
            currency=None,
            quantity_free_remaining=None,
            result_count=0,
            total_result_count=1,
        ),
    )


@pytest.mark.parametrize(
    ("property_type", "residential"),
    [
        *((name, False) for name in DOCUMENTED_NON_RESIDENTIAL_PROPERTY_TYPES),
        ("Unknown", None),
    ],
)
@pytest.mark.parametrize("purchase_requested", [True, None])
def test_paid_and_detached_parses_classify_the_returned_property_type(
    property_type: str, residential: bool | None, purchase_requested: bool | None
) -> None:
    payload = {
        **envelope(purchase=purchase_requested is True),
        "results": [property_record(PType=property_type)],
    }
    result = parse_buyer_transfer_match(
        payload, criteria=criteria(), purchase_requested=purchase_requested
    )

    assert result.matched is True
    assert result.linkage is not None
    property_value = result.linkage.property
    assert property_value.property_type == property_type
    assert property_value.residential_basis == "property_type"
    assert property_value.is_residential is residential
    assert result.scope_fingerprint == buyer_transfer_scope_fingerprint(criteria())


@pytest.mark.parametrize(
    "record",
    [
        pytest.param({"RadarID": "P-SYNTHETIC"}, id="radar_id_only"),
        pytest.param(record_without_property_type(), id="every_field_but_ptype"),
    ],
)
@pytest.mark.parametrize("purchase_requested", [True, None])
def test_paid_and_detached_parses_without_a_ptype_leave_residential_unknown(
    record: dict[str, object], purchase_requested: bool | None
) -> None:
    payload = {**envelope(purchase=purchase_requested is True), "results": [record]}
    result = parse_buyer_transfer_match(
        payload, criteria=criteria(), purchase_requested=purchase_requested
    )

    assert result.linkage is not None
    property_value = result.linkage.property
    assert "PType" not in property_value.returned_fields
    assert property_value.property_type is None
    assert property_value.residential_basis is None
    assert property_value.is_residential is None


@pytest.mark.parametrize("record", [{"RadarID": "P-SYNTHETIC"}, property_record()])
def test_preview_classification_follows_the_residential_criterion(
    record: dict[str, object],
) -> None:
    result = parse_buyer_transfer_match(
        envelope(records=[record]), criteria=criteria(), purchase_requested=False
    )

    assert result.linkage is not None
    property_value = result.linkage.property
    assert property_value.is_residential is True
    if "PType" in record:
        assert property_value.property_type == "Single Family"
        assert property_value.residential_basis == "property_type"
    else:
        assert property_value.property_type is None
        assert property_value.residential_basis == "property_type_criterion"


@pytest.mark.parametrize("property_type", ["Spaceship", "", 1, None, ["SFR"], "SFR"])
@pytest.mark.parametrize("purchase_requested", [False, True, None])
def test_undocumented_returned_property_type_keeps_the_property_type_reason(
    property_type: object, purchase_requested: bool | None
) -> None:
    payload = rejection_envelope(
        property_record(PType=property_type), purchase_requested
    )
    with pytest.raises(BuyerTransferResponseError) as caught:
        parse_buyer_transfer_match(
            payload, criteria=criteria(), purchase_requested=purchase_requested
        )

    assert_record_rejection(
        caught.value, "property_type", rejection_evidence(purchase_requested)
    )


def test_present_provider_text_is_preserved_exactly() -> None:
    result = parse_buyer_transfer_match(
        envelope(
            records=[
                {
                    "RadarID": "P-SYNTHETIC",
                    "PType": "Other Res.",
                    "Address": "",
                    "City": "",
                    "State": "",
                    "County": "",
                    "APN": "",
                }
            ]
        ),
        criteria=criteria(),
    )

    assert result.linkage is not None
    assert result.linkage.property.address == ""
    assert result.linkage.property.city == ""
    assert result.linkage.property.fips is None
    assert result.linkage.property.apn == ""
    assert result.linkage.property.property_type == "Other Res."
    assert result.linkage.property.is_residential is True


def test_returned_unknown_property_type_fails_only_a_preview() -> None:
    payload = envelope(records=[{"RadarID": "P-SYNTHETIC", "PType": "Unknown"}])
    with pytest.raises(
        BuyerTransferResponseError, match=r"\(property_type_outside_criterion\)"
    ):
        parse_buyer_transfer_match(
            payload, criteria=criteria(), purchase_requested=False
        )

    # A detached parse cannot know the request mode, so it classifies the
    # returned PType like a paid parse: Unknown stays unknown.
    detached = parse_buyer_transfer_match(payload, criteria=criteria())
    assert detached.billing.status == "unknown"
    assert detached.linkage is not None
    assert detached.linkage.property.property_type == "Unknown"
    assert detached.linkage.property.residential_basis == "property_type"
    assert detached.linkage.property.is_residential is None


def test_documented_non_residential_property_type_is_not_a_home() -> None:
    payload = envelope(records=[property_record(PType="Commercial")])
    with pytest.raises(
        BuyerTransferResponseError, match=r"\(property_type_outside_criterion\)"
    ):
        parse_buyer_transfer_match(
            payload, criteria=criteria(), purchase_requested=False
        )

    detached = parse_buyer_transfer_match(payload, criteria=criteria())
    assert detached.linkage is not None
    assert detached.linkage.property.property_type == "Commercial"
    assert detached.linkage.property.residential_basis == "property_type"
    assert detached.linkage.property.is_residential is False

    manual = radar_id_only_property(
        returned_fields=("RadarID", "PType"), property_type="Commercial"
    )
    assert manual.residential_basis is None
    assert manual.is_residential is False


@pytest.mark.parametrize(
    ("property_type", "residential"),
    [
        *((name, True) for name in RESIDENTIAL_PROPERTY_TYPES),
        *(
            (name, False)
            for name in NON_RESIDENTIAL_PROPERTY_TYPES
            if name != "Unknown"
        ),
        ("Unknown", None),
    ],
)
def test_direct_construction_without_a_basis_keeps_the_0_4_1_classification(
    property_type: str, residential: bool | None
) -> None:
    value = radar_id_only_property(
        returned_fields=("RadarID", "PType"), property_type=property_type
    )

    assert value.residential_basis is None
    assert value.is_residential is residential
    assert radar_id_only_property().is_residential is None


def test_property_type_criterion_basis_classifies_a_radar_id_only_record() -> None:
    value = radar_id_only_property(residential_basis="property_type_criterion")

    assert value.property_type is None
    assert value.is_residential is True
    rendered = repr(value)
    assert re.search(r"residential_basis='?property_type_criterion'?[,)]", rendered)
    assert "P-SYNTHETIC" not in rendered


@pytest.mark.parametrize(
    ("property_type", "residential"),
    [
        *((name, True) for name in RESIDENTIAL_PROPERTY_TYPES),
        *((name, False) for name in DOCUMENTED_NON_RESIDENTIAL_PROPERTY_TYPES),
        ("Unknown", None),
    ],
)
def test_property_type_basis_accepts_every_documented_property_type(
    property_type: str, residential: bool | None
) -> None:
    # A paid result records basis property_type for any documented PType.
    value = radar_id_only_property(
        returned_fields=("RadarID", "PType"),
        property_type=property_type,
        residential_basis="property_type",
    )

    assert value.residential_basis == "property_type"
    assert value.is_residential is residential


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {
                "returned_fields": ("RadarID", "PType"),
                "property_type": "Single Family",
                "residential_basis": "property_type_criterion",
            },
            "residential_basis property_type_criterion requires no PType",
        ),
        (
            {"residential_basis": "property_type"},
            "residential_basis property_type requires a documented PType",
        ),
        (
            {"residential_basis": "synthetic_guess"},
            "residential_basis is not a documented classification basis",
        ),
        (
            {"residential_basis": True},
            "residential_basis is not a documented classification basis",
        ),
    ],
)
def test_residential_basis_rejects_contradictory_manual_states(
    changes: dict[str, object], message: str
) -> None:
    # Without a basis the same values are a valid 0.4.1 direct construction,
    # so only the residential_basis rule can raise below.
    radar_id_only_property(**{**changes, "residential_basis": None})
    with pytest.raises(ValueError) as caught:
        radar_id_only_property(**changes)
    assert str(caught.value) == message
    assert "P-SYNTHETIC" not in str(caught.value)


def test_missing_optional_property_fields_remain_unavailable() -> None:
    payload = envelope(records=[{"RadarID": "P-SYNTHETIC"}])
    result = parse_buyer_transfer_match(payload, criteria=criteria())
    assert result.linkage is not None
    property_value = result.linkage.property
    assert property_value.returned_fields == ("RadarID",)
    assert property_value.property_type is None
    assert property_value.address is None
    assert property_value.zip_five is None
    assert property_value.latitude is None
    # A detached parse has no criterion to rely on, so the class is unknown.
    assert property_value.residential_basis is None
    assert property_value.is_residential is None

    preview = parse_buyer_transfer_match(
        payload, criteria=criteria(), purchase_requested=False
    )
    assert preview.linkage is not None
    assert preview.linkage.property.residential_basis == "property_type_criterion"
    assert preview.linkage.property.is_residential is True
    assert replace(preview.linkage.property, residential_basis=None) == property_value


@pytest.mark.parametrize(
    "payload",
    [
        {"results": [], "totalCost": "0.00", "resultCount": 0},
        {**envelope(), "unexpected": "value"},
        envelope(records=[property_record(), property_record()]),
        envelope(total_result_count=0),
        envelope(result_count=2, total_result_count=2),
        envelope(records=[{"RadarID": "P-DIFFERENT"}]),
        envelope(records=[{**property_record(), "Owner": "PRIVATE"}]),
        envelope(records=[{"Address": "81 Synthetic Way"}]),
        envelope(records=[property_record(ZipFive=True)]),
        envelope(records=[property_record(FIPS="49A35")]),
        envelope(records=[property_record(FIPS="49049")]),
        envelope(records=[property_record(PType="Spaceship")]),
        envelope(records=[property_record(PType="Commercial")]),
        envelope(records=[property_record(Latitude=91)]),
        envelope(records=[property_record(Longitude=float("nan"))]),
    ],
)
def test_parser_rejects_invalid_or_ambiguous_shapes_without_values(
    payload: dict[str, object],
) -> None:
    with pytest.raises(InvalidResponseError) as caught:
        parse_buyer_transfer_match(
            payload,
            criteria=criteria(),
            purchase_requested=False,
        )
    rendered = str(caught.value)
    assert "Synthetic Buyer" not in rendered
    assert "81 Synthetic Way" not in rendered
    assert "PRIVATE" not in rendered


# Every rejection of the returned record, with the reason it reports. The
# preview-only property_type_outside_criterion has its own tests above.
RECORD_REJECTIONS = [
    pytest.param("P-SYNTHETIC", "property_type", id="non_object_record"),
    pytest.param(FailingSnapshotMapping(), "property_snapshot", id="property_snapshot"),
    pytest.param({1: "P-SYNTHETIC"}, "property_key_type", id="property_key_type"),
    pytest.param(
        {**property_record(), "Owner": "PRIVATE"},
        "undocumented_property_fields",
        id="undocumented_property_fields",
    ),
    pytest.param(
        {"Address": "81 Synthetic Way"}, "missing_radar_id", id="missing_radar_id"
    ),
    pytest.param(property_record(RadarID=""), "radar_id", id="radar_id"),
    pytest.param(
        property_record(RadarID="P-DIFFERENT"),
        "radar_id_mismatch",
        id="radar_id_mismatch",
    ),
    pytest.param(property_record(FIPS="49A35"), "fips", id="fips"),
    pytest.param(property_record(FIPS="49049"), "fips_mismatch", id="fips_mismatch"),
    pytest.param(
        property_record(PType="Spaceship"),
        "property_type",
        id="undocumented_property_type",
    ),
    pytest.param(property_record(Address=81), "address", id="address"),
    pytest.param(property_record(City=81), "city", id="city"),
    pytest.param(property_record(State=81), "state", id="state"),
    pytest.param(property_record(ZipFive=True), "zip_five", id="zip_five"),
    pytest.param(property_record(County=81), "county", id="county"),
    pytest.param(property_record(APN=81), "apn", id="apn"),
    pytest.param(property_record(Latitude=91), "latitude", id="latitude"),
    pytest.param(property_record(Longitude=float("nan")), "longitude", id="longitude"),
]


@pytest.mark.parametrize(("record", "reason"), RECORD_REJECTIONS)
@pytest.mark.parametrize("purchase_requested", [True, False, None])
def test_every_record_rejection_raises_buyer_transfer_response_error_with_evidence(
    record: object, reason: str, purchase_requested: bool | None
) -> None:
    payload = rejection_envelope(record, purchase_requested)
    with pytest.raises(BuyerTransferResponseError) as caught:
        parse_buyer_transfer_match(
            payload, criteria=criteria(), purchase_requested=purchase_requested
        )

    assert_record_rejection(
        caught.value, reason, rejection_evidence(purchase_requested)
    )


def test_paid_record_rejection_evidence_holds_the_parsed_cost_and_counts() -> None:
    payload = {
        **rejection_envelope(property_record(RadarID="P-DIFFERENT"), True),
        "totalCost": 12.75,
    }
    with pytest.raises(InvalidResponseError) as caught:
        parse_buyer_transfer_match(
            payload, criteria=criteria(), purchase_requested=True
        )

    error = caught.value
    assert isinstance(error, BuyerTransferResponseError)
    assert str(error) == (
        "PropertyRadar returned invalid buyer-transfer match (radar_id_mismatch)."
    )
    evidence = error.billing_evidence
    assert evidence.purchase_requested is True
    assert evidence.status == "charged"
    assert type(evidence.total_cost) is Decimal
    assert evidence.total_cost == Decimal("12.75")
    assert evidence.currency is None
    assert evidence.quantity_free_remaining is None
    assert evidence.result_count == 1
    assert evidence.total_result_count == 1
    assert evidence.provider_metadata_omitted is False
    with pytest.raises(FrozenInstanceError):
        evidence.total_cost = Decimal("0")  # type: ignore[misc]


def test_record_rejection_cases_cover_every_contract_reason() -> None:
    policy = BUYER_TRANSFER_MATCH_CONTRACT["parser_policy"]
    assert type(policy) is MappingProxyType
    contract_reasons = policy["failure_billing_evidence"]["record_rejection_reasons"]
    covered = {param.values[1] for param in RECORD_REJECTIONS}

    assert "property_type_outside_criterion" not in covered
    assert covered | {"property_type_outside_criterion"} == set(contract_reasons)
    assert tuple(contract_reasons) == RECORD_REJECTION_REASONS


@pytest.mark.parametrize(
    ("payload", "purchase_requested", "reason"),
    [
        pytest.param(
            {
                **rejection_envelope(property_record(RadarID="P-DIFFERENT"), True),
                "totalCost": -1,
            },
            True,
            "total_cost",
            id="total_cost_before_radar_id_mismatch",
        ),
        pytest.param(
            {**rejection_envelope("P-SYNTHETIC", False), "totalCost": True},
            False,
            "total_cost",
            id="total_cost_before_non_object_record",
        ),
        pytest.param(
            {**rejection_envelope(FailingSnapshotMapping(), None), "totalCost": "1e3"},
            None,
            "total_cost",
            id="total_cost_before_record_snapshot",
        ),
        pytest.param(
            {
                **rejection_envelope("P-SYNTHETIC", True),
                "results": ["P-SYNTHETIC", property_record()],
            },
            True,
            "ambiguous_results",
            id="ambiguous_results_with_a_non_object_item",
        ),
        pytest.param(
            {**rejection_envelope(None, False), "results": [None, None]},
            False,
            "ambiguous_results",
            id="ambiguous_results_of_non_object_items",
        ),
        pytest.param(
            {
                **rejection_envelope(None, True),
                "resultCount": 0,
                "totalResultCount": 0,
            },
            True,
            "result_count_mismatch",
            id="counts_before_non_object_record",
        ),
        pytest.param(
            {
                **rejection_envelope(property_record(RadarID="P-DIFFERENT"), None),
                "resultCount": 2,
            },
            None,
            "result_count",
            id="result_count_before_radar_id_mismatch",
        ),
        pytest.param(
            {
                **rejection_envelope(property_record(RadarID="P-DIFFERENT"), True),
                "quantityFreeRemaining": 99,
            },
            True,
            "charged_preview_metadata",
            id="charged_preview_metadata_before_radar_id_mismatch",
        ),
        pytest.param(
            {
                **rejection_envelope(property_record(RadarID="P-DIFFERENT"), False),
                "quantityFreeRemaining": -1,
            },
            False,
            "quantity_free_remaining",
            id="quantity_free_remaining_before_radar_id_mismatch",
        ),
        pytest.param(
            {"results": [property_record(RadarID="P-DIFFERENT")], "totalCost": 1},
            True,
            "required_envelope_fields",
            id="required_envelope_fields_before_radar_id_mismatch",
        ),
        pytest.param(
            {
                **rejection_envelope(property_record(RadarID="P-DIFFERENT"), False),
                "Owner": "PRIVATE",
            },
            False,
            "undocumented_envelope_fields",
            id="undocumented_envelope_fields_before_radar_id_mismatch",
        ),
    ],
)
def test_envelope_count_and_cost_rejections_stay_plain_invalid_response_errors(
    payload: dict[str, object], purchase_requested: bool | None, reason: str
) -> None:
    with pytest.raises(InvalidResponseError) as caught:
        parse_buyer_transfer_match(
            payload, criteria=criteria(), purchase_requested=purchase_requested
        )

    assert_earlier_rejection(caught.value, reason)


def test_buyer_transfer_response_error_takes_billing_evidence_by_keyword() -> None:
    evidence = rejection_evidence(True)
    message = "PropertyRadar returned invalid buyer-transfer match (radar_id)."
    error = BuyerTransferResponseError(message, billing_evidence=evidence)

    assert issubclass(BuyerTransferResponseError, InvalidResponseError)
    assert error.args == (message,)
    assert str(error) == message
    assert error.billing_evidence is evidence
    assert error.status_code is None
    assert error.request_id is None
    assert error.retry_after is None
    with pytest.raises(TypeError):
        BuyerTransferResponseError(message, evidence)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        BuyerTransferResponseError(message)  # type: ignore[call-arg]


@pytest.mark.parametrize("purchase_requested", [True, None])
def test_paid_and_unknown_parsers_keep_the_0_4_1_exact_count_rule(
    purchase_requested: bool | None,
) -> None:
    with pytest.raises(InvalidResponseError, match=r"\(result_count_mismatch\)"):
        parse_buyer_transfer_match(
            envelope(result_count=0, purchase=purchase_requested is True),
            criteria=criteria(),
            purchase_requested=purchase_requested,
        )
    with pytest.raises(InvalidResponseError, match=r"\(ambiguous_total_result_count\)"):
        parse_buyer_transfer_match(
            envelope(records=[], total_result_count=1, purchase=True),
            criteria=criteria(),
            purchase_requested=purchase_requested,
        )


def test_parser_rejects_preview_metadata_on_a_charged_response() -> None:
    payload = {**envelope(purchase=True), "quantityFreeRemaining": 99}
    with pytest.raises(InvalidResponseError, match="charged_preview_metadata"):
        parse_buyer_transfer_match(
            payload,
            criteria=criteria(),
            purchase_requested=True,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {**envelope(), "resultCount": True},
        {**envelope(), "totalResultCount": -1},
        {**envelope(), "totalCost": -1.0},
        {**envelope(), "totalCost": True},
        {**envelope(), "totalCost": "-1.00"},
        {**envelope(), "quantityFreeRemaining": False},
    ],
)
def test_parser_rejects_invalid_billing_shapes(payload: dict[str, object]) -> None:
    with pytest.raises(InvalidResponseError):
        parse_buyer_transfer_match(payload, criteria=criteria())


def test_parser_now_accepts_a_json_float_total_cost() -> None:
    result = parse_buyer_transfer_match(
        {**envelope(), "totalCost": 1.0}, criteria=criteria()
    )

    assert result.billing.total_cost == Decimal("1.0")


def test_parser_snapshots_hostile_inputs_and_sanitizes_failures() -> None:
    raw_results: list[object] = HostileList([property_record()])
    payload = envelope()
    payload["results"] = raw_results
    parsed = parse_buyer_transfer_match(payload, criteria=criteria())
    assert parsed.matched is True

    with pytest.raises(InvalidResponseError) as caught:
        parse_buyer_transfer_match(FailingSnapshotMapping(), criteria=criteria())
    rendered = "\n".join(
        (str(caught.value), "".join(traceback.format_exception(caught.value)))
    )
    assert "SYNTHETIC PRIVATE" not in rendered


def test_live_bare_zero_hit_preview_never_runs_a_hostile_results_list() -> None:
    # Like the 0.4.1 snapshot above, the bare-preview path must not call a
    # list subclass's own methods: it may accept the empty list as the bare
    # preview or fail closed, but no other error and no value may escape.
    try:
        result = parse_buyer_transfer_match(
            {"results": HostileList()},
            criteria=criteria(),
            purchase_requested=False,
        )
    except InvalidResponseError as error:
        rendered = "\n".join((str(error), "".join(traceback.format_exception(error))))
        assert "SYNTHETIC PRIVATE" not in rendered
        assert error.__cause__ is None
    else:
        assert result.matched is False
        assert result.billing.provider_metadata_omitted is True


def test_public_values_are_frozen_and_repr_redacts_property_values() -> None:
    result = parse_buyer_transfer_match(envelope(), criteria=criteria())
    assert result.linkage is not None
    with pytest.raises(FrozenInstanceError):
        result.linkage.property.address = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.linkage.property.residential_basis = None  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.billing.provider_metadata_omitted = True  # type: ignore[misc]

    rendered = repr(result)
    assert "Synthetic Buyer" not in rendered
    assert "P-SYNTHETIC" not in rendered
    assert "81 Synthetic Way" not in rendered
    assert "SYNTHETIC-81" not in rendered
    assert re.search(
        r"residential_basis='?property_type'?[,)]", repr(result.linkage.property)
    )
    assert "provider_metadata_omitted=False" in repr(result.billing)


def test_manually_constructed_values_reject_contradictions() -> None:
    parsed = parse_buyer_transfer_match(envelope(), criteria=criteria())
    assert parsed.linkage is not None
    with pytest.raises(ValueError, match="scope_fingerprint"):
        replace(parsed.linkage, scope_fingerprint="bad")
    with pytest.raises(ValueError, match="counts"):
        replace(parsed.billing, total_result_count=0)
    with pytest.raises(ValueError, match="linkage presence"):
        replace(parsed, linkage=None)


def test_preview_invariants_tie_linkage_presence_to_the_returned_record() -> None:
    preview = parse_buyer_transfer_match(
        live_one_hit_radar_id_only_preview(),
        criteria=criteria(),
        purchase_requested=False,
    )
    bare = parse_buyer_transfer_match(
        live_bare_zero_hit_preview(), criteria=criteria(), purchase_requested=False
    )
    assert preview.linkage is not None

    assert replace(preview.billing, result_count=1).result_count == 1
    with pytest.raises(ValueError):
        replace(preview.billing, result_count=1, total_result_count=0)
    with pytest.raises(ValueError, match="linkage presence"):
        replace(preview, linkage=None)
    with pytest.raises(ValueError, match="linkage presence"):
        replace(preview, billing=replace(preview.billing, total_result_count=0))
    with pytest.raises(ValueError, match="linkage presence"):
        replace(bare, linkage=preview.linkage)

    charged = parse_buyer_transfer_match(
        paid_envelope(), criteria=criteria(), purchase_requested=True
    )
    with pytest.raises(ValueError, match="counts"):
        replace(charged.billing, result_count=0)


def test_provider_metadata_omitted_marker_is_only_valid_on_an_empty_free_preview() -> (
    None
):
    billing = parse_buyer_transfer_match(
        live_bare_zero_hit_preview(), criteria=criteria(), purchase_requested=False
    ).billing
    assert billing.provider_metadata_omitted is True

    # Each change below is valid without the marker, so only the marker rule
    # can raise when the marker stays True.
    replace(billing, provider_metadata_omitted=False, total_cost=Decimal("0.50"))
    replace(billing, provider_metadata_omitted=False, quantity_free_remaining=9866)
    replace(billing, provider_metadata_omitted=False, total_result_count=1)
    with pytest.raises(ValueError):
        replace(billing, provider_metadata_omitted=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        replace(billing, total_cost=Decimal("0.50"))
    with pytest.raises(ValueError):
        replace(billing, quantity_free_remaining=9866)
    with pytest.raises(ValueError):
        replace(billing, total_result_count=1)
    for purchase_requested, status in ((True, "charged"), (None, "unknown")):
        BuyerTransferBillingEvidence(
            purchase_requested=purchase_requested,
            status=status,  # type: ignore[arg-type]
            total_cost=Decimal("0"),
            currency=None,
            quantity_free_remaining=None,
            result_count=0,
            total_result_count=0,
        )
        with pytest.raises(ValueError):
            BuyerTransferBillingEvidence(
                purchase_requested=purchase_requested,
                status=status,  # type: ignore[arg-type]
                total_cost=Decimal("0"),
                currency=None,
                quantity_free_remaining=None,
                result_count=0,
                total_result_count=0,
                provider_metadata_omitted=True,
            )
    default = BuyerTransferBillingEvidence(
        purchase_requested=False,
        status="preview",
        total_cost=Decimal("0"),
        currency=None,
        quantity_free_remaining=None,
        result_count=0,
        total_result_count=0,
    )
    assert default.provider_metadata_omitted is False


def test_public_property_rejects_invalid_manual_states() -> None:
    parsed = parse_buyer_transfer_match(envelope(), criteria=criteria())
    assert parsed.linkage is not None
    property_value = parsed.linkage.property

    with pytest.raises(ValueError, match="immutable field tuple"):
        replace(property_value, returned_fields=["RadarID"])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="contract order"):
        replace(property_value, returned_fields=("Address", "RadarID"))
    with pytest.raises(ValueError, match="required RadarID"):
        replace(property_value, returned_fields=())
    with pytest.raises(ValueError, match="available property values"):
        replace(
            property_value,
            returned_fields=tuple(
                field_name
                for field_name in property_value.returned_fields
                if field_name != "Address"
            ),
        )
    with pytest.raises(ValueError, match="available property values"):
        replace(property_value, address=None)
    with pytest.raises(ValueError, match="radar_id"):
        replace(property_value, radar_id="")
    assert property_value.residential_basis == "property_type"
    with pytest.raises(ValueError, match="property_type"):
        replace(
            property_value,
            property_type="Spaceship",  # type: ignore[arg-type]
            residential_basis=None,
        )
    with pytest.raises(ValueError):
        replace(property_value, property_type="Spaceship")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="address"):
        replace(property_value, address=81)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="zip_five"):
        replace(property_value, zip_five=100000)
    with pytest.raises(ValueError, match="fips"):
        replace(property_value, fips="49A35")
    with pytest.raises(ValueError, match="latitude"):
        replace(property_value, latitude=Decimal("NaN"))


def test_public_linkage_rejects_unavailable_or_mismatched_values() -> None:
    parsed = parse_buyer_transfer_match(envelope(), criteria=criteria())
    assert parsed.linkage is not None
    linkage = parsed.linkage
    assert "P-SYNTHETIC" not in repr(linkage)

    with pytest.raises(ValueError, match="property"):
        replace(linkage, property=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="relationship"):
        replace(linkage, relationship="confirmed_grantee")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="transaction_identifier"):
        replace(linkage, matched_transaction_identifier="synthetic")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="matched_grantees"):
        replace(linkage, matched_grantees=())  # type: ignore[arg-type]


def test_public_billing_rejects_invalid_manual_states() -> None:
    parsed = parse_buyer_transfer_match(envelope(), criteria=criteria())
    billing = parsed.billing

    with pytest.raises(ValueError, match="purchase_requested"):
        replace(billing, purchase_requested=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="status"):
        replace(billing, status="charged")
    with pytest.raises(ValueError, match="total_cost"):
        replace(billing, total_cost=Decimal("-1"))
    with pytest.raises(ValueError, match="currency"):
        replace(billing, currency="USD")
    with pytest.raises(ValueError, match="result_count"):
        replace(billing, result_count=2, total_result_count=2)
    with pytest.raises(ValueError, match="quantity_free_remaining"):
        replace(billing, quantity_free_remaining=-1)
    with pytest.raises(ValueError, match="charged evidence"):
        BuyerTransferBillingEvidence(
            purchase_requested=True,
            status="charged",
            total_cost=Decimal("0.50"),
            currency=None,
            quantity_free_remaining=1,
            result_count=1,
            total_result_count=1,
        )


def test_public_result_and_entrypoints_reject_wrong_types() -> None:
    parsed = parse_buyer_transfer_match(envelope(), criteria=criteria())
    assert parsed.linkage is not None

    with pytest.raises(ValueError, match="contract_fingerprint"):
        replace(parsed, contract_fingerprint="bad")
    with pytest.raises(ValueError, match="contract_fingerprint"):
        replace(parsed, contract_fingerprint=RECENT_CONTRACT_FINGERPRINT_0_4_1)
    with pytest.raises(ValueError, match="scope_fingerprint"):
        replace(parsed, scope_fingerprint="bad")
    with pytest.raises(ValueError, match="exact scope"):
        replace(
            parsed,
            linkage=replace(parsed.linkage, scope_fingerprint="0" * 64),
        )
    with pytest.raises(ValueError, match="billing"):
        replace(parsed, billing=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="criteria"):
        build_buyer_transfer_match_criteria(object())  # type: ignore[arg-type]
    with pytest.raises(InvalidResponseError, match="criteria_type"):
        parse_buyer_transfer_match(
            envelope(),
            criteria=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(InvalidResponseError, match="purchase_requested"):
        parse_buyer_transfer_match(
            envelope(),
            criteria=criteria(),
            purchase_requested=1,  # type: ignore[arg-type]
        )
    with pytest.raises(InvalidResponseError, match="results_type"):
        parse_buyer_transfer_match(
            {**envelope(), "results": {}},
            criteria=criteria(),
        )
    with pytest.raises(InvalidResponseError, match="envelope_type"):
        parse_buyer_transfer_match([], criteria=criteria())  # type: ignore[arg-type]
    with pytest.raises(InvalidResponseError, match="envelope_key_type"):
        parse_buyer_transfer_match(
            {1: "invalid"},  # type: ignore[dict-item]
            criteria=criteria(),
        )


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
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


def test_resource_convenience_makes_one_exact_preview_request() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=live_one_hit_radar_id_only_preview())

    client, http_client = make_client(handler)
    try:
        result = client.properties.buyer_transfer_match(criteria=criteria())
    finally:
        http_client.close()

    assert result.matched is True
    assert result.billing.status == "preview"
    assert result.linkage is not None
    property_value = result.linkage.property
    assert property_value.residential_basis == "property_type_criterion"
    assert property_value.is_residential is True
    assert result.scope_fingerprint == RECENT_SCOPE_FINGERPRINT
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
    body = json.loads(request.content)
    # The preview sends the residential PropertyType criterion before RadarID.
    assert body == {"Criteria": list(PREVIEW_CRITERIA)}
    assert body == {
        "Criteria": list(build_buyer_transfer_match_criteria(criteria(), preview=True))
    }
    assert [item["name"] for item in body["Criteria"]][-2:] == [
        "PropertyType",
        "RadarID",
    ]


def test_resource_convenience_makes_one_exact_paid_request() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=paid_envelope())

    client, http_client = make_client(handler, allow_charges=True)
    try:
        result = client.properties.buyer_transfer_match(
            criteria=criteria(), purchase=True
        )
    finally:
        http_client.close()

    assert result.billing.status == "charged"
    assert result.billing.total_cost == Decimal("1")
    assert result.linkage is not None
    property_value = result.linkage.property
    assert property_value.residential_basis == "property_type"
    assert property_value.is_residential is True
    assert result.scope_fingerprint == RECENT_SCOPE_FINGERPRINT
    assert len(captured) == 1
    assert captured[0].url.params.multi_items() == [
        ("Fields", ",".join(BUYER_TRANSFER_PROPERTY_FIELDS)),
        ("Limit", "1"),
        ("Start", "0"),
        ("Purchase", "1"),
    ]
    body = json.loads(captured[0].content)
    # The paid request keeps the 0.4.1 criteria: no PropertyType criterion.
    assert body == {"Criteria": list(PAID_CRITERIA)}
    assert body == {"Criteria": list(build_buyer_transfer_match_criteria(criteria()))}
    assert b"PropertyType" not in captured[0].content


def test_paid_resource_convenience_classifies_a_commercial_record() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={**paid_envelope(), "results": [property_record(PType="Commercial")]},
        )

    client, http_client = make_client(handler, allow_charges=True)
    try:
        result = client.properties.buyer_transfer_match(
            criteria=criteria(), purchase=True
        )
    finally:
        http_client.close()

    assert result.matched is True
    assert result.linkage is not None
    property_value = result.linkage.property
    assert property_value.property_type == "Commercial"
    assert property_value.residential_basis == "property_type"
    assert property_value.is_residential is False


def test_paid_resource_total_cost_follows_the_transport_json_decoding() -> None:
    # The transport decodes the body with the standard JSON decoder, so a
    # fractional totalCost with more than 15 significant digits is already
    # rounded when the parser sees it. D9 adds no rejection for it.
    body = json.dumps({**paid_envelope(), "totalCost": "TOTAL-COST"}).replace(
        '"TOTAL-COST"', "1.23456789012345678"
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body.encode("ascii"),
            headers={"Content-Type": "application/json"},
        )

    client, http_client = make_client(handler, allow_charges=True)
    try:
        result = client.properties.buyer_transfer_match(
            criteria=criteria(), purchase=True
        )
    finally:
        http_client.close()

    assert result.billing.status == "charged"
    total_cost = result.billing.total_cost
    assert total_cost.as_tuple() == Decimal("1.2345678901234567").as_tuple()
    assert total_cost != Decimal("1.23456789012345678")


def test_paid_resource_record_rejection_propagates_with_evidence_once() -> None:
    calls = 0
    payload = rejection_envelope(property_record(RadarID="P-DIFFERENT"), True)

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=payload)

    client, http_client = make_client(handler, allow_charges=True, max_retries=3)
    try:
        with pytest.raises(BuyerTransferResponseError) as caught:
            client.properties.buyer_transfer_match(criteria=criteria(), purchase=True)
    finally:
        http_client.close()

    assert calls == 1
    assert_record_rejection(caught.value, "radar_id_mismatch", rejection_evidence(True))


def test_preview_resource_outside_the_criterion_propagates_preview_evidence() -> None:
    payload = {
        **live_one_hit_radar_id_only_preview(),
        "results": [{"RadarID": "P-SYNTHETIC", "PType": "Commercial"}],
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client, http_client = make_client(handler)
    try:
        with pytest.raises(BuyerTransferResponseError) as caught:
            client.properties.buyer_transfer_match(criteria=criteria())
    finally:
        http_client.close()

    assert_record_rejection(
        caught.value,
        "property_type_outside_criterion",
        BuyerTransferBillingEvidence(
            purchase_requested=False,
            status="preview",
            total_cost=Decimal("0"),
            currency=None,
            quantity_free_remaining=None,
            result_count=0,
            total_result_count=1,
        ),
    )


def test_resource_convenience_denies_unapproved_charge_before_network() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=envelope(purchase=True))

    client, http_client = make_client(handler)
    try:
        with pytest.raises(ChargeNotAllowedError):
            client.properties.buyer_transfer_match(criteria=criteria(), purchase=True)
    finally:
        http_client.close()
    assert calls == 0


@pytest.mark.parametrize("purchase", [1, 0, None, "true"])
def test_resource_convenience_rejects_non_boolean_purchase_before_network(
    purchase: object,
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=envelope())

    client, http_client = make_client(handler, allow_charges=True)
    try:
        with pytest.raises(TypeError, match="purchase must be a boolean"):
            client.properties.buyer_transfer_match(
                criteria=criteria(),
                purchase=purchase,  # type: ignore[arg-type]
            )
    finally:
        http_client.close()
    assert calls == 0


def test_paid_resource_convenience_is_not_retried() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"message": "synthetic failure"})

    client, http_client = make_client(handler, allow_charges=True, max_retries=3)
    try:
        with pytest.raises(ServerError):
            client.properties.buyer_transfer_match(criteria=criteria(), purchase=True)
    finally:
        http_client.close()
    assert calls == 1


def test_public_dataclass_construction_smoke() -> None:
    property_value = BuyerTransferProperty(
        returned_fields=("RadarID",),
        radar_id="P-SYNTHETIC",
        property_type=None,
        address=None,
        city=None,
        state=None,
        zip_five=None,
        county=None,
        fips=None,
        apn=None,
        latitude=None,
        longitude=None,
    )
    fingerprint = buyer_transfer_scope_fingerprint(criteria())
    linkage = BuyerTransferLinkage(
        scope_fingerprint=fingerprint,
        property=property_value,
    )
    billing = BuyerTransferBillingEvidence(
        purchase_requested=False,
        status="preview",
        total_cost=Decimal("0.00"),
        currency=None,
        quantity_free_remaining=100,
        result_count=1,
        total_result_count=1,
    )
    result = BuyerTransferMatchResult(
        contract_fingerprint=str(BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"]),
        scope_fingerprint=fingerprint,
        linkage=linkage,
        billing=billing,
    )
    assert result.matched is True
    assert property_value.residential_basis is None
    assert billing.provider_metadata_omitted is False


def test_public_dataclass_construction_of_the_live_one_hit_preview() -> None:
    fingerprint = buyer_transfer_scope_fingerprint(criteria())
    result = BuyerTransferMatchResult(
        contract_fingerprint=str(BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"]),
        scope_fingerprint=fingerprint,
        linkage=BuyerTransferLinkage(
            scope_fingerprint=fingerprint,
            property=radar_id_only_property(
                residential_basis="property_type_criterion"
            ),
        ),
        billing=BuyerTransferBillingEvidence(
            purchase_requested=False,
            status="preview",
            total_cost=Decimal("0"),
            currency=None,
            quantity_free_remaining=None,
            result_count=0,
            total_result_count=1,
        ),
    )

    assert result == parse_buyer_transfer_match(
        live_one_hit_radar_id_only_preview(),
        criteria=criteria(),
        purchase_requested=False,
    )
