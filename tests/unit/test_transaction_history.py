from __future__ import annotations

import hashlib
import json
import traceback
from collections.abc import Callable, Iterator, Mapping
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
from enum import IntEnum
from types import MappingProxyType
from typing import cast, get_type_hints

import httpx
import pytest

from property_radar import (
    PROPERTY_PERSON_IDENTITY_FIELDS,
    TRANSACTION_HISTORY_CONTRACT,
    TRANSACTION_HISTORY_FIELDS,
    InvalidResponseError,
    PropertyPersonIdentityField,
    PropertyRadarClient,
    TransactionBillingEvidence,
    TransactionHistory,
    TransactionHistoryField,
    TransactionHistoryRecord,
    TransactionParty,
    TransactionPartyKind,
    parse_transaction_history,
)

EXPECTED_TRANSACTION_HISTORY_FIELDS = (
    "DocTypeUI",
    "Status",
    "Purpose",
    "LoanPosition",
    "DocNumber",
    "RecDate",
    "Grantor",
    "Grantee",
    "Amount",
    "LTVorDown",
    "hasDocumentImage",
    "isFirstCurrentOwnerRecord",
    "isParentType",
    "DocumentID",
)
EXPECTED_PROPERTY_PERSON_FIELDS = (
    "RadarID",
    "PersonKey",
    "PersonType",
    "FirstName",
    "MiddleName",
    "LastName",
    "Suffix",
    "EntityName",
    "OwnershipRole",
)


class IntegerSubclass(int):
    """A non-JSON integer type that strict parsing must reject."""


class StringSubclass(str):
    """A non-JSON string type that strict parsing must reject."""


class FloatSubclass(float):
    """A non-JSON float type that strict parsing must reject."""


class CountEnum(IntEnum):
    """An integer enum that must not bypass exact primitive checks."""

    ONE = 1


class MutatingRecordMapping(Mapping[str, object]):
    """A mapping that mutates caller-owned containers after its first read."""

    def __init__(
        self,
        values: dict[str, object],
        mutate_sources: Callable[[], None],
    ) -> None:
        self._values = values
        self._mutate_sources = mutate_sources
        self._has_mutated = False

    def __getitem__(self, key: str) -> object:
        value = self._values[key]
        if not self._has_mutated:
            self._has_mutated = True
            self._mutate_sources()
        return value

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


class FailingSnapshotMapping(Mapping[str, object]):
    """A hostile mapping whose source exception must never escape."""

    def __getitem__(self, key: str) -> object:
        raise RuntimeError(f"SYNTHETIC SECRET FOR {key}")

    def __iter__(self) -> Iterator[str]:
        return iter(("results", "totalCost", "resultCount"))

    def __len__(self) -> int:
        return 3


class HostileList(list[object]):
    """A list subclass whose Python-level traversal must be bypassed."""

    def __iter__(self) -> Iterator[object]:
        raise RuntimeError("SYNTHETIC SECRET LIST ITERATION")

    def __len__(self) -> int:
        raise RuntimeError("SYNTHETIC SECRET LIST LENGTH")


def thaw_contract_value(value: object) -> object:
    """Convert immutable contract containers for canonical JSON hashing."""
    if isinstance(value, Mapping):
        return {
            key: thaw_contract_value(nested_value)
            for key, nested_value in value.items()
        }
    if isinstance(value, tuple):
        return tuple(thaw_contract_value(item) for item in value)
    return value


def assert_deeply_immutable(value: object) -> None:
    """Assert every public contract container is recursively immutable."""
    if isinstance(value, Mapping):
        assert isinstance(value, MappingProxyType)
        for nested_value in value.values():
            assert_deeply_immutable(nested_value)
        return
    if isinstance(value, tuple):
        for nested_value in value:
            assert_deeply_immutable(nested_value)
        return
    assert value is None or type(value) in {bool, int, str}


def synthetic_envelope() -> dict[str, object]:
    """Return one wholly synthetic transaction response."""
    return {
        "results": [
            {
                "DocTypeUI": "Synthetic Grant Deed",
                "Status": "original",
                "Purpose": "Synthetic Market",
                "LoanPosition": "",
                "DocNumber": "SYNTHETIC-001",
                "RecDate": "2026-07-15",
                "Grantor": "SYNTHETIC SELLER LLC",
                "Grantee": "SYNTHETIC BUYER & SYNTHETIC CO-BUYER",
                "Amount": "425000",
                "LTVorDown": "20",
                "hasDocumentImage": "0",
                "isFirstCurrentOwnerRecord": "1",
                "isParentType": "1",
                "DocumentID": "d-synthetic-001",
            }
        ],
        "totalCost": "1.00",
        "quantityFreeRemaining": 249,
        "resultCount": 1,
    }


