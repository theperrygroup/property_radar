"""Typed historical buyer linkage under the current provider response schema."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from .buyer_transfer import (
    _FIPS_PATTERN,
    _PROPERTY_TYPES,
    _RELATIONSHIP,
    _REQUIRED_ENVELOPE_FIELDS,
    _RESIDENTIAL_PROPERTY_TYPES,
    _SHA256_PATTERN,
    BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT,
    BUYER_TRANSFER_PROPERTY_FIELDS,
    BuyerTransferBillingEvidence,
    BuyerTransferBillingStatus,
    BuyerTransferLinkageRelationship,
    BuyerTransferMatchCriteria,
    BuyerTransferPropertyField,
    BuyerTransferPropertyType,
    _parse_match_count,
    _parse_nonnegative_integer,
    _parse_optional_coordinate,
    _parse_optional_fips,
    _parse_optional_property_type,
    _parse_optional_provider_text,
    _parse_required_provider_text,
    _parse_total_cost,
    _raise_invalid,
    _snapshot_string_mapping,
    _validate_coordinate,
    buyer_transfer_scope_fingerprint,
)

_ZIP_FIVE_PATTERN = re.compile(r"[0-9]{5}")
_HISTORICAL_ENVELOPE_FIELDS = (
    *_REQUIRED_ENVELOPE_FIELDS,
    "quantityFreeRemaining",
    "maxDistanceMiles",
    "nextPageToken",
    "facets",
)


@dataclass(frozen=True, slots=True, repr=False)
class HistoricalBuyerTransferProperty:
    """One immutable historical match with the provider's exact ZIP string."""

    returned_fields: tuple[BuyerTransferPropertyField, ...]
    radar_id: str
    property_type: BuyerTransferPropertyType | None
    address: str | None
    city: str | None
    state: str | None
    zip_five: str | None
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
            type(self.zip_five) is not str
            or _ZIP_FIVE_PATTERN.fullmatch(self.zip_five) is None
        ):
            raise ValueError("zip_five must be a string of five ASCII digits")
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
class HistoricalBuyerTransferLinkage:
    """Provider evidence that one historical Buyer criterion returned a property."""

    scope_fingerprint: str
    property: HistoricalBuyerTransferProperty
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
        if not isinstance(self.property, HistoricalBuyerTransferProperty):
            raise ValueError("property must be HistoricalBuyerTransferProperty")
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
class HistoricalBuyerTransferMatchResult:
    """One exact historical buyer outcome and its immutable billing evidence."""

    contract_fingerprint: str
    scope_fingerprint: str
    linkage: HistoricalBuyerTransferLinkage | None
    billing: BuyerTransferBillingEvidence

    def __post_init__(self) -> None:
        """Bind linkage and billing evidence to the historical response contract."""
        if (
            self.contract_fingerprint
            != BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT["contract_fingerprint"]
        ):
            raise ValueError("contract_fingerprint does not identify this contract")
        if (
            type(self.scope_fingerprint) is not str
            or _SHA256_PATTERN.fullmatch(self.scope_fingerprint) is None
        ):
            raise ValueError("scope_fingerprint must be a SHA-256 value")
        if self.linkage is not None and (
            not isinstance(self.linkage, HistoricalBuyerTransferLinkage)
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


def parse_historical_buyer_transfer_match(
    envelope: Mapping[str, object],
    *,
    criteria: BuyerTransferMatchCriteria,
    purchase_requested: bool | None = None,
) -> HistoricalBuyerTransferMatchResult:
    """Parse one bounded historical Buyer-criterion property-search response.

    The result retains only documented property and billing fields. The
    linkage does not claim a transaction identifier or structured grantees.
    """
    if not isinstance(criteria, BuyerTransferMatchCriteria):
        _raise_invalid("criteria_type")
    if criteria.recording_date_range is None:
        _raise_invalid("historical_recording_date_range")
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
    if envelope_keys.difference(_HISTORICAL_ENVELOPE_FIELDS):
        _raise_invalid("undocumented_envelope_fields")
    _validate_optional_envelope_fields(typed_envelope)

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
        linkage = HistoricalBuyerTransferLinkage(
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
    return HistoricalBuyerTransferMatchResult(
        contract_fingerprint=cast(
            str, BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT["contract_fingerprint"]
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


def _validate_optional_envelope_fields(envelope: Mapping[str, object]) -> None:
    if "maxDistanceMiles" in envelope:
        distance = envelope["maxDistanceMiles"]
        if type(distance) is not int or not 0 <= distance <= 250:
            _raise_invalid("max_distance_miles")
    if "nextPageToken" in envelope:
        token = envelope["nextPageToken"]
        if type(token) is not str or token != "":
            _raise_invalid("next_page_token")
    if "facets" in envelope:
        facets = envelope["facets"]
        if type(facets) is not dict or facets:
            _raise_invalid("facets")


def _parse_property(
    record: Mapping[str, object],
    *,
    expected_radar_id: str,
    expected_county_fips: str,
) -> HistoricalBuyerTransferProperty:
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
    return HistoricalBuyerTransferProperty(
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


def _parse_optional_zip(record: Mapping[str, object]) -> str | None:
    if "ZipFive" not in record:
        return None
    value = record["ZipFive"]
    if type(value) is not str or _ZIP_FIVE_PATTERN.fullmatch(value) is None:
        _raise_invalid("zip_five")
    return value
