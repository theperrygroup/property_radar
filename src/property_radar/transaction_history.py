"""Immutable typed parsing for PropertyRadar transaction-history responses."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Literal, NoReturn, TypeVar, cast

from .exceptions import InvalidResponseError

TransactionHistoryStatus = Literal["original", "edited", "deleted", "created"]
TransactionHistoryField = Literal[
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
]
PropertyPersonIdentityField = Literal[
    "RadarID",
    "PersonKey",
    "PersonType",
    "FirstName",
    "MiddleName",
    "LastName",
    "Suffix",
    "EntityName",
    "OwnershipRole",
]
ProviderPersonType = Literal["Person", "Company", "Entity", "Trust"]
PropertyOwnershipRole = Literal["Owner", "Principal", "Trustee"]
TransactionPartyKind = Literal["person", "organization", "unknown"]
TransactionBillingStatus = Literal["preview", "charged", "unknown"]

_KeyT = TypeVar("_KeyT")
_ValueT = TypeVar("_ValueT")

TRANSACTION_HISTORY_FIELDS: tuple[TransactionHistoryField, ...] = (
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
"""Official ordered positive fields for ``properties.transactions``."""

PROPERTY_PERSON_IDENTITY_FIELDS: tuple[PropertyPersonIdentityField, ...] = (
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
"""Official fields for the bounded property-current-owner composition."""

_TRANSACTION_HISTORY_STATUSES = ("original", "edited", "deleted", "created")
_TRANSACTION_HISTORY_FILTER_VALUES = ("CurrentOwner", "All")
_PROVIDER_PERSON_TYPES = ("Person", "Company", "Entity", "Trust")
_PROPERTY_OWNERSHIP_ROLES = ("Owner", "Principal", "Trustee")
_TRANSACTION_ENVELOPE_KEYS = (
    "results",
    "totalCost",
    "quantityFreeRemaining",
    "resultCount",
)
_PARSER_REQUIRED_ENVELOPE_FIELDS = ("results", "totalCost", "resultCount")
_REQUIRED_ENVELOPE_KEYS = frozenset(_PARSER_REQUIRED_ENVELOPE_FIELDS)
_TOTAL_COST_MAX_LENGTH = 64
_TOTAL_COST_PATTERN_SOURCE = r"[0-9]+(?:\.[0-9]+)?"
_TOTAL_COST_PATTERN = re.compile(_TOTAL_COST_PATTERN_SOURCE)
_REQUEST_ID_MAX_LENGTH = 128
_REQUEST_ID_PATTERN_SOURCE = r"[A-Za-z0-9]+-[A-Za-z0-9]+-[A-Za-z0-9]+"
_REQUEST_ID_PATTERN = re.compile(_REQUEST_ID_PATTERN_SOURCE)

_RECORD_FIELD_CONTRACT_SOURCE: dict[str, dict[str, object]] = {
    field_name: {"type": "string", "nullable": False, "required": False}
    for field_name in TRANSACTION_HISTORY_FIELDS
}
_ENVELOPE_FIELD_CONTRACT_SOURCE: dict[str, dict[str, object]] = {
    "results": {"type": "array", "nullable": False, "required": False},
    "totalCost": {"type": "string", "nullable": False, "required": False},
    "quantityFreeRemaining": {
        "type": "integer",
        "nullable": False,
        "required": False,
        "preview_only": True,
    },
    "resultCount": {"type": "integer", "nullable": False, "required": False},
}
_PARTY_FIELD_CONTRACT_SOURCE: dict[str, dict[str, object]] = {
    "kind": {
        "type": "string",
        "values": ("person", "organization", "unknown"),
        "nullable": False,
    },
    "display_name": {"type": "string", "nullable": True},
    "first_name": {"type": "string", "nullable": True},
    "middle_name": {"type": "string", "nullable": True},
    "last_name": {"type": "string", "nullable": True},
    "suffix": {"type": "string", "nullable": True},
    "aliases": {
        "type": "array[string]",
        "nullable": True,
        "provider_source": None,
    },
    "provider_id": {
        "type": "string",
        "nullable": True,
        "provider_source": "PersonKey",
    },
    "provider_type": {
        "type": "string",
        "nullable": True,
        "provider_source": "PersonType",
    },
    "ownership_role": {
        "type": "string",
        "nullable": True,
        "provider_source": "OwnershipRole",
    },
}
_STRUCTURED_IDENTITY_COMPOSITION_SOURCE: dict[str, object] = {
    "operation": "properties.persons",
    "method": "GET",
    "path": "/v1/properties/{RadarID}/persons",
    "ordered_fields": PROPERTY_PERSON_IDENTITY_FIELDS,
    "provider_types": _PROVIDER_PERSON_TYPES,
    "ownership_roles": _PROPERTY_OWNERSHIP_ROLES,
    "order": "provider_results_order",
    "radar_id_match_required": True,
    "relationship": "property_current_owners",
    "transaction_party_linkage": None,
}
_TRANSACTION_PARTY_SOURCE: dict[str, object] = {
    "Grantor": {
        "provider_shape": "scalar_display_string",
        "display_preserved_as": "grantor_display",
        "parties": None,
        "reason": "party_boundaries_not_documented",
    },
    "Grantee": {
        "provider_shape": "scalar_display_string",
        "display_preserved_as": "grantee_display",
        "parties": None,
        "reason": "party_boundaries_not_documented",
    },
}
_BILLING_EVIDENCE_SOURCE: dict[str, object] = {
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
        "sanitized_pattern": _REQUEST_ID_PATTERN_SOURCE,
        "max_length": _REQUEST_ID_MAX_LENGTH,
    },
}
_PARSER_POLICY_SOURCE: dict[str, object] = {
    "required_envelope_fields": _PARSER_REQUIRED_ENVELOPE_FIELDS,
    "reject_undocumented_envelope_fields": True,
    "reject_undocumented_record_fields": True,
    "exact_json_primitive_types": True,
    "snapshot_before_validation": (
        "envelope",
        "results",
        "records",
        "property_persons",
    ),
    "result_count": {
        "minimum": 0,
        "must_match_records": True,
        "provider_maximum": None,
    },
    "quantity_free_remaining": {"minimum": 0},
    "total_cost": {
        "fullmatch_pattern": _TOTAL_COST_PATTERN_SOURCE,
        "max_length": _TOTAL_COST_MAX_LENGTH,
    },
    "empty_display_string": None,
    "whitespace_display_string": "preserve",
    "heuristic_name_splitting": False,
}
_PROVIDER_LIMITATIONS_SOURCE: dict[str, object] = {
    "transaction_grantor_grantee": "scalar_display_strings",
    "document_grantor_grantee": "scalar_display_strings",
    "party_boundaries": None,
    "person_to_transaction_link": None,
    "person_display_name": None,
    "aliases": None,
    "currency": None,
    "success_request_id": None,
}
_CONTRACT_FINGERPRINT_SOURCE: dict[str, object] = {
    "api_version": "5.2.0.0",
    "spec_source": "https://developers.propertyradar.com/_spec/api.json",
    "spec_source_sha256": (
        # pragma: allowlist nextline secret
        "f3808349c387cc1190ae41b24fec37962361b8149fde687179c84a72048e6bd4"
    ),
    "operation": "properties.transactions",
    "method": "GET",
    "path": "/v1/properties/{RadarID}/transactions",
    "filter_values": _TRANSACTION_HISTORY_FILTER_VALUES,
    "ordered_fields": TRANSACTION_HISTORY_FIELDS,
    "envelope_fields": _ENVELOPE_FIELD_CONTRACT_SOURCE,
    "record_fields": _RECORD_FIELD_CONTRACT_SOURCE,
    "party_fields": _PARTY_FIELD_CONTRACT_SOURCE,
    "transaction_party_sources": _TRANSACTION_PARTY_SOURCE,
    "structured_identity_composition": _STRUCTURED_IDENTITY_COMPOSITION_SOURCE,
    "billing_evidence": _BILLING_EVIDENCE_SOURCE,
    "provider_enums": {"Status": _TRANSACTION_HISTORY_STATUSES},
    "provider_limitations": _PROVIDER_LIMITATIONS_SOURCE,
    "parser_policy": _PARSER_POLICY_SOURCE,
}


def _fingerprint_contract(payload: Mapping[str, object]) -> str:
    """Return a stable fingerprint without retaining a mutable source mapping."""
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _freeze_value(value: object) -> object:
    """Recursively freeze a contract value."""
    if isinstance(value, Mapping):
        return _freeze_mapping(cast(Mapping[str, object], value))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    return value


def _freeze_mapping(source: Mapping[str, object]) -> Mapping[str, object]:
    """Recursively freeze a string-keyed contract mapping."""
    return MappingProxyType(
        {key: _freeze_value(value) for key, value in source.items()}
    )


TRANSACTION_HISTORY_CONTRACT = _freeze_mapping(
    {
        **_CONTRACT_FINGERPRINT_SOURCE,
        "contract_fingerprint": _fingerprint_contract(_CONTRACT_FINGERPRINT_SOURCE),
    }
)
"""Deeply immutable official schema catalog and strict parser policy."""


@dataclass(frozen=True, slots=True, repr=False)
class TransactionParty:
    """One structured provider identity without invented name information.

    ``aliases`` is ``None`` for the current provider contract because no
    alias field is documented. A tuple remains available for a future
    provider-supplied alias source without conflating unavailable with empty.
    """

    kind: TransactionPartyKind
    display_name: str | None
    first_name: str | None
    middle_name: str | None
    last_name: str | None
    suffix: str | None
    aliases: tuple[str, ...] | None
    provider_id: str | None
    provider_type: ProviderPersonType | None
    ownership_role: PropertyOwnershipRole | None

    def __post_init__(self) -> None:
        """Reject mutable or malformed identity containers."""
        if self.kind not in ("person", "organization", "unknown"):
            raise ValueError("kind is not a supported party kind")
        if self.aliases is not None and (
            type(self.aliases) is not tuple
            or any(type(alias) is not str for alias in self.aliases)
        ):
            raise ValueError("aliases must be an immutable tuple of strings or None")

    def __repr__(self) -> str:
        """Return metadata only, never names or provider identifiers."""
        component_count = sum(
            value is not None
            for value in (
                self.first_name,
                self.middle_name,
                self.last_name,
                self.suffix,
            )
        )
        alias_count = None if self.aliases is None else len(self.aliases)
        return (
            f"{type(self).__name__}(kind={self.kind!r}, "
            f"display_name_available={self.display_name is not None!r}, "
            f"name_component_count={component_count}, "
            f"alias_count={alias_count!r}, "
            f"provider_id_available={self.provider_id is not None!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class TransactionBillingEvidence:
    """Immutable billing evidence for one transaction-history response."""

    purchase_requested: bool | None
    status: TransactionBillingStatus
    total_cost: Decimal
    currency: str | None
    quantity_free_remaining: int | None
    result_count: int
    request_id: str | None

    def __post_init__(self) -> None:
        """Reject mutable or contradictory manually constructed evidence."""
        if (
            self.purchase_requested is not None
            and type(self.purchase_requested) is not bool
        ):
            raise ValueError("purchase_requested must be bool or None")
        if self.status not in ("preview", "charged", "unknown"):
            raise ValueError("status is not a supported billing status")
        expected_status = {
            False: "preview",
            True: "charged",
            None: "unknown",
        }[self.purchase_requested]
        if self.status != expected_status:
            raise ValueError("status does not match purchase_requested")
        if (
            not isinstance(self.total_cost, Decimal)
            or not self.total_cost.is_finite()
            or self.total_cost < 0
        ):
            raise ValueError("total_cost must be a nonnegative finite Decimal")
        if type(self.result_count) is not int or self.result_count < 0:
            raise ValueError("result_count must be a nonnegative integer")
        if self.quantity_free_remaining is not None and (
            type(self.quantity_free_remaining) is not int
            or self.quantity_free_remaining < 0
        ):
            raise ValueError(
                "quantity_free_remaining must be a nonnegative integer or None"
            )
        if self.status == "charged" and self.quantity_free_remaining is not None:
            raise ValueError(
                "charged evidence cannot include preview-only free quantity"
            )
        if self.request_id is not None and (
            _sanitized_request_id(self.request_id) != self.request_id
        ):
            raise ValueError("request_id is not a sanitized correlation code")

    def __repr__(self) -> str:
        """Return non-personal billing metadata without the request identifier."""
        return (
            f"{type(self).__name__}("
            f"purchase_requested={self.purchase_requested!r}, "
            f"status={self.status!r}, total_cost={self.total_cost!r}, "
            f"currency_available={self.currency is not None!r}, "
            f"quantity_free_remaining={self.quantity_free_remaining!r}, "
            f"result_count={self.result_count!r}, "
            f"request_id_available={self.request_id is not None!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class TransactionHistoryRecord:
    """One immutable transaction with opaque group displays.

    The official endpoint does not expose individual party boundaries.
    ``grantors`` and ``grantees`` are therefore ``None`` for parsed provider
    records, while the exact scalar displays remain available separately.
    The tuple-capable fields allow future structured provider parties without
    constraining either side to zero-or-one.
    """

    returned_fields: tuple[TransactionHistoryField, ...]
    document_type_ui: str | None
    status: TransactionHistoryStatus | None
    purpose: str | None
    loan_position: str | None
    document_number: str | None
    recording_date: str | None
    grantor_display: str | None
    grantee_display: str | None
    grantors: tuple[TransactionParty, ...] | None
    grantees: tuple[TransactionParty, ...] | None
    amount: str | None
    ltv_or_down: str | None
    has_document_image: str | None
    is_first_current_owner_record: str | None
    is_parent_type: str | None
    document_id: str | None

    def __post_init__(self) -> None:
        """Reject mutable party and field containers."""
        if type(self.returned_fields) is not tuple:
            raise ValueError("returned_fields must be an immutable tuple")
        for field_name, parties in (
            ("grantors", self.grantors),
            ("grantees", self.grantees),
        ):
            if parties is not None and (
                type(parties) is not tuple
                or any(not isinstance(party, TransactionParty) for party in parties)
            ):
                raise ValueError(f"{field_name} must be a party tuple or None")

    def __repr__(self) -> str:
        """Return shape metadata without record values or party names."""
        return (
            f"{type(self).__name__}("
            f"returned_field_count={len(self.returned_fields)}, "
            f"grantor_display_available={self.grantor_display is not None!r}, "
            f"grantee_display_available={self.grantee_display is not None!r}, "
            f"grantor_count={None if self.grantors is None else len(self.grantors)!r}, "
            f"grantee_count={None if self.grantees is None else len(self.grantees)!r}, "
            f"document_id_available={self.document_id is not None!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class TransactionHistory:
    """Immutable transactions, current-owner identities, and billing evidence.

    ``current_owners`` is ``None`` when no property-person response was
    composed, an empty tuple when the provider returned no owners, and an
    ordered tuple otherwise. These identities are property-level evidence and
    are deliberately not attached to a particular transaction party.
    """

    records: tuple[TransactionHistoryRecord, ...]
    current_owners: tuple[TransactionParty, ...] | None
    billing: TransactionBillingEvidence

    def __post_init__(self) -> None:
        """Reject mutable record and identity containers."""
        if type(self.records) is not tuple or any(
            not isinstance(record, TransactionHistoryRecord) for record in self.records
        ):
            raise ValueError("records must be an immutable transaction tuple")
        if self.current_owners is not None and (
            type(self.current_owners) is not tuple
            or any(
                not isinstance(party, TransactionParty) for party in self.current_owners
            )
        ):
            raise ValueError("current_owners must be a party tuple or None")
        if not isinstance(self.billing, TransactionBillingEvidence):
            raise ValueError("billing must be TransactionBillingEvidence")

    def __repr__(self) -> str:
        """Return aggregate metadata without licensed record values."""
        return (
            f"{type(self).__name__}(record_count={len(self.records)}, "
            f"current_owners_available={self.current_owners is not None!r}, "
            f"current_owner_count="
            f"{None if self.current_owners is None else len(self.current_owners)!r}, "
            f"billing={self.billing!r})"
        )

    @property
    def total_cost(self) -> Decimal:
        """Return the quoted or returned provider cost."""
        return self.billing.total_cost

    @property
    def quantity_free_remaining(self) -> int | None:
        """Return preview-only free quantity when supplied."""
        return self.billing.quantity_free_remaining

    @property
    def result_count(self) -> int:
        """Return the provider result count."""
        return self.billing.result_count

    @property
    def total_result_count(self) -> int:
        """Return the non-paginated result count compatibility view."""
        return self.billing.result_count

    @property
    def purchase_requested(self) -> bool | None:
        """Return the known request purchase flag, or ``None``."""
        return self.billing.purchase_requested

    @property
    def billing_status(self) -> TransactionBillingStatus:
        """Return preview, charged, or unknown request status."""
        return self.billing.status

    @property
    def currency(self) -> str | None:
        """Return provider currency, currently unavailable."""
        return self.billing.currency

    @property
    def request_id(self) -> str | None:
        """Return a sanitized official request identifier when available."""
        return self.billing.request_id


def parse_transaction_history(
    envelope: Mapping[str, object],
    *,
    purchase_requested: bool | None = None,
    property_persons: Mapping[str, object] | None = None,
    radar_id: str | None = None,
    request_id: str | None = None,
) -> TransactionHistory:
    """Parse official transaction and optional property-person envelopes.

    The parser never infers party boundaries from ``Grantor`` or ``Grantee``.
    When ``property_persons`` is supplied, its ordered identities are exposed
    separately as current-owner evidence after every returned ``RadarID`` is
    checked against ``radar_id``.

    Args:
        envelope: Decoded JSON returned by ``properties.transactions`` when
            requesting :data:`TRANSACTION_HISTORY_FIELDS`.
        purchase_requested: The request's exact ``Purchase`` choice. Use
            ``None`` for a detached response whose request context is unknown.
        property_persons: Optional decoded response from
            ``properties.persons`` using
            :data:`PROPERTY_PERSON_IDENTITY_FIELDS`.
        radar_id: Exact property identifier used for both requests. Required
            when ``property_persons`` is supplied.
        request_id: Official correlation identifier when a success response
            source supplies one. Unsafe shapes are discarded.

    Returns:
        Immutable transaction records, optional ordered current-owner
        identities, and typed billing evidence.

    Raises:
        InvalidResponseError: If either envelope violates the bound contract.
    """
    if purchase_requested is not None and type(purchase_requested) is not bool:
        _raise_invalid("purchase_requested")
    typed_envelope = _snapshot_string_mapping(
        envelope,
        object_reason="envelope_type",
        snapshot_reason="envelope_snapshot",
        key_reason="envelope_key_type",
    )
    envelope_keys = set(typed_envelope)
    if not _REQUIRED_ENVELOPE_KEYS.issubset(envelope_keys):
        _raise_invalid("required_envelope_keys")
    if envelope_keys.difference(_TRANSACTION_ENVELOPE_KEYS):
        _raise_invalid("undocumented_envelope_keys")

    raw_records = typed_envelope["results"]
    if not isinstance(raw_records, list):
        _raise_invalid("results_type")
    raw_record_snapshots = tuple(
        _snapshot_record(raw_record) for raw_record in tuple(list.copy(raw_records))
    )
    records = tuple(_parse_record(raw_record) for raw_record in raw_record_snapshots)
    result_count = _parse_nonnegative_integer(
        typed_envelope["resultCount"],
        field_name="result_count",
    )
    if result_count != len(records):
        _raise_invalid("result_count_mismatch")

    quantity_free_remaining = None
    if "quantityFreeRemaining" in typed_envelope:
        quantity_free_remaining = _parse_nonnegative_integer(
            typed_envelope["quantityFreeRemaining"],
            field_name="quantity_free_remaining",
        )
    if purchase_requested is True and quantity_free_remaining is not None:
        _raise_invalid("charged_preview_metadata")

    current_owners = None
    if property_persons is not None:
        if type(radar_id) is not str or radar_id == "":
            _raise_invalid("composition_radar_id")
        current_owners = _parse_property_persons(property_persons, radar_id=radar_id)

    billing_status: TransactionBillingStatus
    if purchase_requested is None:
        billing_status = "unknown"
    elif purchase_requested:
        billing_status = "charged"
    else:
        billing_status = "preview"

    return TransactionHistory(
        records=records,
        current_owners=current_owners,
        billing=TransactionBillingEvidence(
            purchase_requested=purchase_requested,
            status=billing_status,
            total_cost=_parse_total_cost(typed_envelope["totalCost"]),
            currency=None,
            quantity_free_remaining=quantity_free_remaining,
            result_count=result_count,
            request_id=_sanitized_request_id(request_id),
        ),
    )


def _snapshot_mapping(
    source: Mapping[_KeyT, _ValueT],
    *,
    reason: str,
) -> dict[_KeyT, _ValueT]:
    """Copy one caller-owned mapping and sanitize snapshot failures."""
    try:
        if isinstance(source, dict):
            return dict.copy(source)
        return dict(source)
    except Exception:
        pass
    _raise_invalid(reason)


def _snapshot_string_mapping(
    source: object,
    *,
    object_reason: str,
    snapshot_reason: str,
    key_reason: str,
) -> dict[str, object]:
    """Snapshot one object and require exact string keys."""
    if not isinstance(source, Mapping):
        _raise_invalid(object_reason)
    snapshot = _snapshot_mapping(source, reason=snapshot_reason)
    if any(type(key) is not str for key in tuple(snapshot)):
        _raise_invalid(key_reason)
    return cast(dict[str, object], snapshot)


def _snapshot_record(raw_record: object) -> dict[str, object]:
    """Snapshot one transaction record before validating it."""
    return _snapshot_string_mapping(
        raw_record,
        object_reason="record_type",
        snapshot_reason="record_snapshot",
        key_reason="record_key_type",
    )


def _parse_record(raw_record: Mapping[str, object]) -> TransactionHistoryRecord:
    """Parse one private record snapshot into immutable typed values."""
    record_keys = set(raw_record)
    if record_keys.difference(TRANSACTION_HISTORY_FIELDS):
        _raise_invalid("undocumented_record_fields")
    for value in raw_record.values():
        if type(value) is not str:
            _raise_invalid("record_field_type")

    status_value = _optional_text(raw_record, "Status")
    if status_value is not None and status_value not in _TRANSACTION_HISTORY_STATUSES:
        _raise_invalid("status_enum")

    return TransactionHistoryRecord(
        returned_fields=tuple(
            field_name
            for field_name in TRANSACTION_HISTORY_FIELDS
            if field_name in raw_record
        ),
        document_type_ui=_optional_text(raw_record, "DocTypeUI"),
        status=cast(TransactionHistoryStatus | None, status_value),
        purpose=_optional_text(raw_record, "Purpose"),
        loan_position=_optional_text(raw_record, "LoanPosition"),
        document_number=_optional_text(raw_record, "DocNumber"),
        recording_date=_optional_text(raw_record, "RecDate"),
        grantor_display=_optional_display(raw_record, "Grantor"),
        grantee_display=_optional_display(raw_record, "Grantee"),
        grantors=None,
        grantees=None,
        amount=_optional_text(raw_record, "Amount"),
        ltv_or_down=_optional_text(raw_record, "LTVorDown"),
        has_document_image=_optional_text(raw_record, "hasDocumentImage"),
        is_first_current_owner_record=_optional_text(
            raw_record,
            "isFirstCurrentOwnerRecord",
        ),
        is_parent_type=_optional_text(raw_record, "isParentType"),
        document_id=_optional_text(raw_record, "DocumentID"),
    )


def _parse_property_persons(
    envelope: Mapping[str, object],
    *,
    radar_id: str,
) -> tuple[TransactionParty, ...]:
    """Parse ordered provider current-owner identities without linking records."""
    typed_envelope = _snapshot_string_mapping(
        envelope,
        object_reason="property_persons_envelope_type",
        snapshot_reason="property_persons_snapshot",
        key_reason="property_persons_key_type",
    )
    if set(typed_envelope).difference(_TRANSACTION_ENVELOPE_KEYS):
        _raise_invalid("property_persons_undocumented_envelope_fields")
    raw_results = typed_envelope.get("results")
    if not isinstance(raw_results, list):
        _raise_invalid("property_persons_results_type")
    raw_people = tuple(
        _snapshot_string_mapping(
            raw_person,
            object_reason="property_person_type",
            snapshot_reason="property_person_snapshot",
            key_reason="property_person_key_type",
        )
        for raw_person in tuple(list.copy(raw_results))
    )
    people = tuple(
        _parse_property_person(raw_person, radar_id=radar_id)
        for raw_person in raw_people
    )
    if "resultCount" in typed_envelope:
        result_count = _parse_nonnegative_integer(
            typed_envelope["resultCount"],
            field_name="property_persons_result_count",
        )
        if result_count != len(people):
            _raise_invalid("property_persons_result_count_mismatch")
    if "totalCost" in typed_envelope:
        _parse_total_cost(typed_envelope["totalCost"])
    if "quantityFreeRemaining" in typed_envelope:
        _parse_nonnegative_integer(
            typed_envelope["quantityFreeRemaining"],
            field_name="property_persons_quantity_free_remaining",
        )
    return people


def _parse_property_person(
    raw_person: Mapping[str, object],
    *,
    radar_id: str,
) -> TransactionParty:
    """Parse one dedicated property-person result in provider order."""
    if set(raw_person).difference(PROPERTY_PERSON_IDENTITY_FIELDS):
        _raise_invalid("property_person_undocumented_fields")
    for value in raw_person.values():
        if type(value) is not str:
            _raise_invalid("property_person_field_type")
    if raw_person.get("RadarID") != radar_id:
        _raise_invalid("property_person_radar_id_mismatch")

    provider_type_value = _optional_nonempty_text(raw_person, "PersonType")
    if (
        provider_type_value is not None
        and provider_type_value not in _PROVIDER_PERSON_TYPES
    ):
        _raise_invalid("property_person_type_enum")
    ownership_role_value = _optional_nonempty_text(raw_person, "OwnershipRole")
    if (
        ownership_role_value is not None
        and ownership_role_value not in _PROPERTY_OWNERSHIP_ROLES
    ):
        _raise_invalid("property_person_ownership_role_enum")

    kind: TransactionPartyKind = "unknown"
    if provider_type_value == "Person":
        kind = "person"
    elif provider_type_value in ("Company", "Entity", "Trust"):
        kind = "organization"

    return TransactionParty(
        kind=kind,
        display_name=_optional_nonempty_text(raw_person, "EntityName"),
        first_name=_optional_nonempty_text(raw_person, "FirstName"),
        middle_name=_optional_nonempty_text(raw_person, "MiddleName"),
        last_name=_optional_nonempty_text(raw_person, "LastName"),
        suffix=_optional_nonempty_text(raw_person, "Suffix"),
        aliases=None,
        provider_id=_optional_nonempty_text(raw_person, "PersonKey"),
        provider_type=cast(ProviderPersonType | None, provider_type_value),
        ownership_role=cast(PropertyOwnershipRole | None, ownership_role_value),
    )


def _optional_text(record: Mapping[str, object], field_name: str) -> str | None:
    """Return an already type-validated optional provider string."""
    value = record.get(field_name)
    if value is None:
        return None
    return cast(str, value)


def _optional_nonempty_text(
    record: Mapping[str, object],
    field_name: str,
) -> str | None:
    """Map a missing or exactly blank provider string to unavailable."""
    value = _optional_text(record, field_name)
    return None if value == "" else value


def _optional_display(
    record: Mapping[str, object],
    field_name: Literal["Grantor", "Grantee"],
) -> str | None:
    """Preserve the entire opaque display without inventing boundaries."""
    return _optional_nonempty_text(record, field_name)


def _parse_nonnegative_integer(value: object, *, field_name: str) -> int:
    """Parse an exact nonnegative JSON integer without an invented maximum."""
    if type(value) is not int or value < 0:
        _raise_invalid(field_name)
    return value


def _parse_total_cost(value: object) -> Decimal:
    """Parse the documented decimal string without numeric coercion."""
    if (
        type(value) is not str
        or len(value) > _TOTAL_COST_MAX_LENGTH
        or _TOTAL_COST_PATTERN.fullmatch(value) is None
    ):
        _raise_invalid("total_cost")
    return Decimal(value)


def _sanitized_request_id(value: str | None) -> str | None:
    """Return only a bounded official correlation-code shape."""
    if (
        type(value) is not str
        or len(value) > _REQUEST_ID_MAX_LENGTH
        or _REQUEST_ID_PATTERN.fullmatch(value) is None
    ):
        return None
    return value


def _raise_invalid(reason: str) -> NoReturn:
    """Raise a bounded failure that never echoes source response values."""
    raise InvalidResponseError(
        f"PropertyRadar returned invalid transaction history ({reason})."
    ) from None
