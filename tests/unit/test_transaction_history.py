from __future__ import annotations

import hashlib
import json
import traceback
from collections.abc import Callable, Iterator, Mapping
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from enum import IntEnum
from types import MappingProxyType
from typing import cast, get_type_hints

import pytest

from property_radar import (
    PROPERTY_PERSON_IDENTITY_FIELDS,
    TRANSACTION_HISTORY_CONTRACT,
    TRANSACTION_HISTORY_FIELDS,
    InvalidResponseError,
    PropertyPersonIdentityField,
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
            "type": "decimal_string",
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
        "request_id": {
            "type": "string",
            "nullable": True,
            "success_response_source": None,
            "sanitized_pattern": r"[A-Za-z0-9]+-[A-Za-z0-9]+-[A-Za-z0-9]+",
            "max_length": 128,
        },
    }
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
        # pragma: allowlist nextline secret
        "d750039019a93bbfc0449b6eecdb47ea8f064e18a7dcfcbd01c3ec30c4e057a8"
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
            {"results": [], "totalCost": 1},
            "P-SYNTHETIC",
            "total_cost",
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
        (lambda envelope: envelope.update({"totalCost": 1}), "total_cost"),
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
