"""Typed buyer/grantee search linkage with immutable property location.

Only a non-billable ``Purchase=0`` preview carries the residential
PropertyType criterion. That criterion follows the official API reference and
has not been live-probed on ``Purchase=0``. A preview's ``matched=False`` also
covers a non-residential or Unknown transfer that the provider dropped under
the criterion. A paid ``Purchase=1`` request carries no PropertyType
criterion, and a paid result classifies the property from the returned PType.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
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
BuyerTransferResidentialBasis = Literal["property_type", "property_type_criterion"]

_KeyT = TypeVar("_KeyT")
_ValueT = TypeVar("_ValueT")
_RecordT = TypeVar("_RecordT")

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
"""Ordered public fields requested for one purchased buyer-transfer match."""

BUYER_TRANSFER_PREVIEW_FIELDS: tuple[BuyerTransferPropertyField, ...] = ("RadarID",)
"""Fields requested by a non-billable ``Purchase=0`` buyer-transfer preview.

RadarID is the only free field of a ``Purchase=0`` property search. Requesting
any other field of ``BUYER_TRANSFER_PROPERTY_FIELDS`` makes the preview return
no record.
"""

BUYER_TRANSFER_RESIDENTIAL_PTYPE_CODES: tuple[str, ...] = (
    "SFR",
    "CND",
    "MFR",
    "APT",
    "RES",
)
"""Official PType codes of the PropertyType criterion on every preview request.

