"""Typed historical buyer linkage under the current provider response schema.

Only a non-billable ``Purchase=0`` preview carries the residential
PropertyType criterion. That criterion follows the official API reference and
has not been live-probed on ``Purchase=0``. A preview's ``matched=False`` also
covers a non-residential or Unknown transfer that the provider dropped under
the criterion. A paid ``Purchase=1`` request carries no PropertyType
criterion, and a paid result classifies the property from the returned PType.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import cast

from .buyer_transfer import (
    _FIPS_PATTERN,
    _PROPERTY_TYPES,
    _RELATIONSHIP,
    _REQUIRED_ENVELOPE_FIELDS,
    _SHA256_PATTERN,
    BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT,
    BUYER_TRANSFER_PROPERTY_FIELDS,
    BuyerTransferBillingEvidence,
    BuyerTransferLinkageRelationship,
    BuyerTransferMatchCriteria,
    BuyerTransferPropertyField,
    BuyerTransferPropertyType,
    BuyerTransferResidentialBasis,
    _bare_preview_billing,
    _billing_returns_record,
    _classify_residential,
    _is_bare_preview_envelope,
    _parse_billed_record,
    _parse_match_billing,
    _parse_optional_coordinate,
    _parse_optional_fips,
    _parse_optional_provider_text,
    _parse_required_provider_text,
    _parse_residential_property_type,
    _raise_invalid,
    _snapshot_string_mapping,
    _validate_coordinate,
    _validate_residential_basis,
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
    """One exact historical buyer outcome and its immutable billing evidence.

    A preview's ``matched=False`` also covers a non-residential or Unknown
    transfer that the provider dropped under the preview's residential
    PropertyType criterion. That criterion follows the official API reference
    and has not been live-probed on ``Purchase=0``. A paid result classifies
    the property from the returned PType.
    """

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


def parse_historical_buyer_transfer_match(
    envelope: Mapping[str, object],
    *,
    criteria: BuyerTransferMatchCriteria,
    purchase_requested: bool | None = None,
) -> HistoricalBuyerTransferMatchResult:
    """Parse one bounded historical Buyer-criterion property-search response.

    The result retains only documented property and billing fields. The
    linkage does not claim a transaction identifier or structured grantees.

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
    if _is_bare_preview_envelope(typed_envelope, purchase_requested=purchase_requested):
        return HistoricalBuyerTransferMatchResult(
            contract_fingerprint=cast(
                str, BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT["contract_fingerprint"]
            ),
            scope_fingerprint=buyer_transfer_scope_fingerprint(criteria),
            linkage=None,
            billing=_bare_preview_billing(),
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
        linkage = HistoricalBuyerTransferLinkage(
            scope_fingerprint=scope_fingerprint,
            property=property_result,
        )

    return HistoricalBuyerTransferMatchResult(
        contract_fingerprint=cast(
            str, BUYER_TRANSFER_HISTORICAL_MATCH_CONTRACT["contract_fingerprint"]
        ),
        scope_fingerprint=scope_fingerprint,
        linkage=linkage,
        billing=billing,
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
    purchase_requested: bool | None,
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
    property_type, residential_basis = _parse_residential_property_type(
        record, purchase_requested=purchase_requested
    )
    return HistoricalBuyerTransferProperty(
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


def _parse_optional_zip(record: Mapping[str, object]) -> str | None:
    if "ZipFive" not in record:
        return None
    value = record["ZipFive"]
    if type(value) is not str or _ZIP_FIVE_PATTERN.fullmatch(value) is None:
        _raise_invalid("zip_five")
    return value
