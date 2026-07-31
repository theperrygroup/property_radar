"""Typed buyer/grantee search linkage with immutable property location."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Literal, NoReturn, TypeVar, cast

from .exceptions import InvalidResponseError
from .types import Criterion

BuyerTransferPropertyField = Literal[
    "RadarID",
    "PType",
    "Address",
    "City",
    "State",
    "ZipFive",
    "County",
    "FIPS",
    "APN",
    "Latitude",
    "Longitude",
]
BuyerTransferBillingStatus = Literal["preview", "charged", "unknown"]
BuyerTransferLinkageRelationship = Literal["provider_buyer_criterion_property_match"]
BuyerTransferPropertyType = Literal[
    "Single Family",
    "Condominium",
    "Multi-Family 2-4",
    "Multi-Family 5+",
    "Other Res.",
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
]
BuyerTransferPublicationWindow = Literal["Last 7 Days"]
BuyerTransferRecordingWindow = Literal["Last 30 Days"]

_KeyT = TypeVar("_KeyT")
_ValueT = TypeVar("_ValueT")

BUYER_TRANSFER_PROPERTY_FIELDS: tuple[BuyerTransferPropertyField, ...] = (
    "RadarID",
    "PType",
    "Address",
    "City",
    "State",
    "ZipFive",
    "County",
    "FIPS",
    "APN",
    "Latitude",
    "Longitude",
)
"""Ordered public fields requested for one buyer-transfer property match."""

_BUYER_TRANSFER_ENVELOPE_FIELDS = (
    "results",
    "totalCost",
    "quantityFreeRemaining",
    "resultCount",
    "totalResultCount",
)
_REQUIRED_ENVELOPE_FIELDS = (
    "results",
    "totalCost",
    "resultCount",
    "totalResultCount",
)
_BUYER_TRANSFER_CRITERION_ORDER = (
    "State",
    "County",
    "Buyer",
    "TransferPublishedDate",
    "TransferRecDate",
    "isMostRecentMarketTransfer",
    "RadarID",
)
_RELATIONSHIP: BuyerTransferLinkageRelationship = (
    "provider_buyer_criterion_property_match"
)
_PUBLICATION_WINDOW: BuyerTransferPublicationWindow = "Last 7 Days"
_RECORDING_WINDOW: BuyerTransferRecordingWindow = "Last 30 Days"
_STATE_CODE_PATTERN = re.compile(r"[A-Z]{2}")
_COUNTY_FIPS_PATTERN = re.compile(r"[0-9]{4,5}")
_FIPS_PATTERN = re.compile(r"[0-9]{4,5}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_TOTAL_COST_PATTERN_SOURCE = r"[0-9]+(?:\.[0-9]+)?"
_TOTAL_COST_PATTERN = re.compile(_TOTAL_COST_PATTERN_SOURCE)
_TOTAL_COST_MAX_LENGTH = 64
_PROPERTY_TYPES: tuple[BuyerTransferPropertyType, ...] = (
    "Single Family",
    "Condominium",
    "Multi-Family 2-4",
    "Multi-Family 5+",
    "Other Res.",
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
_RESIDENTIAL_PROPERTY_TYPES = frozenset(
    {
        "Single Family",
        "Condominium",
        "Multi-Family 2-4",
        "Multi-Family 5+",
        "Other Res.",
    }
)

_PROPERTY_FIELD_CONTRACT_SOURCE: dict[str, dict[str, object]] = {
    "RadarID": {"type": "string", "required": True},
    "PType": {
        "type": "string",
        "required": False,
        "values": _PROPERTY_TYPES,
    },
    "Address": {"type": "string", "required": False},
    "City": {"type": "string", "required": False},
    "State": {"type": "string", "required": False},
    "ZipFive": {
        "type": "integer",
        "required": False,
        "minimum": 0,
        "maximum": 99999,
    },
    "County": {"type": "string", "required": False},
    "FIPS": {
        "type": "string",
        "required": False,
        "pattern": _FIPS_PATTERN.pattern,
    },
    "APN": {"type": "string", "required": False},
    "Latitude": {
        "type": "number",
        "required": False,
        "minimum": "-90",
        "maximum": "90",
    },
    "Longitude": {
        "type": "number",
        "required": False,
        "minimum": "-180",
        "maximum": "180",
    },
}
_BILLING_CONTRACT_SOURCE: dict[str, object] = {
    "method_purchase_argument": {
        "type": "boolean",
        "preflight_before_network": True,
    },
    "purchase_requested": {
        "type": "boolean",
        "nullable": True,
        "response_echoed": False,
    },
    "status_values": ("preview", "charged", "unknown"),
    "total_cost": {
        "provider_source": "totalCost",
        "type": "decimal_string",
        "required_by_parser": True,
    },
    "currency": {"provider_source": None, "nullable": True},
    "quantity_free_remaining": {
        "provider_source": "quantityFreeRemaining",
        "preview_only": True,
    },
    "result_count": {"provider_source": "resultCount"},
    "total_result_count": {"provider_source": "totalResultCount"},
}
_PARSER_POLICY_SOURCE: dict[str, object] = {
    "required_envelope_fields": _REQUIRED_ENVELOPE_FIELDS,
    "reject_undocumented_envelope_fields": True,
    "reject_undocumented_property_fields": True,
    "exact_json_primitive_types": True,
    "snapshot_before_validation": ("envelope", "results", "property"),
    "maximum_result_count": 1,
    "result_count_must_equal_total": True,
    "returned_radar_id_must_equal_criterion": True,
    "returned_fips_must_equal_county_criterion": True,
    "missing_optional_fields": None,
    "preserve_provider_strings_exactly": True,
    "trim_or_coerce_provider_values": False,
}
_CONTRACT_FINGERPRINT_SOURCE: dict[str, object] = {
    "api_version": "5.2.0.0",
    "spec_source": "https://developers.propertyradar.com/_spec/api.json",
    "spec_source_sha256": (
        # pragma: allowlist nextline secret
        "f3808349c387cc1190ae41b24fec37962361b8149fde687179c84a72048e6bd4"
    ),
    "criteria_source": "https://developers.propertyradar.com/criteria_reference",
    "criteria_source_inspected_on": "2026-07-31",
    "criteria_help_source": (
        "https://help.propertyradar.com/en/articles/2507682-criteria-glossary-2007-2026"
    ),
    "operation": "properties.search",
    "method": "POST",
    "path": "/v1/properties",
    "relationship": _RELATIONSHIP,
    "buyer_criterion_semantics": "party_receiving_title_or_real_property_interest",
    "most_recent_change_of_ownership_semantics": (
        "most_recent_ownership_change_market_or_non_market"
    ),
    "criterion_order": _BUYER_TRANSFER_CRITERION_ORDER,
    "publication_window_values": (_PUBLICATION_WINDOW,),
    "recording_window_values": (_RECORDING_WINDOW,),
    "ordered_fields": BUYER_TRANSFER_PROPERTY_FIELDS,
    "property_fields": _PROPERTY_FIELD_CONTRACT_SOURCE,
    "envelope_fields": _BUYER_TRANSFER_ENVELOPE_FIELDS,
    "billing": _BILLING_CONTRACT_SOURCE,
    "parser_policy": _PARSER_POLICY_SOURCE,
    "provider_limitations": {
        "exact_name_match_semantics": None,
        "matched_transaction_identifier": None,
        "matched_structured_grantees": None,
        "transaction_party_boundaries": None,
        "scalar_grantor_grantee_parsing": False,
        "verification_decision": "caller_policy",
    },
}


def _fingerprint_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(cast(Mapping[str, object], value))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    return value


def _freeze_mapping(source: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {key: _freeze_value(value) for key, value in source.items()}
    )


BUYER_TRANSFER_MATCH_CONTRACT = _freeze_mapping(
    {
        **_CONTRACT_FINGERPRINT_SOURCE,
        "contract_fingerprint": _fingerprint_payload(_CONTRACT_FINGERPRINT_SOURCE),
    }
)
"""Deeply immutable buyer-transfer linkage and parser contract."""


@dataclass(frozen=True, slots=True, repr=False)
class BuyerTransferMatchCriteria:
    """Bounded criteria for linking one buyer/grantee query to one property."""

    buyer_name: str = field(repr=False)
    radar_id: str
    state_code: str
    county_fips: str
    publication_window: BuyerTransferPublicationWindow = _PUBLICATION_WINDOW
    recording_window: BuyerTransferRecordingWindow | None = None
    most_recent_change_of_ownership_only: bool = False

    def __post_init__(self) -> None:
        """Validate exact caller-normalized criteria and bounded windows."""
        _validate_buyer_name(self.buyer_name)
        if type(self.radar_id) is not str or not self.radar_id:
            raise ValueError("radar_id must be one nonempty string")
        if (
            type(self.state_code) is not str
            or _STATE_CODE_PATTERN.fullmatch(self.state_code) is None
        ):
            raise ValueError("state_code must be two uppercase letters")
        if (
            type(self.county_fips) is not str
            or _COUNTY_FIPS_PATTERN.fullmatch(self.county_fips) is None
        ):
            raise ValueError("county_fips must contain four or five digits")
        if self.publication_window != _PUBLICATION_WINDOW:
            raise ValueError("publication_window is not supported by this contract")
        if self.recording_window not in (None, _RECORDING_WINDOW):
            raise ValueError("recording_window is not supported by this contract")
        if type(self.most_recent_change_of_ownership_only) is not bool:
            raise ValueError("most_recent_change_of_ownership_only must be a boolean")

    def __repr__(self) -> str:
        """Return query-shape metadata without names or property identity."""
        return (
            f"{type(self).__name__}(buyer_name_available=True, "
            f"radar_id_available=True, state_code_available=True, "
            f"county_fips_available=True, "
            f"publication_window={self.publication_window!r}, "
            f"recording_window={self.recording_window!r}, "
            f"most_recent_change_of_ownership_only="
            f"{self.most_recent_change_of_ownership_only!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class BuyerTransferProperty:
    """One immutable property identity and location returned for the match."""

    returned_fields: tuple[BuyerTransferPropertyField, ...]
    radar_id: str
    property_type: BuyerTransferPropertyType | None
    address: str | None
    city: str | None
    state: str | None
    zip_five: int | None
    county: str | None
    fips: str | None
    apn: str | None
    latitude: Decimal | None
    longitude: Decimal | None

    def __post_init__(self) -> None:
        """Validate immutable field order and documented primitive shapes."""
        if type(self.returned_fields) is not tuple or any(
            field_name not in BUYER_TRANSFER_PROPERTY_FIELDS
            for field_name in self.returned_fields
        ):
            raise ValueError("returned_fields must be an immutable field tuple")
        if self.returned_fields != tuple(
            field_name
            for field_name in BUYER_TRANSFER_PROPERTY_FIELDS
            if field_name in self.returned_fields
        ):
            raise ValueError("returned_fields must preserve contract order")
        returned_field_set = set(self.returned_fields)
        if "RadarID" not in returned_field_set:
            raise ValueError("returned_fields must contain required RadarID")
        optional_availability = (
            ("PType", self.property_type),
            ("Address", self.address),
            ("City", self.city),
            ("State", self.state),
            ("ZipFive", self.zip_five),
            ("County", self.county),
            ("FIPS", self.fips),
            ("APN", self.apn),
            ("Latitude", self.latitude),
            ("Longitude", self.longitude),
        )
        if any(
            (field_name in returned_field_set) != (value is not None)
            for field_name, value in optional_availability
        ):
            raise ValueError(
                "returned_fields must agree with available property values"
            )
        if type(self.radar_id) is not str or not self.radar_id:
            raise ValueError("radar_id must be one nonempty string")
        if self.property_type is not None and self.property_type not in _PROPERTY_TYPES:
            raise ValueError("property_type is not a documented PType value")
        for field_name, value in (
            ("address", self.address),
            ("city", self.city),
            ("state", self.state),
            ("county", self.county),
            ("apn", self.apn),
        ):
            if value is not None and type(value) is not str:
                raise ValueError(f"{field_name} must be provider text or None")
        if self.zip_five is not None and (
            type(self.zip_five) is not int or not 0 <= self.zip_five <= 99999
        ):
            raise ValueError("zip_five must be an integer from 0 through 99999")
        if self.fips is not None and (
            type(self.fips) is not str or _FIPS_PATTERN.fullmatch(self.fips) is None
        ):
            raise ValueError("fips must contain four or five digits")
        _validate_coordinate(
            self.latitude,
            minimum=Decimal("-90"),
            maximum=Decimal("90"),
            field_name="latitude",
        )
        _validate_coordinate(
            self.longitude,
            minimum=Decimal("-180"),
            maximum=Decimal("180"),
            field_name="longitude",
        )

    @property
    def is_residential(self) -> bool | None:
        """Classify the documented broad property type without guessing Unknown."""
        if self.property_type in (None, "Unknown"):
            return None
        return self.property_type in _RESIDENTIAL_PROPERTY_TYPES

    def __repr__(self) -> str:
        """Return completeness metadata without property values."""
        return (
            f"{type(self).__name__}(returned_field_count={len(self.returned_fields)}, "
            f"property_type_available={self.property_type is not None!r}, "
            f"residential={self.is_residential!r}, "
            f"address_available={self.address is not None!r}, "
            f"city_available={self.city is not None!r}, "
            f"state_available={self.state is not None!r}, "
            f"zip_available={self.zip_five is not None!r}, "
            f"county_available={self.county is not None!r}, "
            f"parcel_available={self.apn is not None!r}, "
            f"coordinates_available="
            f"{self.latitude is not None and self.longitude is not None!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class BuyerTransferLinkage:
    """Provider evidence that one Buyer criterion returned one property."""

    scope_fingerprint: str
    property: BuyerTransferProperty
    relationship: BuyerTransferLinkageRelationship = _RELATIONSHIP
    matched_transaction_identifier: None = None
    matched_grantees: None = None

    def __post_init__(self) -> None:
        """Validate scope identity and explicit unavailable linkage fields."""
        if (
            type(self.scope_fingerprint) is not str
            or _SHA256_PATTERN.fullmatch(self.scope_fingerprint) is None
        ):
            raise ValueError("scope_fingerprint must be a SHA-256 value")
        if not isinstance(self.property, BuyerTransferProperty):
            raise ValueError("property must be BuyerTransferProperty")
        if self.relationship != _RELATIONSHIP:
            raise ValueError("relationship is not supported by this contract")
        if self.matched_transaction_identifier is not None:
            raise ValueError("matched_transaction_identifier is unavailable")
        if self.matched_grantees is not None:
            raise ValueError("matched_grantees are unavailable")

    def __repr__(self) -> str:
        """Return linkage shape without identity or fingerprint values."""
        return (
            f"{type(self).__name__}(relationship={self.relationship!r}, "
            f"property={self.property!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class BuyerTransferBillingEvidence:
    """Immutable billing evidence for one exact buyer-transfer search."""

    purchase_requested: bool | None
    status: BuyerTransferBillingStatus
    total_cost: Decimal
    currency: str | None
    quantity_free_remaining: int | None
    result_count: int
    total_result_count: int

    def __post_init__(self) -> None:
        """Validate billing state and exact-target result cardinality."""
        if (
            self.purchase_requested is not None
            and type(self.purchase_requested) is not bool
        ):
            raise ValueError("purchase_requested must be bool or None")
        expected_status = {False: "preview", True: "charged", None: "unknown"}[
            self.purchase_requested
        ]
        if self.status != expected_status:
            raise ValueError("status does not match purchase_requested")
        if (
            not isinstance(self.total_cost, Decimal)
            or not self.total_cost.is_finite()
            or self.total_cost < 0
        ):
            raise ValueError("total_cost must be a nonnegative finite Decimal")
        if self.currency is not None:
            raise ValueError("currency is unavailable under the current contract")
        for field_name, value in (
            ("result_count", self.result_count),
            ("total_result_count", self.total_result_count),
        ):
            if type(value) is not int or not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be zero or one")
        if self.result_count != self.total_result_count:
            raise ValueError("exact match counts must agree")
        if self.quantity_free_remaining is not None and (
            type(self.quantity_free_remaining) is not int
            or self.quantity_free_remaining < 0
        ):
            raise ValueError(
                "quantity_free_remaining must be a nonnegative integer or None"
            )
        if self.status == "charged" and self.quantity_free_remaining is not None:
            raise ValueError("charged evidence cannot include preview-only metadata")

    def __repr__(self) -> str:
        """Return non-personal billing metadata."""
        return (
            f"{type(self).__name__}(purchase_requested={self.purchase_requested!r}, "
            f"status={self.status!r}, total_cost={self.total_cost!r}, "
            f"quantity_free_remaining={self.quantity_free_remaining!r}, "
            f"result_count={self.result_count!r}, "
            f"total_result_count={self.total_result_count!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class BuyerTransferMatchResult:
    """One exact buyer/grantee criterion outcome and its billing evidence."""

    contract_fingerprint: str
    scope_fingerprint: str
    linkage: BuyerTransferLinkage | None
    billing: BuyerTransferBillingEvidence

    def __post_init__(self) -> None:
        """Bind the linkage and billing evidence to one public contract."""
        if (
            self.contract_fingerprint
            != BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"]
        ):
            raise ValueError("contract_fingerprint does not identify this contract")
        if (
            type(self.scope_fingerprint) is not str
            or _SHA256_PATTERN.fullmatch(self.scope_fingerprint) is None
        ):
            raise ValueError("scope_fingerprint must be a SHA-256 value")
        if self.linkage is not None and (
            not isinstance(self.linkage, BuyerTransferLinkage)
            or self.linkage.scope_fingerprint != self.scope_fingerprint
        ):
            raise ValueError("linkage must use the exact scope fingerprint")
        if not isinstance(self.billing, BuyerTransferBillingEvidence):
            raise ValueError("billing must be BuyerTransferBillingEvidence")
        if (self.linkage is None) != (self.billing.result_count == 0):
            raise ValueError("linkage presence must match the provider result count")

    @property
    def matched(self) -> bool:
        """Return whether the provider linked the Buyer criterion to a property."""
        return self.linkage is not None

    def __repr__(self) -> str:
        """Return outcome metadata without provider or person values."""
        return (
            f"{type(self).__name__}(matched={self.matched!r}, billing={self.billing!r})"
        )


def build_buyer_transfer_match_criteria(
    criteria: BuyerTransferMatchCriteria,
) -> tuple[Criterion, ...]:
    """Build the exact public PropertyRadar criteria for one property match."""
    if not isinstance(criteria, BuyerTransferMatchCriteria):
        raise TypeError("criteria must be BuyerTransferMatchCriteria")
    built: list[Criterion] = [
        {"name": "State", "value": [criteria.state_code]},
        {"name": "County", "value": [int(criteria.county_fips)]},
        {"name": "Buyer", "value": [criteria.buyer_name]},
        {"name": "TransferPublishedDate", "value": [criteria.publication_window]},
    ]
    if criteria.recording_window is not None:
        built.append({"name": "TransferRecDate", "value": [criteria.recording_window]})
    if criteria.most_recent_change_of_ownership_only:
        built.append({"name": "isMostRecentMarketTransfer", "value": [1]})
    built.append({"name": "RadarID", "value": [criteria.radar_id]})
    return tuple(built)


def buyer_transfer_scope_fingerprint(
    criteria: BuyerTransferMatchCriteria,
) -> str:
    """Return a stable digest of the exact bounded request scope."""
    built = build_buyer_transfer_match_criteria(criteria)
    return _fingerprint_payload(
        {
            "operation": "properties.search",
            "criteria": list(built),
            "fields": BUYER_TRANSFER_PROPERTY_FIELDS,
            "limit": 1,
            "start": 0,
        }
    )


def parse_buyer_transfer_match(
    envelope: Mapping[str, object],
    *,
    criteria: BuyerTransferMatchCriteria,
    purchase_requested: bool | None = None,
) -> BuyerTransferMatchResult:
    """Parse one exact Buyer-criterion property-search response.

    The linkage means only that PropertyRadar returned the exact property for
    its documented Buyer Name (Grantee) criterion and the supplied bounded
    windows. It does not invent a transaction identifier, exact-name matching
    semantics, or party boundaries.
    """
    if not isinstance(criteria, BuyerTransferMatchCriteria):
        _raise_invalid("criteria_type")
    if purchase_requested is not None and type(purchase_requested) is not bool:
        _raise_invalid("purchase_requested")
    typed_envelope = _snapshot_string_mapping(
        envelope,
        object_reason="envelope_type",
        snapshot_reason="envelope_snapshot",
        key_reason="envelope_key_type",
    )
    envelope_keys = set(typed_envelope)
    if not set(_REQUIRED_ENVELOPE_FIELDS).issubset(envelope_keys):
        _raise_invalid("required_envelope_fields")
    if envelope_keys.difference(_BUYER_TRANSFER_ENVELOPE_FIELDS):
        _raise_invalid("undocumented_envelope_fields")

    raw_results = typed_envelope["results"]
    if not isinstance(raw_results, list):
        _raise_invalid("results_type")
    result_snapshots = tuple(
        _snapshot_string_mapping(
            item,
            object_reason="property_type",
            snapshot_reason="property_snapshot",
            key_reason="property_key_type",
        )
        for item in tuple(list.copy(raw_results))
    )
    if len(result_snapshots) > 1:
        _raise_invalid("ambiguous_results")
    result_count = _parse_match_count(
        typed_envelope["resultCount"], field_name="result_count"
    )
    total_result_count = _parse_match_count(
        typed_envelope["totalResultCount"], field_name="total_result_count"
    )
    if result_count != len(result_snapshots):
        _raise_invalid("result_count_mismatch")
    if result_count != total_result_count:
        _raise_invalid("ambiguous_total_result_count")

    quantity_free_remaining = None
    if "quantityFreeRemaining" in typed_envelope:
        quantity_free_remaining = _parse_nonnegative_integer(
            typed_envelope["quantityFreeRemaining"],
            field_name="quantity_free_remaining",
        )
    if purchase_requested is True and quantity_free_remaining is not None:
        _raise_invalid("charged_preview_metadata")

    scope_fingerprint = buyer_transfer_scope_fingerprint(criteria)
    linkage = None
    if result_snapshots:
        property_result = _parse_property(
            result_snapshots[0],
            expected_radar_id=criteria.radar_id,
            expected_county_fips=criteria.county_fips,
        )
        linkage = BuyerTransferLinkage(
            scope_fingerprint=scope_fingerprint,
            property=property_result,
        )

    billing_status: BuyerTransferBillingStatus
    if purchase_requested is None:
        billing_status = "unknown"
    elif purchase_requested:
        billing_status = "charged"
    else:
        billing_status = "preview"
    return BuyerTransferMatchResult(
        contract_fingerprint=cast(
            str, BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"]
        ),
        scope_fingerprint=scope_fingerprint,
        linkage=linkage,
        billing=BuyerTransferBillingEvidence(
            purchase_requested=purchase_requested,
            status=billing_status,
            total_cost=_parse_total_cost(typed_envelope["totalCost"]),
            currency=None,
            quantity_free_remaining=quantity_free_remaining,
            result_count=result_count,
            total_result_count=total_result_count,
        ),
    )


def _parse_property(
    record: Mapping[str, object],
    *,
    expected_radar_id: str,
    expected_county_fips: str,
) -> BuyerTransferProperty:
    if set(record).difference(BUYER_TRANSFER_PROPERTY_FIELDS):
        _raise_invalid("undocumented_property_fields")
    if "RadarID" not in record:
        _raise_invalid("missing_radar_id")
    radar_id = _parse_required_provider_text(record["RadarID"], field_name="radar_id")
    if radar_id != expected_radar_id:
        _raise_invalid("radar_id_mismatch")
    fips = _parse_optional_fips(record)
    if fips is not None and int(fips) != int(expected_county_fips):
        _raise_invalid("fips_mismatch")
    return BuyerTransferProperty(
        returned_fields=tuple(
            field_name
            for field_name in BUYER_TRANSFER_PROPERTY_FIELDS
            if field_name in record
        ),
        radar_id=radar_id,
        property_type=_parse_optional_property_type(record),
        address=_parse_optional_provider_text(record, "Address"),
        city=_parse_optional_provider_text(record, "City"),
        state=_parse_optional_provider_text(record, "State"),
        zip_five=_parse_optional_zip(record),
        county=_parse_optional_provider_text(record, "County"),
        fips=fips,
        apn=_parse_optional_provider_text(record, "APN"),
        latitude=_parse_optional_coordinate(
            record,
            "Latitude",
            minimum=Decimal("-90"),
            maximum=Decimal("90"),
        ),
        longitude=_parse_optional_coordinate(
            record,
            "Longitude",
            minimum=Decimal("-180"),
            maximum=Decimal("180"),
        ),
    )


def _validate_buyer_name(value: object) -> None:
    if type(value) is not str:
        raise ValueError("buyer_name must be a bounded printable string")
    if not value or not value.isprintable() or value != " ".join(value.split()):
        raise ValueError("buyer_name must be one normalized printable string")


def _validate_coordinate(
    value: Decimal | None,
    *,
    minimum: Decimal,
    maximum: Decimal,
    field_name: str,
) -> None:
    if value is None:
        return
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{field_name} must be a bounded finite Decimal or None")


def _snapshot_mapping(
    source: Mapping[_KeyT, _ValueT], *, reason: str
) -> dict[_KeyT, _ValueT]:
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
    if not isinstance(source, Mapping):
        _raise_invalid(object_reason)
    snapshot = _snapshot_mapping(source, reason=snapshot_reason)
    if any(type(key) is not str for key in tuple(snapshot)):
        _raise_invalid(key_reason)
    return cast(dict[str, object], snapshot)


def _parse_required_provider_text(value: object, *, field_name: str) -> str:
    if type(value) is not str or not value:
        _raise_invalid(field_name)
    return value


def _parse_optional_provider_text(
    record: Mapping[str, object], field_name: str
) -> str | None:
    if field_name not in record:
        return None
    value = record[field_name]
    if type(value) is not str:
        _raise_invalid(field_name.lower())
    return value


def _parse_optional_property_type(
    record: Mapping[str, object],
) -> BuyerTransferPropertyType | None:
    if "PType" not in record:
        return None
    value = record["PType"]
    if type(value) is not str or value not in _PROPERTY_TYPES:
        _raise_invalid("property_type")
    return value


def _parse_optional_zip(record: Mapping[str, object]) -> int | None:
    if "ZipFive" not in record:
        return None
    value = record["ZipFive"]
    if type(value) is not int or not 0 <= value <= 99999:
        _raise_invalid("zip_five")
    return value


def _parse_optional_fips(record: Mapping[str, object]) -> str | None:
    if "FIPS" not in record:
        return None
    value = record["FIPS"]
    if type(value) is not str or _FIPS_PATTERN.fullmatch(value) is None:
        _raise_invalid("fips")
    return value


def _parse_optional_coordinate(
    record: Mapping[str, object],
    field_name: Literal["Latitude", "Longitude"],
    *,
    minimum: Decimal,
    maximum: Decimal,
) -> Decimal | None:
    if field_name not in record:
        return None
    value = record[field_name]
    if type(value) not in (int, float) or (
        type(value) is float and not math.isfinite(value)
    ):
        _raise_invalid(field_name.lower())
    parsed = Decimal(str(value))
    if not minimum <= parsed <= maximum:
        _raise_invalid(field_name.lower())
    return parsed


def _parse_match_count(value: object, *, field_name: str) -> int:
    parsed = _parse_nonnegative_integer(value, field_name=field_name)
    if parsed > 1:
        _raise_invalid(field_name)
    return parsed


def _parse_nonnegative_integer(value: object, *, field_name: str) -> int:
    if type(value) is not int or value < 0:
        _raise_invalid(field_name)
    return value


def _parse_total_cost(value: object) -> Decimal:
    if (
        type(value) is not str
        or len(value) > _TOTAL_COST_MAX_LENGTH
        or _TOTAL_COST_PATTERN.fullmatch(value) is None
    ):
        _raise_invalid("total_cost")
    return Decimal(value)


def _raise_invalid(reason: str) -> NoReturn:
    raise InvalidResponseError(
        f"PropertyRadar returned invalid buyer-transfer match ({reason})."
    ) from None