The codes map, in order, to the residential response PType names Single
Family, Condominium, Multi-Family 2-4, Multi-Family 5+ and Other Res. A paid
``Purchase=1`` request carries no PropertyType criterion.
"""

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
_BUYER_TRANSFER_PREVIEW_CRITERION_ORDER = (
    *_BUYER_TRANSFER_CRITERION_ORDER[:-1],
    "PropertyType",
    "RadarID",
)
_BARE_PREVIEW_ENVELOPE_FIELDS = ("results",)
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
_TOTAL_COST_INTEGER_LIMIT = 10**_TOTAL_COST_MAX_LENGTH
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
_PROPERTY_TYPE_CODES = (
    "SFR",
    "CND",
    "MFR",
    "APT",
    "RES",
    "COM",
    "IND",
    "AGR",
    "LND",
    "GOV",
    "REC",
    "TRA",
    "UTL",
    "OTH",
    "UNK",
)
_PROPERTY_TYPE_CODE_NAMES: dict[str, BuyerTransferPropertyType] = dict(
    zip(_PROPERTY_TYPE_CODES, _PROPERTY_TYPES, strict=True)
)
_RESIDENTIAL_PROPERTY_TYPE_CODE_NAMES: dict[str, BuyerTransferPropertyType] = {
    code: _PROPERTY_TYPE_CODE_NAMES[code]
    for code in BUYER_TRANSFER_RESIDENTIAL_PTYPE_CODES
}
_RESIDENTIAL_PROPERTY_TYPES = frozenset(_RESIDENTIAL_PROPERTY_TYPE_CODE_NAMES.values())
_RESIDENTIAL_BASES: tuple[BuyerTransferResidentialBasis, ...] = (
    "property_type",
    "property_type_criterion",
)
_PREVIEW_PROPERTY_TYPE_CRITERION: Criterion = {
    "name": "PropertyType",
    "value": [{"name": "PType", "value": list(BUYER_TRANSFER_RESIDENTIAL_PTYPE_CODES)}],
}
_PROPERTY_TYPE_CRITERION_SOURCE: dict[str, object] = {
    "criterion": "PropertyType",
    "subcriterion": "PType",
    "codes": BUYER_TRANSFER_RESIDENTIAL_PTYPE_CODES,
    "code_property_types": _RESIDENTIAL_PROPERTY_TYPE_CODE_NAMES,
    "documented_codes": _PROPERTY_TYPE_CODES,
    "documented_property_types": _PROPERTY_TYPES,
    "code_order_matches_property_type_order": True,
    "shape": _PREVIEW_PROPERTY_TYPE_CRITERION,
    "position": "immediately_before_radar_id",
    "requests": ("preview",),
    "evidence": {
        "codes_source": "spec_query_parameter_PType_enum",
        "codes_source_operations": (
            "GET /v1/properties/{RadarID}/comps/sales",
            "GET /v1/properties/{RadarID}/comps/forsale",
            "GET /v1/lists/{ListID}/items",
        ),
        "property_types_source": "spec_POST_v1_properties_results_PType_enum",
        "spec_api_version": "5.3.1.0",
        "spec_source_sha256": (
            # pragma: allowlist nextline secret
            "9feadf6a8fade0530045f4d6f14db69f520144078a71637ef6c999aea8493c14"
        ),
        "shape_source": "https://developers.propertyradar.com/criteria",
        "shape_source_inspected_on": "2026-11-03",
    },
    "purchase_0_live_probed": False,
}

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
        "accepted_json_types": ("string", "integer", "number"),
        "string": {
            "pattern": _TOTAL_COST_PATTERN_SOURCE,
            "maximum_length": _TOTAL_COST_MAX_LENGTH,
        },
        "integer": {
            "exact_type": "int",
            "boolean_rejected": True,
            "minimum": 0,
            "maximum_digits": _TOTAL_COST_MAX_LENGTH,
        },
        "number": {
            "exact_type": "float",
            "finite": True,
            "negative_zero_rejected": True,
            "minimum": 0,
            "conversion": "Decimal(repr(value))",
            "plain_form_pattern": _TOTAL_COST_PATTERN_SOURCE,
            "plain_form_maximum_length": _TOTAL_COST_MAX_LENGTH,
        },
        "rejected": (
            "boolean",
            "null",
            "nan",
            "infinity",
            "negative",
            "over_long",
            "other_types",
        ),
        "parsed_type": "Decimal",
        "required_by_parser": True,
        "bare_preview_value": "0",
    },
    "currency": {"provider_source": None, "nullable": True},
    "quantity_free_remaining": {
        "provider_source": "quantityFreeRemaining",
        "preview_only": True,
    },
    "result_count": {
        "provider_source": "resultCount",
        "preview_meaning": "purchased_rows",
    },
    "total_result_count": {
        "provider_source": "totalResultCount",
        "preview_meaning": "matches",
    },
    "provider_metadata_omitted": {
        "type": "boolean",
        "default": False,
        "true_only_for": "bare_preview_envelope",
    },
    "purchase_0_billable": False,
}
_PARSER_POLICY_SOURCE: dict[str, object] = {
    "required_envelope_fields": _REQUIRED_ENVELOPE_FIELDS,
    "bare_preview_envelope": {
        "purchase_requested": False,
        "fields": _BARE_PREVIEW_ENVELOPE_FIELDS,
        "results": "empty_list",
        "matched": False,
        "status": "preview",
        "total_cost": "0",
        "currency": None,
        "quantity_free_remaining": None,
        "result_count": 0,
        "total_result_count": 0,
        "provider_metadata_omitted": True,
        "charged_or_unknown_reason": "required_envelope_fields",
    },
    "reject_undocumented_envelope_fields": True,
    "reject_undocumented_property_fields": True,
    "exact_json_primitive_types": True,
    "snapshot_before_validation": ("envelope", "results", "property"),
    "maximum_result_count": 1,
    "count_rules": {
        "charged_or_unknown": "result_count_equals_results_length_equals_total",
        "preview": {
            "total_result_count_values": (0, 1),
            "results_length_must_equal_total_result_count": True,
            "result_count_values": ("zero", "results_length"),
            "withheld_record_reason": "preview_record_withheld",
            "linkage_follows": "returned_record",
        },
    },
    "returned_radar_id_must_equal_criterion": True,
    "returned_fips_must_equal_county_criterion": True,
    "returned_property_type_must_be_within_criterion": {
        "preview": True,
        "charged_or_unknown": False,
    },
    "residential_classification": {
        "preview": {
            "property_type_returned": {
                "residential_basis": "property_type",
                "allowed_values": tuple(_RESIDENTIAL_PROPERTY_TYPE_CODE_NAMES.values()),
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
                "residential_values": tuple(
                    _RESIDENTIAL_PROPERTY_TYPE_CODE_NAMES.values()
                ),
                "non_residential_values": tuple(
                    property_type
                    for property_type in _PROPERTY_TYPES
                    if property_type not in (*_RESIDENTIAL_PROPERTY_TYPES, "Unknown")
                ),
                "unknown_values": ("Unknown",),
                "outside_criterion_reason": None,
            },
            "property_type_not_returned": {
                "residential_basis": None,
                "is_residential": None,
            },
        },
    },
    "failure_billing_evidence": {
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
        "record_rejection_reasons": (
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
        ),
        "earlier_rejection_type": "InvalidResponseError",
        "message": "reason_code_only",
    },
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
    "preview_criterion_order": _BUYER_TRANSFER_PREVIEW_CRITERION_ORDER,
    "publication_window_values": (_PUBLICATION_WINDOW,),
    "recording_window_values": (_RECORDING_WINDOW,),
    "ordered_fields": BUYER_TRANSFER_PROPERTY_FIELDS,
    "preview_fields": BUYER_TRANSFER_PREVIEW_FIELDS,
    "preview_fields_evidence": (
        "spec_POST_v1_properties_Purchase_parameter_radar_id_only_not_charged"
    ),
    "property_type_criterion": _PROPERTY_TYPE_CRITERION_SOURCE,
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


_HISTORICAL_CONTRACT_FINGERPRINT_SOURCE: dict[str, object] = {
    **_CONTRACT_FINGERPRINT_SOURCE,
    "api_version": "5.3.1.0",
    "spec_source_sha256": (
        # pragma: allowlist nextline secret
        "9feadf6a8fade0530045f4d6f14db69f520144078a71637ef6c999aea8493c14"
    ),
    "contract_version": 1,
    "mode": "historical_recording_range",
    "criteria_source_inspected_on": "2026-11-03",
    "criteria_syntax_source": "https://developers.propertyradar.com/criteria",
    "criterion_order": tuple(
        name
        for name in _BUYER_TRANSFER_CRITERION_ORDER
        if name != "TransferPublishedDate"
    ),
    "preview_criterion_order": tuple(
        name
        for name in _BUYER_TRANSFER_PREVIEW_CRITERION_ORDER
        if name != "TransferPublishedDate"
    ),
    "publication_window_values": (),
    "recording_window_values": (),
    "property_fields": {
        **_PROPERTY_FIELD_CONTRACT_SOURCE,
        "ZipFive": {
            "type": "string",
            "required": False,
            "pattern": "^[0-9]{5}$",
        },
    },
    "envelope_fields": (
        *_BUYER_TRANSFER_ENVELOPE_FIELDS,
        "maxDistanceMiles",
        "nextPageToken",
        "facets",
    ),
    "parser_policy": {
        **_PARSER_POLICY_SOURCE,
        "result_type": "HistoricalBuyerTransferMatchResult",
        "optional_metadata": {
            "maxDistanceMiles": {"type": "integer", "minimum": 0, "maximum": 250},
            "nextPageToken": {"type": "string", "allowed_value": ""},
            "facets": {"type": "object", "allowed_value": {}},
        },
        "retain_optional_metadata": False,
        "pagination": False,
    },
    "recording_date_range": {
        "criterion": "TransferRecDate",
        "boundary_type": "date",
        "inclusive": True,
        "minimum_date": date.min.isoformat(),
        "maximum_date": date.max.isoformat(),
        "span_limit": "caller_authorization_policy",
        "format": "from: M/D/YYYY to: M/D/YYYY",
        "open_ended": False,
    },
    "scope_fingerprint_policy": "bind_mode_contract_and_recording_boundaries",
}
BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT = _freeze_mapping(
    {
        **_HISTORICAL_CONTRACT_FINGERPRINT_SOURCE,
        "contract_fingerprint": _fingerprint_payload(
            _HISTORICAL_CONTRACT_FINGERPRINT_SOURCE
        ),
    }
)
"""Versioned historical request and strict API 5.3.1.0 response contract."""


@dataclass(frozen=True, slots=True, repr=False)
class BuyerTransferRecordingDateRange:
    """An inclusive finite recording-date range subject to caller authorization."""

    start: date
    end: date

    def __post_init__(self) -> None:
        """Reject open, non-date, and reversed ranges."""
        if type(self.start) is not date or type(self.end) is not date:
            raise ValueError("recording range boundaries must be exact date objects")
        if self.start > self.end:
            raise ValueError("recording range start must not follow end")

    def __repr__(self) -> str:
        """Describe the range without exposing recording dates."""
        return f"{type(self).__name__}(bounded=True)"


@dataclass(frozen=True, slots=True, repr=False)
class BuyerTransferMatchCriteria:
    """Bounded criteria for linking one buyer/grantee query to one property."""

    buyer_name: str = field(repr=False)
    radar_id: str
    state_code: str
    county_fips: str
    publication_window: BuyerTransferPublicationWindow | None = _PUBLICATION_WINDOW
    recording_window: BuyerTransferRecordingWindow | None = None
    most_recent_change_of_ownership_only: bool = False
    recording_date_range: BuyerTransferRecordingDateRange | None = field(
        default=None, kw_only=True
    )

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
        if self.recording_date_range is None:
            if self.publication_window != _PUBLICATION_WINDOW:
                raise ValueError("publication_window is not supported by this contract")
            if self.recording_window not in (None, _RECORDING_WINDOW):
                raise ValueError("recording_window is not supported by this contract")
        else:
            if type(self.recording_date_range) is not BuyerTransferRecordingDateRange:
                raise ValueError(
                    "recording_date_range must be BuyerTransferRecordingDateRange"
                )
            if self.publication_window is not None:
                raise ValueError("historical criteria require publication_window=None")
            if self.recording_window is not None:
                raise ValueError("historical criteria require recording_window=None")
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
            f"{self.most_recent_change_of_ownership_only!r}"
            + (
                ", recording_date_range_available=True)"
                if self.recording_date_range is not None
                else ")"
            )
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
    residential_basis: BuyerTransferResidentialBasis | None = field(
        default=None, kw_only=True
    )

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
        _validate_residential_basis(self.residential_basis, self.property_type)

    @property
    def is_residential(self) -> bool | None:
        """Classify residential use from PType or the preview's type criterion.

        A preview record matched under the residential PropertyType criterion
        without a returned PType is residential. That criterion follows the
        official API reference and has not been live-probed on ``Purchase=0``,
        and a preview's ``matched=False`` also covers a non-residential or
        Unknown transfer that the provider dropped under it. A paid or unknown
        result classifies the property from the returned PType: the documented
        broad property type decides, and Unknown or a missing PType stays
        unknown.
        """
        return _classify_residential(self.property_type, self.residential_basis)

    def __repr__(self) -> str:
        """Return completeness metadata without property values."""
        return (
            f"{type(self).__name__}(returned_field_count={len(self.returned_fields)}, "
            f"property_type_available={self.property_type is not None!r}, "
            f"residential={self.is_residential!r}, "
            f"residential_basis={self.residential_basis!r}, "
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
    provider_metadata_omitted: bool = field(default=False, kw_only=True)

    def __post_init__(self) -> None:
        """Validate billing state and exact-target result cardinality.

        In a preview, ``result_count`` counts purchased rows (zero, or the
        returned record) while ``total_result_count`` counts matches. Charged
        and unknown evidence keeps both counts equal.
        """
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
        if self.status == "preview":
            if self.result_count not in (0, self.total_result_count):
                raise ValueError(
                    "preview result counts must be zero or equal the match count"
                )
        elif self.result_count != self.total_result_count:
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
        if type(self.provider_metadata_omitted) is not bool:
            raise ValueError("provider_metadata_omitted must be a boolean")
        if self.provider_metadata_omitted and (
            self.status != "preview"
            or self.total_cost != 0
            or self.quantity_free_remaining is not None
            or self.total_result_count != 0
        ):
            raise ValueError(
                "provider_metadata_omitted requires an empty zero-cost preview"
            )

    def __repr__(self) -> str:
        """Return non-personal billing metadata."""
        return (
            f"{type(self).__name__}(purchase_requested={self.purchase_requested!r}, "
            f"status={self.status!r}, total_cost={self.total_cost!r}, "
            f"quantity_free_remaining={self.quantity_free_remaining!r}, "
            f"result_count={self.result_count!r}, "
            f"total_result_count={self.total_result_count!r}, "
            f"provider_metadata_omitted={self.provider_metadata_omitted!r})"
        )


class BuyerTransferResponseError(InvalidResponseError):
    """A rejected buyer-transfer record with valid, privacy-safe billing data.

    Both buyer-transfer parsers raise it for every rejection of the returned
    record. They validate the envelope, the counts and ``totalCost`` first, so
    ``billing_evidence`` keeps the cost and counts of a charged request. The
    message holds only the reason code.
    """

    def __init__(
        self, message: str, *, billing_evidence: BuyerTransferBillingEvidence
    ) -> None:
        """Attach immutable billing evidence without retaining the response."""
        super().__init__(message)
        self.billing_evidence = billing_evidence


@dataclass(frozen=True, slots=True, repr=False)
class BuyerTransferMatchResult:
    """One exact buyer/grantee criterion outcome and its billing evidence.

    A preview's ``matched=False`` also covers a non-residential or Unknown
    transfer that the provider dropped under the preview's residential
    PropertyType criterion. That criterion follows the official API reference
    and has not been live-probed on ``Purchase=0``. A paid result classifies
    the property from the returned PType.
    """

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
        if (self.linkage is not None) != _billing_returns_record(self.billing):
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


def _billing_returns_record(billing: BuyerTransferBillingEvidence) -> bool:
    """Return whether validated billing evidence implies one returned record.

    A preview returns its matched record without counting it as purchased, so
    the match count decides. Charged and unknown evidence keeps the purchased
    result count equal to the match count.
    """
    if billing.status == "preview":
        return billing.total_result_count == 1
    return billing.result_count == 1


def build_buyer_transfer_match_criteria(
    criteria: BuyerTransferMatchCriteria,
    *,
    preview: bool = False,
) -> tuple[Criterion, ...]:
    """Build the exact public PropertyRadar criteria for one property match.

    The default builds the criteria of a paid ``Purchase=1`` request, the
    0.4.1 list with the exact RadarID criterion last. A paid result classifies
    the property from the returned PType.

    With ``preview=True`` the non-billable ``Purchase=0`` preview also
    restricts the match to residential property types with the official
    PropertyType criterion, placed just before RadarID, which stays last. That
    criterion follows the official API reference and has not been live-probed
    on ``Purchase=0``. So a preview's ``matched=False`` also covers a
    non-residential or Unknown transfer that the provider dropped under it.

    Raises:
        TypeError: If ``criteria`` is not ``BuyerTransferMatchCriteria`` or
            ``preview`` is not exactly a boolean.
    """
    if not isinstance(criteria, BuyerTransferMatchCriteria):
        raise TypeError("criteria must be BuyerTransferMatchCriteria")
    if type(preview) is not bool:
        raise TypeError("preview must be a boolean")
    built: list[Criterion] = [
        {"name": "State", "value": [criteria.state_code]},
        {"name": "County", "value": [int(criteria.county_fips)]},
        {"name": "Buyer", "value": [criteria.buyer_name]},
    ]
    if criteria.recording_date_range is not None:
        start = criteria.recording_date_range.start
        end = criteria.recording_date_range.end
        built.append(
            {
                "name": "TransferRecDate",
                "value": [
                    f"from: {start.month}/{start.day}/{start.year:04d} "
                    f"to: {end.month}/{end.day}/{end.year:04d}"
                ],
            }
        )
    else:
        built.append(
            {"name": "TransferPublishedDate", "value": [criteria.publication_window]}
        )
    if criteria.recording_window is not None:
        built.append({"name": "TransferRecDate", "value": [criteria.recording_window]})
    if criteria.most_recent_change_of_ownership_only:
        built.append({"name": "isMostRecentMarketTransfer", "value": [1]})
    if preview:
        built.append(copy.deepcopy(_PREVIEW_PROPERTY_TYPE_CRITERION))
    built.append({"name": "RadarID", "value": [criteria.radar_id]})
    return tuple(built)


def buyer_transfer_scope_fingerprint(
    criteria: BuyerTransferMatchCriteria,
) -> str:
    """Return a stable digest of the exact bounded request scope.

    The digest binds the paid request's criteria, the preview's PropertyType
    criterion under a key of its own and both constant field sets, so the
    preview and the purchased parse of the same criteria share one value.
    """
    built = build_buyer_transfer_match_criteria(criteria)
    scope: dict[str, object] = {
        "operation": "properties.search",
        "criteria": list(built),
        "preview_property_type_criterion": _PREVIEW_PROPERTY_TYPE_CRITERION,
        "fields": BUYER_TRANSFER_PROPERTY_FIELDS,
        "preview_fields": BUYER_TRANSFER_PREVIEW_FIELDS,
        "limit": 1,
        "start": 0,
    }
    if criteria.recording_date_range is not None:
        scope.update(
            mode="historical_recording_range",
            contract_fingerprint=(
                BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT["contract_fingerprint"]
            ),
            recording_date_range={
                "start": criteria.recording_date_range.start.isoformat(),
                "end": criteria.recording_date_range.end.isoformat(),
            },
        )
    return _fingerprint_payload(scope)


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

    With ``purchase_requested=False`` the parser also accepts the provider's
    bare zero-hit preview ``{"results": []}`` and preview counts, where
    ``resultCount`` counts purchased rows and ``totalResultCount`` counts
    matches. Charged and unknown parses keep the exact count rule.

    A preview carries the residential PropertyType criterion, which follows
    the official API reference and has not been live-probed on
    ``Purchase=0``. A returned preview PType must be residential, and a
    preview's ``matched=False`` also covers a non-residential or Unknown
    transfer that the provider dropped under the criterion. A paid or unknown
    parse classifies the property from the returned PType alone.

    Raises:
        BuyerTransferResponseError: If the returned record is rejected after
            the envelope, the counts and ``totalCost`` were validated. Its
            ``billing_evidence`` carries that cost and those counts.
        InvalidResponseError: If any earlier part of the response or an
            argument violates the contract.
    """
    if not isinstance(criteria, BuyerTransferMatchCriteria):
        _raise_invalid("criteria_type")
    if criteria.recording_date_range is not None:
        _raise_invalid("historical_criteria_requires_historical_parser")
    if purchase_requested is not None and type(purchase_requested) is not bool:
        _raise_invalid("purchase_requested")
    typed_envelope = _snapshot_string_mapping(
        envelope,
        object_reason="envelope_type",
        snapshot_reason="envelope_snapshot",
        key_reason="envelope_key_type",
    )
    if _is_bare_preview_envelope(typed_envelope, purchase_requested=purchase_requested):
        return BuyerTransferMatchResult(
            contract_fingerprint=cast(
                str, BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"]
            ),
            scope_fingerprint=buyer_transfer_scope_fingerprint(criteria),
            linkage=None,
            billing=_bare_preview_billing(),
        )
    envelope_keys = set(typed_envelope)
    if not set(_REQUIRED_ENVELOPE_FIELDS).issubset(envelope_keys):
        _raise_invalid("required_envelope_fields")
    if envelope_keys.difference(_BUYER_TRANSFER_ENVELOPE_FIELDS):
        _raise_invalid("undocumented_envelope_fields")

    raw_results = typed_envelope["results"]
    if not isinstance(raw_results, list):
        _raise_invalid("results_type")
    raw_records = tuple(list.copy(raw_results))
    billing = _parse_match_billing(
        typed_envelope,
        returned_count=len(raw_records),
        purchase_requested=purchase_requested,
    )

    scope_fingerprint = buyer_transfer_scope_fingerprint(criteria)
    linkage = None
    if raw_records:
        property_result = _parse_billed_record(
            raw_records[0],
            lambda record: _parse_property(
                record,
                expected_radar_id=criteria.radar_id,
                expected_county_fips=criteria.county_fips,
                purchase_requested=purchase_requested,
            ),
            billing_evidence=billing,
        )
        linkage = BuyerTransferLinkage(
            scope_fingerprint=scope_fingerprint,
            property=property_result,
        )

    return BuyerTransferMatchResult(
        contract_fingerprint=cast(
            str, BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"]
        ),
        scope_fingerprint=scope_fingerprint,
        linkage=linkage,
        billing=billing,
    )