def synthetic_persons(
    people: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Return a synthetic dedicated property-person response."""
    results = people if people is not None else []
    return {
        "results": results,
        "totalCost": "0.40",
        "quantityFreeRemaining": 248,
        "resultCount": len(results),
    }


def party(
    *,
    kind: str = "person",
    display_name: str | None = None,
    first_name: str | None = "Synthetic",
    aliases: tuple[str, ...] | None = None,
    provider_id: str | None = "p-synthetic",
) -> TransactionParty:
    """Build a typed synthetic party for public-model tests."""
    return TransactionParty(
        kind=cast(TransactionPartyKind, kind),
        display_name=display_name,
        first_name=first_name,
        middle_name=None,
        last_name="Person" if first_name is not None else None,
        suffix=None,
        aliases=aliases,
        provider_id=provider_id,
        provider_type="Person" if kind == "person" else None,
        ownership_role="Owner",
    )


def record_with_parties(
    *,
    grantors: tuple[TransactionParty, ...] | None,
    grantees: tuple[TransactionParty, ...] | None,
) -> TransactionHistoryRecord:
    """Build a minimal synthetic record for cardinality tests."""
    return TransactionHistoryRecord(
        returned_fields=(),
        document_type_ui=None,
        status=None,
        purpose=None,
        loan_position=None,
        document_number=None,
        recording_date=None,
        grantor_display=None,
        grantee_display=None,
        grantors=grantors,
        grantees=grantees,
        amount=None,
        ltv_or_down=None,
        has_document_image=None,
        is_first_current_owner_record=None,
        is_parent_type=None,
        document_id=None,
    )


# 0.4.2 accepts a JSON int or float totalCost (D1), documents totalResultCount
# and accepts withheld preview rows, so the contract fingerprint moves.
TRANSACTION_HISTORY_CONTRACT_FINGERPRINT_0_4_1 = (
    # pragma: allowlist nextline secret
    "d750039019a93bbfc0449b6eecdb47ea8f064e18a7dcfcbd01c3ec30c4e057a8"
)
TRANSACTION_HISTORY_CONTRACT_FINGERPRINT_0_4_2 = (
    # pragma: allowlist nextline secret
    "db0dd03413f298367f79749e522bd3e454e295cafcc68e7dd6d077085254e707"
)
TOTAL_COST_PROVIDER_TYPES = ("integer", "number", "string")
TOTAL_COST_REJECTED_CLASSES = (
    "boolean",
    "null",
    "nan",
    "infinity",
    "negative",
    "negative_zero",
    "over_64_characters",
    "other_types",
)
TOTAL_COST_ERROR = (
    r"^PropertyRadar returned invalid transaction history \(total_cost\)\.$"
)
# The exact live Purchase=0 transactions body, byte for byte as JSON text.
LIVE_TRANSACTIONS_PREVIEW_BODY = (
    '{"results":[],"totalCost":0,"quantityFreeRemaining":9866,'
    '"resultCount":2,"totalResultCount":2}'
)
# Every accepted totalCost class and the exact Decimal it must become.
ACCEPTED_TOTAL_COSTS = [
    pytest.param(0, Decimal("0"), id="json-int-zero-live"),
    pytest.param(12, Decimal("12"), id="json-int"),
    pytest.param(10**64 - 1, Decimal("9" * 64), id="json-int-64-digits"),
    pytest.param(0.0, Decimal("0.0"), id="json-float-zero"),
    pytest.param(0.5, Decimal("0.5"), id="json-float-half"),
    pytest.param(1.25, Decimal("1.25"), id="json-float"),
    pytest.param(0.1, Decimal("0.1"), id="json-float-repr-not-binary"),
    pytest.param(2.675, Decimal("2.675"), id="json-float-repr-not-rounded"),
    pytest.param(1e-7, Decimal("1E-7"), id="json-float-exponent-form"),
    pytest.param(1e63, Decimal("1E+63"), id="json-float-64-character-plain-form"),
    pytest.param(1e-62, Decimal("1E-62"), id="json-float-64-character-fraction"),
    pytest.param("3.50", Decimal("3.50"), id="decimal-string-scale-kept"),
    pytest.param("0", Decimal("0"), id="decimal-string-zero"),
    pytest.param("9" * 64, Decimal("9" * 64), id="decimal-string-64-characters"),
]
ACCEPTED_TOTAL_COST_VALUES = [
    pytest.param(case.values[0], id=case.id) for case in ACCEPTED_TOTAL_COSTS
]
# Every rejected totalCost class; each fails closed with the total_cost reason.
REJECTED_TOTAL_COSTS = [
    pytest.param(True, id="bool-true"),
    pytest.param(False, id="bool-false"),
    pytest.param(None, id="null"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
    pytest.param(-1, id="negative-int"),
    pytest.param(-0.5, id="negative-float"),
    pytest.param(-0.0, id="negative-zero-float"),
    pytest.param(10**64, id="int-65-digits"),
    pytest.param(10**5000, id="int-beyond-the-str-conversion-limit"),
    pytest.param("1" * 65, id="string-65-characters"),
    pytest.param(1e300, id="float-301-character-plain-form"),
    pytest.param(1e64, id="float-65-character-plain-form"),
    pytest.param(1e-63, id="float-65-character-fraction"),
    pytest.param(5e-324, id="float-subnormal-326-character-fraction"),
    pytest.param([], id="list"),
    pytest.param([0], id="list-holding-a-valid-cost"),
    pytest.param({}, id="dict"),
    pytest.param({"totalCost": 0}, id="dict-holding-a-valid-cost"),
    pytest.param(Decimal("1.25"), id="decimal-object"),
    pytest.param(IntegerSubclass(1), id="int-subclass"),
    pytest.param(FloatSubclass(0.5), id="float-subclass"),
    pytest.param(StringSubclass("0.50"), id="string-subclass"),
]
# JSON wire tokens for totalCost, decoded by the transport's stdlib JSON parser.
ACCEPTED_WIRE_TOTAL_COSTS = [
    pytest.param("0", Decimal("0"), id="json-int-zero-live"),
    pytest.param("12", Decimal("12"), id="json-int"),
    pytest.param("0.5", Decimal("0.5"), id="json-float-half"),
    pytest.param("1.25", Decimal("1.25"), id="json-float"),
    pytest.param("0.1", Decimal("0.1"), id="json-float-repr-not-binary"),
    pytest.param("1e-7", Decimal("1E-7"), id="json-float-exponent-form"),
    pytest.param('"3.50"', Decimal("3.50"), id="json-decimal-string"),
]
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


def live_transactions_preview_envelope() -> dict[str, object]:
    """Return the exact live Purchase=0 transactions envelope (totalCost int 0)."""
    return {
        "results": [],
        "totalCost": 0,
        "quantityFreeRemaining": 9866,
        "resultCount": 2,
        "totalResultCount": 2,
    }


def d1_preview_envelope() -> dict[str, object]:
    """Return a preview that isolates D1 from the withheld-row rule."""
    return {
        "results": [],
        "totalCost": 0,
        "resultCount": 0,
        "quantityFreeRemaining": 9866,
    }


def envelope_for_purchase(
    purchase_requested: bool | None, total_cost: object
) -> dict[str, object]:
    """Return the synthetic envelope, valid for one purchase mode, with a cost."""
    envelope = synthetic_envelope()
    envelope["totalCost"] = total_cost
    if purchase_requested is True:
        envelope.pop("quantityFreeRemaining")
    return envelope


def body_with_total_cost(envelope: Mapping[str, object], token: str) -> str:
    """Return JSON wire text for an envelope with one raw totalCost token."""
    placeholder = "SYNTHETIC_TOTAL_COST_TOKEN"
    text = json.dumps({**envelope, "totalCost": placeholder}, separators=(",", ":"))
    return text.replace(f'"{placeholder}"', token)


def json_response(body: str) -> httpx.Response:
    """Return a 200 response that carries the exact JSON wire text."""
    return httpx.Response(
        200,
        content=body.encode("ascii"),
        headers={"Content-Type": "application/json"},
    )


def make_client(
    handler: Callable[[httpx.Request], httpx.Response], *, allow_charges: bool = False
) -> tuple[PropertyRadarClient, httpx.Client]:
    """Return a client whose only transport is the synthetic handler."""
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


def preview_billing(**changes: object) -> TransactionBillingEvidence:
    """Return manual preview evidence for two withheld rows."""
    values: dict[str, object] = {
        "purchase_requested": False,
        "status": "preview",
        "total_cost": Decimal("0"),
        "currency": None,
        "quantity_free_remaining": 9866,
        "result_count": 2,
        "request_id": None,
    }
    values.update(changes)
    return TransactionBillingEvidence(**values)  # type: ignore[arg-type]


def test_contract_is_current_deeply_immutable_and_fingerprinted() -> None:
    assert isinstance(TRANSACTION_HISTORY_CONTRACT, MappingProxyType)
    assert TRANSACTION_HISTORY_CONTRACT["api_version"] == "5.2.0.0"
    assert TRANSACTION_HISTORY_CONTRACT["spec_source"] == (
        "https://developers.propertyradar.com/_spec/api.json"
    )
    assert TRANSACTION_HISTORY_CONTRACT["spec_source_sha256"] == (
        # pragma: allowlist nextline secret
        "f3808349c387cc1190ae41b24fec37962361b8149fde687179c84a72048e6bd4"
    )
    assert TRANSACTION_HISTORY_CONTRACT["operation"] == "properties.transactions"
    assert TRANSACTION_HISTORY_CONTRACT["filter_values"] == ("CurrentOwner", "All")
    assert TRANSACTION_HISTORY_FIELDS == EXPECTED_TRANSACTION_HISTORY_FIELDS
    assert PROPERTY_PERSON_IDENTITY_FIELDS == EXPECTED_PROPERTY_PERSON_FIELDS
    assert TRANSACTION_HISTORY_CONTRACT["ordered_fields"] == (
        EXPECTED_TRANSACTION_HISTORY_FIELDS
    )
    assert TRANSACTION_HISTORY_CONTRACT["structured_identity_composition"] == {
        "operation": "properties.persons",
        "method": "GET",
        "path": "/v1/properties/{RadarID}/persons",
        "ordered_fields": EXPECTED_PROPERTY_PERSON_FIELDS,
        "provider_types": ("Person", "Company", "Entity", "Trust"),
        "ownership_roles": ("Owner", "Principal", "Trustee"),
        "order": "provider_results_order",
        "radar_id_match_required": True,
        "relationship": "property_current_owners",
        "transaction_party_linkage": None,
    }
    assert TRANSACTION_HISTORY_CONTRACT["provider_limitations"] == {
        "transaction_grantor_grantee": "scalar_display_strings",
        "document_grantor_grantee": "scalar_display_strings",
        "party_boundaries": None,
        "person_to_transaction_link": None,
        "person_display_name": None,
        "aliases": None,
        "currency": None,
        "success_request_id": None,
    }
    assert TRANSACTION_HISTORY_CONTRACT["billing_evidence"] == {
        "purchase_requested": {
            "type": "boolean",
            "nullable": True,
            "response_echoed": False,
        },
        "status_values": ("preview", "charged", "unknown"),
        "status_rules": {
            "purchase_false": "preview",
            "purchase_true": "charged",
            "purchase_unavailable": "unknown",
        },
        "total_cost": {
            "provider_source": "totalCost",
            "type": "decimal",
            "provider_types": TOTAL_COST_PROVIDER_TYPES,
            "required_by_parser": True,
        },
        "currency": {
            "type": "string",
            "nullable": True,
            "provider_source": None,
        },
        "quantity_free_remaining": {
            "provider_source": "quantityFreeRemaining",
            "preview_only": True,
        },
        "result_count": {"provider_source": "resultCount"},
        "total_result_count": {
            "provider_source": "totalResultCount",
            "nullable": True,
        },
        "request_id": {
            "type": "string",
            "nullable": True,
            "success_response_source": None,
            "sanitized_pattern": r"[A-Za-z0-9]+-[A-Za-z0-9]+-[A-Za-z0-9]+",
            "max_length": 128,
        },
    }
    assert TRANSACTION_HISTORY_CONTRACT["envelope_fields"] == {
        "results": {"type": "array", "nullable": False, "required": False},
        "totalCost": {
            "type": TOTAL_COST_PROVIDER_TYPES,
            "nullable": False,
            "required": False,
        },
        "quantityFreeRemaining": {
            "type": "integer",
            "nullable": False,
            "required": False,
            "preview_only": True,
        },
        "resultCount": {"type": "integer", "nullable": False, "required": False},
        "totalResultCount": {
            "type": "integer",
            "nullable": False,
            "required": False,
        },
    }
    parser_policy = cast(
        Mapping[str, object], TRANSACTION_HISTORY_CONTRACT["parser_policy"]
    )
    assert parser_policy["required_envelope_fields"] == (
        "results",
        "totalCost",
        "resultCount",
    )
    assert parser_policy["total_cost"] == {
        "fullmatch_pattern": r"[0-9]+(?:\.[0-9]+)?",
        "max_length": 64,
        "accepted_types": TOTAL_COST_PROVIDER_TYPES,
        "integer": "exact_int_minimum_0_maximum_64_digits",
        "number": "finite_float_minimum_0_decimal_repr_plain_form_matches_pattern",
        "rejected": TOTAL_COST_REJECTED_CLASSES,
    }
    assert parser_policy["result_count"] == {
        "minimum": 0,
        "must_match_records": True,
        "provider_maximum": None,
        "withheld_records": {
            "purchase_requested": False,
            "results": "empty",
            "result_count": "positive",
            "records_withheld": True,
        },
    }
    assert parser_policy["total_result_count"] == {
        "required": False,
        "minimum": 0,
        "not_less_than": "result_count",
        "provider_maximum": None,
    }
    assert parser_policy["property_persons_envelope_fields"] == (
        "results",
        "totalCost",
        "quantityFreeRemaining",
        "resultCount",
    )
    fingerprint_source = {
        key: thaw_contract_value(value)
        for key, value in TRANSACTION_HISTORY_CONTRACT.items()
        if key != "contract_fingerprint"
    }
    encoded_contract = json.dumps(
        fingerprint_source,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    assert (
        hashlib.sha256(encoded_contract).hexdigest()
        == (TRANSACTION_HISTORY_CONTRACT["contract_fingerprint"])
    )
    assert TRANSACTION_HISTORY_CONTRACT["contract_fingerprint"] == (
        TRANSACTION_HISTORY_CONTRACT_FINGERPRINT_0_4_2
    )
    assert TRANSACTION_HISTORY_CONTRACT["contract_fingerprint"] != (
        TRANSACTION_HISTORY_CONTRACT_FINGERPRINT_0_4_1
    )
    assert_deeply_immutable(TRANSACTION_HISTORY_CONTRACT)

    contract = cast(dict[str, object], TRANSACTION_HISTORY_CONTRACT)
    with pytest.raises(TypeError):
        contract["api_version"] = "forged"
    composition = cast(
        dict[str, object],
        TRANSACTION_HISTORY_CONTRACT["structured_identity_composition"],
    )
    with pytest.raises(TypeError):
        composition["relationship"] = "forged"
    party_fields = cast(
        dict[str, object],
        TRANSACTION_HISTORY_CONTRACT["party_fields"],
    )
    aliases = cast(dict[str, object], party_fields["aliases"])
    with pytest.raises(TypeError):
        aliases["provider_source"] = "InventedAliases"


def test_public_model_supports_zero_one_and_multiple_parties() -> None:
    first = party(provider_id="p-synthetic-1")
    second = party(
        kind="organization",
        display_name="SYNTHETIC ORGANIZATION",
        first_name=None,
        provider_id="p-synthetic-2",
    )

    zero = record_with_parties(grantors=(), grantees=())
    one = record_with_parties(grantors=(first,), grantees=(second,))
    multiple = record_with_parties(
        grantors=(first, second),
        grantees=(second, first),
    )

    assert zero.grantors == ()
    assert len(cast(tuple[TransactionParty, ...], one.grantees)) == 1
    assert multiple.grantors == (first, second)
    assert multiple.grantees == (second, first)


def test_party_alias_and_currency_types_distinguish_unknown_from_supplied() -> None:
    unknown_aliases = party(aliases=None)
    supplied_aliases = party(aliases=("SYNTHETIC ALIAS ONE", "SYNTHETIC ALIAS TWO"))
    explicit_currency = TransactionBillingEvidence(
        purchase_requested=False,
        status="preview",
        total_cost=Decimal("1.00"),
        currency="SYNTHETIC-CURRENCY",
        quantity_free_remaining=1,
        result_count=1,
        request_id=None,
    )

    assert unknown_aliases.aliases is None
    assert supplied_aliases.aliases == (
        "SYNTHETIC ALIAS ONE",
        "SYNTHETIC ALIAS TWO",
    )
    assert explicit_currency.currency == "SYNTHETIC-CURRENCY"
    assert "SYNTHETIC" not in repr(supplied_aliases)
    assert "SYNTHETIC-CURRENCY" not in repr(explicit_currency)


def test_parse_returns_immutable_values_and_unknown_billing_context() -> None:
    parsed = parse_transaction_history(
        synthetic_envelope(),
        request_id="synthetic-123-request",
    )

    record = parsed.records[0]
    assert record.returned_fields == TRANSACTION_HISTORY_FIELDS
    assert record.document_type_ui == "Synthetic Grant Deed"
    assert record.grantor_display == "SYNTHETIC SELLER LLC"
    assert record.grantee_display == "SYNTHETIC BUYER & SYNTHETIC CO-BUYER"
    assert record.grantors is None
    assert record.grantees is None
    assert parsed.current_owners is None
    assert parsed.billing == TransactionBillingEvidence(
        purchase_requested=None,
        status="unknown",
        total_cost=Decimal("1.00"),
        currency=None,
        quantity_free_remaining=249,
        result_count=1,
        request_id="synthetic-123-request",
    )
    assert parsed.total_cost == Decimal("1.00")
    assert parsed.result_count == 1
    assert parsed.total_result_count == 1
    assert parsed.billing.total_result_count is None
    assert parsed.records_withheld is False
    assert parsed.billing_status == "unknown"
    assert parsed.purchase_requested is None
    assert parsed.currency is None
    assert parsed.request_id == "synthetic-123-request"
    assert not hasattr(parsed, "__dict__")
    assert not hasattr(record, "__dict__")
    with pytest.raises(FrozenInstanceError):
        parsed.records = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        record.status = "deleted"  # type: ignore[misc]

    history_hints = get_type_hints(TransactionHistory)
    record_hints = get_type_hints(TransactionHistoryRecord)
    assert history_hints["current_owners"] == tuple[TransactionParty, ...] | None
    assert record_hints["returned_fields"] == tuple[TransactionHistoryField, ...]
    person_field: PropertyPersonIdentityField = "PersonKey"
    assert person_field in PROPERTY_PERSON_IDENTITY_FIELDS


@pytest.mark.parametrize(
    ("purchase_requested", "expected_status"),
    [(False, "preview"), (None, "unknown")],
)
def test_preview_and_unknown_billing_status(
    purchase_requested: bool | None,
    expected_status: str,
) -> None:
    parsed = parse_transaction_history(
        synthetic_envelope(),
        purchase_requested=purchase_requested,
    )
    assert parsed.billing.status == expected_status
    assert parsed.billing.purchase_requested is purchase_requested
    assert parsed.billing.currency is None
    assert parsed.billing.quantity_free_remaining == 249


def test_charged_billing_requires_absence_of_preview_only_metadata() -> None:
    envelope = synthetic_envelope()
    envelope.pop("quantityFreeRemaining")

    parsed = parse_transaction_history(envelope, purchase_requested=True)

    assert parsed.billing.status == "charged"
    assert parsed.billing.purchase_requested is True
    assert parsed.billing.total_cost == Decimal("1.00")
    assert parsed.billing.quantity_free_remaining is None

    contradictory = synthetic_envelope()
    with pytest.raises(InvalidResponseError, match=r"\(charged_preview_metadata\)"):
        parse_transaction_history(contradictory, purchase_requested=True)


@pytest.mark.parametrize("purchase_requested", [0, 1, "false", []])
def test_purchase_context_rejects_non_boolean_values(
    purchase_requested: object,
) -> None:
    with pytest.raises(InvalidResponseError, match=r"\(purchase_requested\)"):
        parse_transaction_history(
            synthetic_envelope(),
            purchase_requested=cast(bool, purchase_requested),
        )


def test_request_id_is_bounded_and_never_accepts_arbitrary_text() -> None:
    unsafe_values = (
        "SYNTHETIC PRIVATE NAME",
        "synthetic/address",
        "a" * 129,
        "",
    )
    for unsafe in unsafe_values:
        assert (
            parse_transaction_history(
                synthetic_envelope(),
                request_id=unsafe,
            ).request_id
            is None
        )

    assert (
        parse_transaction_history(
            synthetic_envelope(),
            request_id="abc-123-def",
        ).request_id
        == "abc-123-def"
    )


def test_property_person_composition_preserves_provider_order_and_identity() -> None:
    persons = synthetic_persons(
        [
            {
                "RadarID": "P-SYNTHETIC",
                "PersonKey": "p-synthetic-person",
                "PersonType": "Person",
                "FirstName": "Synthetic",
                "MiddleName": "Q",
                "LastName": "Purchaser",
                "Suffix": "Jr",
                "EntityName": "",
                "OwnershipRole": "Owner",
            },
            {
                "RadarID": "P-SYNTHETIC",
                "PersonKey": "p-synthetic-company",
                "PersonType": "Company",
                "FirstName": "",
                "MiddleName": "",
                "LastName": "",
                "Suffix": "",
                "EntityName": "SYNTHETIC HOLDINGS LLC",
                "OwnershipRole": "Principal",
            },
            {
                "RadarID": "P-SYNTHETIC",
                "PersonKey": "",
                "PersonType": "",
                "FirstName": "",
                "MiddleName": "",
                "LastName": "",
                "Suffix": "",
                "EntityName": "",
                "OwnershipRole": "",
            },
        ]
    )

    parsed = parse_transaction_history(
        synthetic_envelope(),
        purchase_requested=False,
        property_persons=persons,
        radar_id="P-SYNTHETIC",
    )

    assert parsed.current_owners == (
        TransactionParty(
            kind="person",
            display_name=None,
            first_name="Synthetic",
            middle_name="Q",
            last_name="Purchaser",
            suffix="Jr",
            aliases=None,
            provider_id="p-synthetic-person",
            provider_type="Person",
            ownership_role="Owner",
        ),
        TransactionParty(
            kind="organization",
            display_name="SYNTHETIC HOLDINGS LLC",
            first_name=None,
            middle_name=None,
            last_name=None,
            suffix=None,
            aliases=None,
            provider_id="p-synthetic-company",
            provider_type="Company",
            ownership_role="Principal",
        ),
        TransactionParty(
            kind="unknown",
            display_name=None,
            first_name=None,
            middle_name=None,
            last_name=None,
            suffix=None,
            aliases=None,
            provider_id=None,
            provider_type=None,
            ownership_role=None,
        ),
    )
    assert parsed.records[0].grantees is None
    assert parsed.records[0].grantee_display == ("SYNTHETIC BUYER & SYNTHETIC CO-BUYER")


@pytest.mark.parametrize("provider_type", ("Company", "Entity", "Trust"))
def test_every_provider_organization_type_is_preserved(
    provider_type: str,
) -> None:
    parsed = parse_transaction_history(
        synthetic_envelope(),
        property_persons=synthetic_persons(
            [
                {
                    "RadarID": "P-SYNTHETIC",
                    "PersonType": provider_type,
                    "EntityName": "SYNTHETIC ENTITY",
                }
            ]
        ),
        radar_id="P-SYNTHETIC",
    )
    owner = cast(tuple[TransactionParty, ...], parsed.current_owners)[0]
    assert owner.kind == "organization"
    assert owner.provider_type == provider_type
    assert owner.display_name == "SYNTHETIC ENTITY"


def test_zero_property_persons_is_distinct_from_no_composition() -> None:
    absent = parse_transaction_history(synthetic_envelope())
    empty = parse_transaction_history(
        synthetic_envelope(),
        property_persons=synthetic_persons(),
        radar_id="P-SYNTHETIC",
    )

    assert absent.current_owners is None
    assert empty.current_owners == ()


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (
            lambda envelope: cast(dict[str, object], envelope).update(
                {"Aliases": ["SYNTHETIC"]}
            ),
            "property_person_undocumented_fields",
        ),
        (
            lambda envelope: cast(dict[str, object], envelope).update(
                {"PersonType": "Other"}
            ),
            "property_person_type_enum",
        ),
        (
            lambda envelope: cast(dict[str, object], envelope).update(
                {"OwnershipRole": "Other"}
            ),
            "property_person_ownership_role_enum",
        ),
        (
            lambda envelope: cast(dict[str, object], envelope).update(
                {"PersonKey": 123}
            ),
            "property_person_field_type",
        ),
        (
            lambda envelope: cast(dict[str, object], envelope).update(
                {"RadarID": "P-OTHER"}
            ),
            "property_person_radar_id_mismatch",
        ),
        (
            lambda envelope: cast(dict[str, object], envelope).pop("RadarID"),
            "property_person_radar_id_mismatch",
        ),
    ],
)
def test_property_person_malformed_fields_fail_closed(
    mutator: Callable[[object], object],
    reason: str,
) -> None:
    person: dict[str, object] = {
        "RadarID": "P-SYNTHETIC",
        "PersonType": "Person",
        "FirstName": "SYNTHETIC PRIVATE NAME",
    }
    mutator(person)
    with pytest.raises(
        InvalidResponseError,
        match=rf"\({reason}\)",
    ) as failure:
        parse_transaction_history(
            synthetic_envelope(),
            property_persons=synthetic_persons([person]),
            radar_id="P-SYNTHETIC",
        )
    assert "PRIVATE NAME" not in str(failure.value)


@pytest.mark.parametrize(
    ("persons", "radar_id", "reason"),
    [
        (
            cast(Mapping[str, object], []),
            "P-SYNTHETIC",
            "property_persons_envelope_type",
        ),
        ({}, "P-SYNTHETIC", "property_persons_results_type"),
        ({"results": {}}, "P-SYNTHETIC", "property_persons_results_type"),
        (
            {"results": ["bad"]},
            "P-SYNTHETIC",
            "property_person_type",
        ),
        (
            {"results": [], "unknown": "value"},
            "P-SYNTHETIC",
            "property_persons_undocumented_envelope_fields",
        ),
        (
            {"results": [], "resultCount": 1},
            "P-SYNTHETIC",
            "property_persons_result_count_mismatch",
        ),
        (
            {"results": [], "resultCount": True},
            "P-SYNTHETIC",
            "property_persons_result_count",
        ),
        (
            {"results": [], "totalCost": -1},
            "P-SYNTHETIC",
            "total_cost",
        ),
        (
            {"results": [], "totalResultCount": 0},
            "P-SYNTHETIC",
            "property_persons_undocumented_envelope_fields",
        ),
        (
            {"results": [], "quantityFreeRemaining": -1},
            "P-SYNTHETIC",
            "property_persons_quantity_free_remaining",
        ),
        ({"results": []}, None, "composition_radar_id"),
        ({"results": []}, "", "composition_radar_id"),
    ],
)
def test_property_person_composition_envelope_failures(
    persons: Mapping[str, object],
    radar_id: str | None,
    reason: str,
) -> None:
    with pytest.raises(InvalidResponseError, match=rf"\({reason}\)"):
        parse_transaction_history(
            synthetic_envelope(),
            property_persons=persons,
            radar_id=radar_id,
        )


def test_property_person_keys_and_snapshots_are_sanitized() -> None:
    bad_key_persons: dict[object, object] = {"results": []}
    bad_key_persons[1] = "private"
    with pytest.raises(
        InvalidResponseError,
        match=r"\(property_persons_key_type\)",
    ):
        parse_transaction_history(
            synthetic_envelope(),
            property_persons=cast(Mapping[str, object], bad_key_persons),
            radar_id="P-SYNTHETIC",
        )

    bad_person_key: dict[object, object] = {"RadarID": "P-SYNTHETIC", 1: "private"}
    with pytest.raises(InvalidResponseError, match=r"\(property_person_key_type\)"):
        parse_transaction_history(
            synthetic_envelope(),
            property_persons=synthetic_persons(
                [cast(dict[str, object], bad_person_key)]
            ),
            radar_id="P-SYNTHETIC",
        )

    with pytest.raises(InvalidResponseError, match=r"\(property_person_snapshot\)"):
        parse_transaction_history(
            synthetic_envelope(),
            property_persons={"results": [FailingSnapshotMapping()]},
            radar_id="P-SYNTHETIC",
        )


def test_transaction_displays_are_never_split_or_trimmed() -> None:
    envelope = synthetic_envelope()
    record = cast(list[dict[str, str]], envelope["results"])[0]
    record["Grantor"] = "ONE, TWO & THREE / FOUR"
    record["Grantee"] = "   "

    parsed = parse_transaction_history(envelope)

    assert parsed.records[0].grantor_display == "ONE, TWO & THREE / FOUR"
    assert parsed.records[0].grantee_display == "   "
    assert parsed.records[0].grantors is None
    assert parsed.records[0].grantees is None

    record["Grantor"] = ""
    assert parse_transaction_history(envelope).records[0].grantor_display is None


def test_returned_fields_follow_official_order_and_status_values() -> None:
    envelope = synthetic_envelope()
    source_record = cast(list[dict[str, str]], envelope["results"])[0]
    envelope["results"] = [dict(reversed(tuple(source_record.items())))]
    assert parse_transaction_history(envelope).records[0].returned_fields == (
        EXPECTED_TRANSACTION_HISTORY_FIELDS
    )

    for status in ("original", "edited", "deleted", "created"):
        cast(list[dict[str, str]], envelope["results"])[0]["Status"] = status
        assert parse_transaction_history(envelope).records[0].status == status


def test_optional_fields_and_source_mutation_remain_detached() -> None:
    source: dict[str, object] = {
        "results": [{"Grantee": "SYNTHETIC BUYER"}],
        "totalCost": "0",
        "resultCount": 1,
    }
    parsed = parse_transaction_history(source)
    record = parsed.records[0]
    assert record.returned_fields == ("Grantee",)
    assert record.grantee_display == "SYNTHETIC BUYER"
    assert record.grantor_display is None
    assert record.recording_date is None
    assert parsed.quantity_free_remaining is None

    source_records = cast(list[dict[str, str]], source["results"])
    source_records[0]["Grantee"] = "CHANGED"
    source_records.clear()
    source["totalCost"] = "999.00"
    source["resultCount"] = 0
    assert record.grantee_display == "SYNTHETIC BUYER"
    assert parsed.total_cost == Decimal("0")
    assert parsed.result_count == 1


def test_snapshots_precede_caller_mutation_and_bypass_hostile_list() -> None:
    envelope = synthetic_envelope()
    source_records = cast(list[object], envelope["results"])
    record_values: dict[str, object] = {"Grantee": "SYNTHETIC BUYER"}

    def mutate_sources() -> None:
        envelope["resultCount"] = 2
        source_records.append({"Grantee": "SYNTHETIC LATE APPEND"})
        record_values["Grantee"] = ["SYNTHETIC", "MUTATED"]

    source_records[:] = [MutatingRecordMapping(record_values, mutate_sources)]
    parsed = parse_transaction_history(envelope)
    assert parsed.records[0].grantee_display == "SYNTHETIC BUYER"
    assert parsed.result_count == 1

    hostile = synthetic_envelope()
    source_record = cast(list[object], hostile["results"])[0]
    hostile["results"] = HostileList([source_record])
    assert parse_transaction_history(hostile).records[0].document_id == (
        "d-synthetic-001"
    )


@pytest.mark.parametrize(
    ("envelope", "reason"),
    [
        (FailingSnapshotMapping(), "envelope_snapshot"),
        (
            {
                "results": [FailingSnapshotMapping()],
                "totalCost": "1.00",
                "resultCount": 1,
            },
            "record_snapshot",
        ),
    ],
)
def test_snapshot_failures_are_sanitized(
    envelope: Mapping[str, object],
    reason: str,
) -> None:
    with pytest.raises(
        InvalidResponseError,
        match=rf"^PropertyRadar returned invalid transaction history \({reason}\)\.$",
    ) as failure:
        parse_transaction_history(envelope)

    assert "SECRET" not in str(failure.value)
    assert failure.value.__context__ is None
    assert "SECRET" not in "".join(
        traceback.format_exception(failure.type, failure.value, failure.tb)
    )


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (
            lambda envelope: envelope.update({"undocumented": "value"}),
            "undocumented_envelope_keys",
        ),
        (
            lambda envelope: envelope.update({"currency": "USD"}),
            "undocumented_envelope_keys",
        ),
        (
            lambda envelope: envelope.update({"requestId": "SYNTHETIC"}),
            "undocumented_envelope_keys",
        ),
        (
            lambda envelope: cast(dict[object, object], envelope).update({1: "value"}),
            "envelope_key_type",
        ),
        (lambda envelope: envelope.pop("results"), "required_envelope_keys"),
        (lambda envelope: envelope.pop("totalCost"), "required_envelope_keys"),
        (lambda envelope: envelope.pop("resultCount"), "required_envelope_keys"),
        (lambda envelope: envelope.update({"results": {}}), "results_type"),
        (lambda envelope: envelope.update({"results": None}), "results_type"),
        (lambda envelope: envelope.update({"results": True}), "results_type"),
        (
            lambda envelope: cast(list[object], envelope["results"]).append("bad"),
            "record_type",
        ),
        (
            lambda envelope: cast(list[dict[str, object]], envelope["results"])[
                0
            ].update({"Unknown": "value"}),
            "undocumented_record_fields",
        ),
        (
            lambda envelope: cast(
                dict[object, object],
                cast(list[object], envelope["results"])[0],
            ).update({1: "value"}),
            "record_key_type",
        ),
        (
            lambda envelope: cast(list[dict[str, object]], envelope["results"])[
                0
            ].update({"Grantee": ["ONE", "TWO"]}),
            "record_field_type",
        ),
        (
            lambda envelope: cast(list[dict[str, object]], envelope["results"])[
                0
            ].update({"Status": "unknown"}),
            "status_enum",
        ),
        (lambda envelope: envelope.update({"resultCount": True}), "result_count"),
        (lambda envelope: envelope.update({"resultCount": None}), "result_count"),
        (lambda envelope: envelope.update({"resultCount": "1"}), "result_count"),
        (lambda envelope: envelope.update({"resultCount": -1}), "result_count"),
        (
            lambda envelope: envelope.update({"resultCount": CountEnum.ONE}),
            "result_count",
        ),
        (
            lambda envelope: envelope.update({"resultCount": IntegerSubclass(1)}),
            "result_count",
        ),
        (
            lambda envelope: envelope.update({"resultCount": 2}),
            "result_count_mismatch",
        ),
        (
            lambda envelope: envelope.update({"results": []}),
            "result_count_mismatch",
        ),
        (
            lambda envelope: envelope.update({"totalResultCount": True}),
            "total_result_count",
        ),
        (
            lambda envelope: envelope.update({"totalResultCount": None}),
            "total_result_count",
        ),
        (
            lambda envelope: envelope.update({"totalResultCount": 0}),
            "total_result_count_mismatch",
        ),
        (
            lambda envelope: envelope.update({"quantityFreeRemaining": -1}),
            "quantity_free_remaining",
        ),
        (
            lambda envelope: envelope.update({"quantityFreeRemaining": True}),
            "quantity_free_remaining",
        ),
        (
            lambda envelope: envelope.update({"quantityFreeRemaining": "249"}),
            "quantity_free_remaining",
        ),
        (lambda envelope: envelope.update({"totalCost": -1}), "total_cost"),
        (lambda envelope: envelope.update({"totalCost": True}), "total_cost"),
        (lambda envelope: envelope.update({"totalCost": None}), "total_cost"),
        (lambda envelope: envelope.update({"totalCost": "-1.00"}), "total_cost"),
        (lambda envelope: envelope.update({"totalCost": "1e0"}), "total_cost"),
        (lambda envelope: envelope.update({"totalCost": " 1.00 "}), "total_cost"),
        (lambda envelope: envelope.update({"totalCost": "NaN"}), "total_cost"),
        (
            lambda envelope: envelope.update({"totalCost": StringSubclass("1.00")}),
            "total_cost",
        ),
        (
            lambda envelope: envelope.update({"totalCost": "\u0661.\u0660\u0660"}),
            "total_cost",
        ),
        (
            lambda envelope: envelope.update({"totalCost": "1" * 65}),
            "total_cost",
        ),
    ],
)
def test_malformed_transaction_shapes_fail_closed(
    mutator: Callable[[dict[str, object]], object],
    reason: str,
) -> None:
    envelope = synthetic_envelope()
    mutator(envelope)
    with pytest.raises(
        InvalidResponseError,
        match=rf"\({reason}\)",
    ) as failure:
        parse_transaction_history(envelope)
    assert "SYNTHETIC" not in str(failure.value)


@pytest.mark.parametrize("field_name", EXPECTED_TRANSACTION_HISTORY_FIELDS)
def test_every_official_record_field_rejects_null(field_name: str) -> None:
    envelope = synthetic_envelope()
    cast(list[dict[str, object]], envelope["results"])[0][field_name] = None
    with pytest.raises(InvalidResponseError, match=r"\(record_field_type\)"):
        parse_transaction_history(envelope)


@pytest.mark.parametrize(
    "total_cost",
    ("0", "00", "01.00", "1.001", "1" * 64),
)
def test_total_cost_accepts_bounded_ascii_decimal_strings(
    total_cost: str,
) -> None:
    envelope = synthetic_envelope()
    envelope["totalCost"] = total_cost
    assert parse_transaction_history(envelope).total_cost == Decimal(total_cost)


def test_quantity_free_remaining_has_no_undocumented_int32_ceiling() -> None:
    envelope = synthetic_envelope()
    envelope["quantityFreeRemaining"] = 2_147_483_648
    assert parse_transaction_history(envelope).quantity_free_remaining == (
        2_147_483_648
    )


def test_sanitized_representations_never_expose_record_values() -> None:
    parsed = parse_transaction_history(
        synthetic_envelope(),
        property_persons=synthetic_persons(
            [
                {
                    "RadarID": "P-SYNTHETIC",
                    "PersonKey": "p-private-id",
                    "PersonType": "Person",
                    "FirstName": "PRIVATE FIRST",
                    "LastName": "PRIVATE LAST",
                }
            ]
        ),
        radar_id="P-SYNTHETIC",
        request_id="private-123-request",
    )
    representations = (
        repr(parsed),
        str(parsed),
        repr(parsed.records[0]),
        repr(cast(tuple[TransactionParty, ...], parsed.current_owners)[0]),
        repr(parsed.billing),
    )
    forbidden = (
        "PRIVATE FIRST",
        "PRIVATE LAST",
        "p-private-id",
        "SYNTHETIC SELLER",
        "SYNTHETIC BUYER",
        "d-synthetic-001",
        "private-123-request",
    )
    for representation in representations:
        assert all(secret not in representation for secret in forbidden)


def test_manual_model_validation_rejects_mutable_or_contradictory_values() -> None:
    with pytest.raises(ValueError, match="party kind"):
        party(kind="not-supported")
    with pytest.raises(ValueError, match="aliases"):
        TransactionParty(
            kind="person",
            display_name=None,
            first_name=None,
            middle_name=None,
            last_name=None,
            suffix=None,
            aliases=cast(tuple[str, ...], ["mutable"]),
            provider_id=None,
            provider_type=None,
            ownership_role=None,
        )
    with pytest.raises(ValueError, match="returned_fields"):
        replace(
            record_with_parties(grantors=None, grantees=None),
            returned_fields=cast(tuple[TransactionHistoryField, ...], []),
        )


def test_non_mapping_envelope_fails_closed() -> None:
    with pytest.raises(InvalidResponseError, match=r"\(envelope_type\)"):
        parse_transaction_history(cast(Mapping[str, object], []))


@pytest.mark.parametrize("purchase_requested", [False, True, None])
@pytest.mark.parametrize(("total_cost", "expected"), ACCEPTED_TOTAL_COSTS)
def test_main_envelope_accepts_json_int_float_and_decimal_string_costs_exactly(
    total_cost: object,
    expected: Decimal,
    purchase_requested: bool | None,
) -> None:
    parsed = parse_transaction_history(
        envelope_for_purchase(purchase_requested, total_cost),
        purchase_requested=purchase_requested,
    )

    assert type(parsed.total_cost) is Decimal
    assert parsed.total_cost == expected
    assert parsed.total_cost.as_tuple() == expected.as_tuple()
    assert parsed.result_count == 1
    assert len(parsed.records) == 1


@pytest.mark.parametrize("total_cost", [0.1, 2.675, 1e-7])
def test_float_costs_convert_through_repr_not_the_binary_expansion(
    total_cost: float,
) -> None:
    parsed = parse_transaction_history(
        envelope_for_purchase(False, total_cost), purchase_requested=False
    )

    assert parsed.total_cost == Decimal(repr(total_cost))
    assert parsed.total_cost != Decimal(total_cost)


@pytest.mark.parametrize("purchase_requested", [False, True, None])
@pytest.mark.parametrize("total_cost", REJECTED_TOTAL_COSTS)
def test_main_envelope_rejects_each_cost_class_outside_the_rule(
    total_cost: object,
    purchase_requested: bool | None,
) -> None:
    with pytest.raises(InvalidResponseError, match=TOTAL_COST_ERROR) as failure:
        parse_transaction_history(
            envelope_for_purchase(purchase_requested, total_cost),
            purchase_requested=purchase_requested,
        )
    assert failure.value.__cause__ is None


@pytest.mark.parametrize("total_cost", ACCEPTED_TOTAL_COST_VALUES)
def test_property_persons_envelope_accepts_each_total_cost_class(
    total_cost: object,
) -> None:
    persons = synthetic_persons()
    persons["totalCost"] = total_cost

    parsed = parse_transaction_history(
        synthetic_envelope(),
        property_persons=persons,
        radar_id="P-SYNTHETIC",
    )

    assert parsed.current_owners == ()
    assert parsed.total_cost == Decimal("1.00")


@pytest.mark.parametrize("total_cost", REJECTED_TOTAL_COSTS)
def test_property_persons_envelope_rejects_each_cost_class_outside_the_rule(
    total_cost: object,
) -> None:
    persons = synthetic_persons()
    persons["totalCost"] = total_cost
    with pytest.raises(InvalidResponseError, match=TOTAL_COST_ERROR):
        parse_transaction_history(
            synthetic_envelope(),
            property_persons=persons,
            radar_id="P-SYNTHETIC",
        )


def test_live_transactions_preview_envelope_parses_with_withheld_rows() -> None:
    envelope = live_transactions_preview_envelope()

    parsed = parse_transaction_history(envelope, purchase_requested=False)

    assert parsed.records == ()
    assert parsed.records_withheld is True
    assert parsed.current_owners is None
    assert parsed.result_count == 2
    assert parsed.total_result_count == 2
    assert type(parsed.total_cost) is Decimal
    assert parsed.total_cost.as_tuple() == Decimal("0").as_tuple()
    assert parsed.quantity_free_remaining == 9866
    assert parsed.billing_status == "preview"
    assert parsed.billing == TransactionBillingEvidence(
        purchase_requested=False,
        status="preview",
        total_cost=Decimal("0"),
        currency=None,
        quantity_free_remaining=9866,
        result_count=2,
        request_id=None,
        total_result_count=2,
    )
    assert envelope == live_transactions_preview_envelope()
    assert repr(parsed).startswith(
        "TransactionHistory(record_count=0, records_withheld=True, "
    )
    assert repr(parsed.billing).endswith(
        "result_count=2, total_result_count=2, request_id_available=False)"
    )


@pytest.mark.parametrize("purchase_requested", [True, None])
def test_live_transactions_preview_envelope_is_never_a_charged_or_unknown_history(
    purchase_requested: bool | None,
) -> None:
    with pytest.raises(InvalidResponseError, match=r"\(result_count_mismatch\)"):
        parse_transaction_history(
            live_transactions_preview_envelope(),
            purchase_requested=purchase_requested,
        )


def test_live_transactions_preview_envelope_through_transaction_history() -> None:
    decoded = json.loads(LIVE_TRANSACTIONS_PREVIEW_BODY)
    assert decoded == live_transactions_preview_envelope()
    assert type(decoded["totalCost"]) is int
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(LIVE_TRANSACTIONS_PREVIEW_BODY)

    client, transport = make_client(handler)
    try:
        history = client.properties.transaction_history("P-SYNTHETIC", purchase=False)
    finally:
        transport.close()

    assert history.records == ()
    assert history.records_withheld is True
    assert history.current_owners is None
    assert history.billing_status == "preview"
    assert history.purchase_requested is False
    assert type(history.total_cost) is Decimal
    assert history.total_cost.as_tuple() == Decimal("0").as_tuple()
    assert history.quantity_free_remaining == 9866
    assert history.result_count == 2
    assert history.total_result_count == 2
    assert history.billing.total_result_count == 2
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert request.url.path == "/v1/properties/P-SYNTHETIC/transactions"
    assert request.url.params.multi_items() == [
        ("Fields", ",".join(TRANSACTION_HISTORY_FIELDS)),
        ("Purchase", "0"),
    ]


def test_d1_preview_through_transaction_history_keeps_the_json_int_cost_exact() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(json.dumps(d1_preview_envelope()))

    client, transport = make_client(handler)
    try:
        history = client.properties.transaction_history("P-SYNTHETIC", purchase=False)
    finally:
        transport.close()

    assert history.records == ()
    assert history.records_withheld is False
    assert history.billing_status == "preview"
    assert type(history.total_cost) is Decimal
    assert history.total_cost.as_tuple() == Decimal("0").as_tuple()
    assert history.quantity_free_remaining == 9866
    assert history.result_count == 0
    assert history.billing.total_result_count is None
    assert history.total_result_count == 0
    assert len(requests) == 1


@pytest.mark.parametrize(("token", "expected"), ACCEPTED_WIRE_TOTAL_COSTS)
def test_transaction_history_accepts_each_wire_total_cost_on_the_live_shape(
    token: str, expected: Decimal
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(
            body_with_total_cost(live_transactions_preview_envelope(), token)
        )

    client, transport = make_client(handler)
    try:
        history = client.properties.transaction_history("P-SYNTHETIC")
    finally:
        transport.close()

    assert type(history.total_cost) is Decimal
    assert history.total_cost == expected
    assert history.total_cost.as_tuple() == expected.as_tuple()
    assert history.records_withheld is True
    assert history.total_result_count == 2
    assert len(requests) == 1


@pytest.mark.parametrize("token", REJECTED_WIRE_TOTAL_COSTS)
def test_transaction_history_rejects_each_invalid_wire_total_cost_on_the_live_shape(
    token: str,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(
            body_with_total_cost(live_transactions_preview_envelope(), token)
        )

    client, transport = make_client(handler)
    try:
        with pytest.raises(InvalidResponseError, match=TOTAL_COST_ERROR):
            client.properties.transaction_history("P-SYNTHETIC")
    finally:
        transport.close()
    assert len(requests) == 1


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        pytest.param("1", Decimal("1"), id="json-int"),
        pytest.param("0.25", Decimal("0.25"), id="json-float"),
        pytest.param('"0.25"', Decimal("0.25"), id="json-decimal-string"),
    ],
)
def test_paid_transaction_history_accepts_json_costs_and_total_result_count(
    token: str, expected: Decimal
) -> None:
    envelope = synthetic_envelope()
    envelope.pop("quantityFreeRemaining")
    envelope["totalResultCount"] = 3
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(body_with_total_cost(envelope, token))

    client, transport = make_client(handler, allow_charges=True)
    try:
        history = client.properties.transaction_history("P-SYNTHETIC", purchase=True)
    finally:
        transport.close()

    assert history.billing_status == "charged"
    assert type(history.total_cost) is Decimal
    assert history.total_cost.as_tuple() == expected.as_tuple()
    assert len(history.records) == 1
    assert history.records_withheld is False
    assert history.result_count == 1
    assert history.billing.total_result_count == 3
    assert history.total_result_count == 3
    assert len(requests) == 1
    assert requests[0].url.params["Purchase"] == "1"


def test_paid_transaction_history_rejects_a_nan_cost_without_retry() -> None:
    envelope = synthetic_envelope()
    envelope.pop("quantityFreeRemaining")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return json_response(body_with_total_cost(envelope, "NaN"))

    client, transport = make_client(handler, allow_charges=True)
    try:
        with pytest.raises(InvalidResponseError, match=TOTAL_COST_ERROR):
            client.properties.transaction_history("P-SYNTHETIC", purchase=True)
    finally:
        transport.close()
    assert len(requests) == 1


@pytest.mark.parametrize("purchase_requested", [False, True, None])
@pytest.mark.parametrize("total_result_count", [1, 2, 2_147_483_648])
def test_total_result_count_is_documented_optional_and_not_below_result_count(
    total_result_count: int,
    purchase_requested: bool | None,
) -> None:
    envelope = envelope_for_purchase(purchase_requested, "1.00")
    envelope["totalResultCount"] = total_result_count

    parsed = parse_transaction_history(envelope, purchase_requested=purchase_requested)

    assert parsed.result_count == 1
    assert len(parsed.records) == 1
    assert parsed.billing.total_result_count == total_result_count
    assert parsed.total_result_count == total_result_count
    assert parsed.records_withheld is False


@pytest.mark.parametrize(
    "total_result_count",
    [
        pytest.param(True, id="bool-true"),
        pytest.param(False, id="bool-false"),
        pytest.param(None, id="null"),
        pytest.param("2", id="string"),
        pytest.param(2.0, id="float"),
        pytest.param(-1, id="negative"),
        pytest.param(IntegerSubclass(2), id="int-subclass"),
        pytest.param(CountEnum.ONE, id="int-enum"),
        pytest.param([2], id="list"),
    ],
)
def test_total_result_count_rejects_every_non_exact_nonnegative_int(
    total_result_count: object,
) -> None:
    envelope = live_transactions_preview_envelope()
    envelope["totalResultCount"] = total_result_count
    with pytest.raises(
        InvalidResponseError,
        match=r"^PropertyRadar returned invalid transaction history "
        r"\(total_result_count\)\.$",
    ):
        parse_transaction_history(envelope, purchase_requested=False)


@pytest.mark.parametrize(
    ("result_count", "total_result_count"), [(2, 1), (2, 0), (3, 2)]
)
def test_result_count_above_total_result_count_fails_closed(
    result_count: int,
    total_result_count: int,
) -> None:
    envelope = live_transactions_preview_envelope()
    envelope["resultCount"] = result_count
    envelope["totalResultCount"] = total_result_count
    with pytest.raises(
        InvalidResponseError,
        match=r"^PropertyRadar returned invalid transaction history "
        r"\(total_result_count_mismatch\)\.$",
    ):
        parse_transaction_history(envelope, purchase_requested=False)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"resultCount": True, "totalResultCount": True}, "result_count"),
        ({"totalResultCount": True, "totalCost": None}, "total_result_count"),
        (
            {"totalResultCount": True, "quantityFreeRemaining": -1},
            "total_result_count",
        ),
        ({"resultCount": 2, "totalResultCount": 1}, "total_result_count_mismatch"),
        (
            {"totalResultCount": 0, "quantityFreeRemaining": -1},
            "total_result_count_mismatch",
        ),
        ({"totalResultCount": "1", "results": "bad"}, "results_type"),
        (
            {"totalResultCount": 1, "undocumented": "value"},
            "undocumented_envelope_keys",
        ),
    ],
)
def test_total_result_count_checks_follow_the_documented_order(
    changes: dict[str, object],
    reason: str,
) -> None:
    envelope = synthetic_envelope()
    envelope.update(changes)
    with pytest.raises(InvalidResponseError, match=rf"\({reason}\)"):
        parse_transaction_history(envelope)


@pytest.mark.parametrize("result_count", [1, 2, 2_147_483_648])
def test_preview_accepts_withheld_rows_without_total_result_count(
    result_count: int,
) -> None:
    envelope: dict[str, object] = {
        "results": [],
        "totalCost": "0.00",
        "quantityFreeRemaining": 9866,
        "resultCount": result_count,
    }

    parsed = parse_transaction_history(envelope, purchase_requested=False)

    assert parsed.records == ()
    assert parsed.records_withheld is True
    assert parsed.result_count == result_count
    assert parsed.billing.total_result_count is None
    assert parsed.total_result_count == result_count
    assert parsed.billing_status == "preview"


@pytest.mark.parametrize("purchase_requested", [True, None])
def test_charged_and_unknown_modes_never_accept_withheld_rows(
    purchase_requested: bool | None,
) -> None:
    envelope: dict[str, object] = {
        "results": [],
        "totalCost": 0,
        "resultCount": 2,
        "totalResultCount": 2,
    }
    with pytest.raises(InvalidResponseError, match=r"\(result_count_mismatch\)"):
        parse_transaction_history(envelope, purchase_requested=purchase_requested)


@pytest.mark.parametrize("purchase_requested", [False, True, None])
def test_empty_results_with_zero_result_count_are_never_withheld(
    purchase_requested: bool | None,
) -> None:
    parsed = parse_transaction_history(
        {"results": [], "totalCost": 0, "resultCount": 0},
        purchase_requested=purchase_requested,
    )

    assert parsed.records == ()
    assert parsed.records_withheld is False
    assert parsed.result_count == 0
    assert parsed.total_result_count == 0


@pytest.mark.parametrize("purchase_requested", [False, True, None])
def test_non_empty_results_must_match_result_count_in_every_mode(
    purchase_requested: bool | None,
) -> None:
    envelope = envelope_for_purchase(purchase_requested, "1.00")
    envelope["resultCount"] = 2
    envelope["totalResultCount"] = 2
    with pytest.raises(InvalidResponseError, match=r"\(result_count_mismatch\)"):
        parse_transaction_history(envelope, purchase_requested=purchase_requested)


def test_withheld_preview_rows_still_compose_current_owners() -> None:
    parsed = parse_transaction_history(
        live_transactions_preview_envelope(),
        purchase_requested=False,
        property_persons=synthetic_persons(
            [{"RadarID": "P-SYNTHETIC", "PersonType": "Person", "FirstName": "SYN"}]
        ),
        radar_id="P-SYNTHETIC",
    )

    assert parsed.records == ()
    assert parsed.records_withheld is True
    owners = cast(tuple[TransactionParty, ...], parsed.current_owners)
    assert len(owners) == 1
    assert owners[0].first_name == "SYN"


def test_new_model_fields_are_last_with_defaults_for_0_4_1_constructions() -> None:
    assert [field.name for field in fields(TransactionBillingEvidence)] == [
        "purchase_requested",
        "status",
        "total_cost",
        "currency",
        "quantity_free_remaining",
        "result_count",
        "request_id",
        "total_result_count",
    ]
    assert [field.name for field in fields(TransactionHistory)] == [
        "records",
        "current_owners",
        "billing",
        "records_withheld",
    ]
    positional = TransactionBillingEvidence(
        False, "preview", Decimal("0"), None, 9866, 2, None
    )
    assert positional == preview_billing()
    assert positional.total_result_count is None
    history = TransactionHistory((), None, positional)
    assert history == TransactionHistory(
        records=(), current_owners=None, billing=positional, records_withheld=False
    )
    assert history.records_withheld is False
    assert history.total_result_count == 2
    assert repr(history).startswith(
        "TransactionHistory(record_count=0, records_withheld=False, "
    )
    assert repr(positional).endswith(
        "result_count=2, total_result_count=None, request_id_available=False)"
    )


@pytest.mark.parametrize("total_result_count", [None, 2, 3, 2_147_483_648])
def test_manual_billing_accepts_total_result_count_not_below_result_count(
    total_result_count: int | None,
) -> None:
    billing = preview_billing(total_result_count=total_result_count)

    history = TransactionHistory(records=(), current_owners=None, billing=billing)

    assert billing.total_result_count == total_result_count
    expected = 2 if total_result_count is None else total_result_count
    assert history.total_result_count == expected


@pytest.mark.parametrize(
    "total_result_count",
    [
        pytest.param(True, id="bool-true"),
        pytest.param(False, id="bool-false"),
        pytest.param(-1, id="negative"),
        pytest.param(0, id="below-result-count"),
        pytest.param(1, id="one-below-result-count"),
        pytest.param("3", id="string"),
        pytest.param(3.0, id="float"),
        pytest.param(IntegerSubclass(3), id="int-subclass"),
    ],
)
def test_manual_billing_rejects_invalid_total_result_count(
    total_result_count: object,
) -> None:
    with pytest.raises(
        ValueError,
        match="total_result_count must be None or a nonnegative integer "
        "not less than result_count",
    ):
        preview_billing(total_result_count=total_result_count)


def test_manual_history_accepts_records_withheld_for_an_empty_positive_preview() -> (
    None
):
    withheld = TransactionHistory(
        records=(),
        current_owners=None,
        billing=preview_billing(total_result_count=2),
        records_withheld=True,
    )

    assert withheld.records_withheld is True
    assert withheld == parse_transaction_history(
        live_transactions_preview_envelope(), purchase_requested=False
    )
    assert replace(withheld, records_withheld=False).records_withheld is False


@pytest.mark.parametrize(
    "records_withheld",
    [
        pytest.param(1, id="int-one"),
        pytest.param(0, id="int-zero"),
        pytest.param("True", id="string"),
        pytest.param(None, id="null"),
    ],
)
def test_manual_history_rejects_a_non_boolean_records_withheld(
    records_withheld: object,
) -> None:
    with pytest.raises(ValueError, match="records_withheld must be a boolean"):
        TransactionHistory(
            records=(),
            current_owners=None,
            billing=preview_billing(),
            records_withheld=cast(bool, records_withheld),
        )


@pytest.mark.parametrize(
    ("records", "billing"),
    [
        pytest.param(
            (record_with_parties(grantors=None, grantees=None),),
            preview_billing(),
            id="records-present",
        ),
        pytest.param(
            (),
            TransactionBillingEvidence(
                purchase_requested=True,
                status="charged",
                total_cost=Decimal("0"),
                currency=None,
                quantity_free_remaining=None,
                result_count=2,
                request_id=None,
            ),
            id="charged",
        ),
        pytest.param(
            (),
            TransactionBillingEvidence(
                purchase_requested=None,
                status="unknown",
                total_cost=Decimal("0"),
                currency=None,
                quantity_free_remaining=None,
                result_count=2,
                request_id=None,
            ),
            id="unknown",
        ),
        pytest.param((), preview_billing(result_count=0), id="zero-result-count"),
    ],
)
def test_manual_history_rejects_records_withheld_outside_an_empty_positive_preview(
    records: tuple[TransactionHistoryRecord, ...],
    billing: TransactionBillingEvidence,
) -> None:
    with pytest.raises(
        ValueError,
        match="records_withheld requires no records, preview status "
        "and a positive result_count",
    ):
        TransactionHistory(
            records=records,
            current_owners=None,
            billing=billing,
            records_withheld=True,
        )