def _parse_match_billing(
    envelope: Mapping[str, object],
    *,
    returned_count: int,
    purchase_requested: bool | None,
) -> BuyerTransferBillingEvidence:
    """Validate the counts, preview metadata and ``totalCost`` before the record.

    No billing evidence exists yet, so each rejection here stays a plain
    ``InvalidResponseError``.
    """
    if returned_count > 1:
        _raise_invalid("ambiguous_results")
    result_count = _parse_match_count(
        envelope["resultCount"], field_name="result_count"
    )
    total_result_count = _parse_match_count(
        envelope["totalResultCount"], field_name="total_result_count"
    )
    _validate_match_counts(
        returned_count=returned_count,
        result_count=result_count,
        total_result_count=total_result_count,
        purchase_requested=purchase_requested,
    )
    quantity_free_remaining = None
    if "quantityFreeRemaining" in envelope:
        quantity_free_remaining = _parse_nonnegative_integer(
            envelope["quantityFreeRemaining"],
            field_name="quantity_free_remaining",
        )
    if purchase_requested is True and quantity_free_remaining is not None:
        _raise_invalid("charged_preview_metadata")
    return BuyerTransferBillingEvidence(
        purchase_requested=purchase_requested,
        status=_billing_status(purchase_requested),
        total_cost=_parse_total_cost(envelope["totalCost"]),
        currency=None,
        quantity_free_remaining=quantity_free_remaining,
        result_count=result_count,
        total_result_count=total_result_count,
    )


def _parse_billed_record(
    raw_record: object,
    parse: Callable[[Mapping[str, object]], _RecordT],
    *,
    billing_evidence: BuyerTransferBillingEvidence,
) -> _RecordT:
    """Snapshot and parse the returned record after billing was validated.

    A rejection keeps its exact reason-code message and is raised again as
    ``BuyerTransferResponseError`` with the billing evidence, outside the
    handler, so the new error has no context.
    """
    try:
        return parse(
            _snapshot_string_mapping(
                raw_record,
                object_reason="property_type",
                snapshot_reason="property_snapshot",
                key_reason="property_key_type",
            )
        )
    except InvalidResponseError as error:
        message = str(error)
    _raise_billed_invalid(message, billing_evidence)


def _is_bare_preview_envelope(
    envelope: Mapping[str, object], *, purchase_requested: bool | None
) -> bool:
    """Return whether a preview omitted all metadata around empty results."""
    if purchase_requested is not False or set(envelope) != set(
        _BARE_PREVIEW_ENVELOPE_FIELDS
    ):
        return False
    raw_results = envelope["results"]
    return isinstance(raw_results, list) and not list.copy(raw_results)


def _bare_preview_billing() -> BuyerTransferBillingEvidence:
    """Return the non-billable evidence of a bare zero-hit preview."""
    return BuyerTransferBillingEvidence(
        purchase_requested=False,
        status="preview",
        total_cost=Decimal("0"),
        currency=None,
        quantity_free_remaining=None,
        result_count=0,
        total_result_count=0,
        provider_metadata_omitted=True,
    )


def _billing_status(purchase_requested: bool | None) -> BuyerTransferBillingStatus:
    if purchase_requested is None:
        return "unknown"
    if purchase_requested:
        return "charged"
    return "preview"


def _validate_match_counts(
    *,
    returned_count: int,
    result_count: int,
    total_result_count: int,
    purchase_requested: bool | None,
) -> None:
    """Fail closed unless the counts describe one exact-target outcome.

    A preview counts purchased rows in ``resultCount`` and matches in
    ``totalResultCount``, so each match must come with its returned record.
    Charged and unknown responses keep the exact equality of both counts and
    the returned records.
    """
    if purchase_requested is False:
        if returned_count != total_result_count:
            _raise_invalid(
                "preview_record_withheld"
                if total_result_count
                else "ambiguous_total_result_count"
            )
        if result_count not in (0, returned_count):
            _raise_invalid("result_count_mismatch")
        return
    if result_count != returned_count:
        _raise_invalid("result_count_mismatch")
    if result_count != total_result_count:
        _raise_invalid("ambiguous_total_result_count")


def _parse_property(
    record: Mapping[str, object],
    *,
    expected_radar_id: str,
    expected_county_fips: str,
    purchase_requested: bool | None,
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
    property_type, residential_basis = _parse_residential_property_type(
        record, purchase_requested=purchase_requested
    )
    return BuyerTransferProperty(
        returned_fields=tuple(
            field_name
            for field_name in BUYER_TRANSFER_PROPERTY_FIELDS
            if field_name in record
        ),
        radar_id=radar_id,
        property_type=property_type,
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
        residential_basis=residential_basis,
    )


def _parse_residential_property_type(
    record: Mapping[str, object], *, purchase_requested: bool | None
) -> tuple[BuyerTransferPropertyType | None, BuyerTransferResidentialBasis | None]:
    """Parse PType and the basis of its residential classification.

    Only a preview carries the residential PropertyType criterion, so only a
    preview rejects a returned type outside it and classifies a record
    without PType as residential. A paid or unknown parse classifies from the
    returned PType alone, and a missing PType stays unclassified.
    """
    property_type = _parse_optional_property_type(record)
    if purchase_requested is not False:
        if property_type is None:
            return None, None
        return property_type, "property_type"
    if property_type is None:
        return None, "property_type_criterion"
    if property_type not in _RESIDENTIAL_PROPERTY_TYPES:
        _raise_invalid("property_type_outside_criterion")
    return property_type, "property_type"


def _validate_residential_basis(
    residential_basis: object, property_type: object
) -> None:
    if residential_basis is None:
        return
    if (
        type(residential_basis) is not str
        or residential_basis not in _RESIDENTIAL_BASES
    ):
        raise ValueError("residential_basis is not a documented classification basis")
    if residential_basis == "property_type_criterion":
        if property_type is not None:
            raise ValueError(
                "residential_basis property_type_criterion requires no PType"
            )
    elif property_type not in _PROPERTY_TYPES:
        raise ValueError("residential_basis property_type requires a documented PType")


def _classify_residential(
    property_type: BuyerTransferPropertyType | None,
    residential_basis: BuyerTransferResidentialBasis | None,
) -> bool | None:
    if residential_basis == "property_type_criterion":
        return True
    if property_type in (None, "Unknown"):
        return None
    return property_type in _RESIDENTIAL_PROPERTY_TYPES


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
    """Parse ``totalCost`` sent as a decimal string, a JSON integer or a number.

    Booleans, nulls, non-finite or negative numbers (``-0.0`` included),
    over-long values and every other type fail closed.

    A JSON integer is always exact. A JSON number with a fraction or an
    exponent is already a float when the parser sees it. Its Decimal equals
    the number as written when it has at most 15 significant digits. A longer
    number can already be rounded by JSON decoding before the library sees
    it, and no such number is rejected for that reason.
    """
    parsed: Decimal | None = None
    if type(value) is str:
        parsed = _parse_total_cost_text(value)
    elif type(value) is int:
        parsed = Decimal(value) if 0 <= value < _TOTAL_COST_INTEGER_LIMIT else None
    elif type(value) is float:
        parsed = _parse_total_cost_float(value)
    if parsed is None:
        _raise_invalid("total_cost")
    return parsed


def _parse_total_cost_text(value: str) -> Decimal | None:
    if (
        len(value) <= _TOTAL_COST_MAX_LENGTH
        and _TOTAL_COST_PATTERN.fullmatch(value) is not None
    ):
        return Decimal(value)
    return None


def _parse_total_cost_float(value: float) -> Decimal | None:
    if not math.isfinite(value) or math.copysign(1.0, value) < 0:
        return None
    parsed = Decimal(repr(value))
    if _parse_total_cost_text(format(parsed, "f")) is None:
        return None
    return parsed


def _raise_invalid(reason: str) -> NoReturn:
    raise InvalidResponseError(
        f"PropertyRadar returned invalid buyer-transfer match ({reason})."
    ) from None


def _raise_billed_invalid(
    message: str, billing_evidence: BuyerTransferBillingEvidence
) -> NoReturn:
    raise BuyerTransferResponseError(
        message, billing_evidence=billing_evidence
    ) from None
