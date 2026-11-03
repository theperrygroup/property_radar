"""Versioned, bounded transaction quotes and results for API 5.3.1.0.

This contract deliberately leaves the older transaction-history parser intact.
It performs no I/O, authorization, retry, party matching, or date inference.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Literal, NoReturn, cast

from .exceptions import InvalidResponseError

HistoricalTransactionFilter = Literal["All", "CurrentOwner"]
HistoricalTransactionDocGroup = Literal[
    "Mortgage", "Deed", "Foreclosure", "Lien", "Notice", "Release", "Other"
]
HistoricalTransactionField = Literal[
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
    "RadarID",
    "DocType",
    "DocGroup",
]
HistoricalRecordingDateStatus = Literal[
    "missing", "scalar_unverified", "ambiguous_array"
]

HISTORICAL_TRANSACTION_FIELDS: tuple[HistoricalTransactionField, ...] = (
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
    "RadarID",
    "DocType",
    "DocGroup",
)
"""Explicit positive field selection; no implicit provider fieldset changes."""

_GROUPS = ("Mortgage", "Deed", "Foreclosure", "Lien", "Notice", "Release", "Other")
_STATUSES = ("original", "edited", "deleted", "created")
_COST = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_DOC_TYPE = re.compile(r"[A-Z]{3}")
_ENVELOPE_FIELDS = frozenset(
    ("results", "totalCost", "resultCount", "totalResultCount", "quantityFreeRemaining")
)
_REQUIRED_FIELDS = frozenset(("totalCost", "resultCount", "totalResultCount"))


def _fingerprint(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


_CONTRACT_SOURCE: dict[str, object] = {
    "contract_version": "1.1",
    "api_version": "5.3.1.0",
    "spec_source": "https://developers.propertyradar.com/_spec/api.json",
    "spec_source_sha256": (
        # pragma: allowlist nextline secret
        "9feadf6a8fade0530045f4d6f14db69f520144078a71637ef6c999aea8493c14"
    ),
    "method": "GET",
    "path": "/v1/properties/{RadarID}/transactions",
    "ordered_fields": HISTORICAL_TRANSACTION_FIELDS,
    "filter_values": ("All", "CurrentOwner"),
    "doc_group_values": _GROUPS,
    "status_values": _STATUSES,
    "recording_dates": "explicit_absolute_start_and_end_boundary_semantics_unspecified",
    "local_limit_minimum": 1,
    "local_limit_maximum": 500,
    "provider_limit_maximum": None,
    "document_id_lookup": "unsupported_bypasses_limit",
    "local_selected_count_policy": "min(totalResultCount, Limit)",
    "quote_records": "omitted_or_empty",
    "paid_records": "exactly_resultCount",
    "counts": "exact_nonnegative_json_integers",
    "total_cost": "nonnegative_ascii_decimal_string_maximum_64_characters",
    "currency": None,
    "required_envelope_fields": tuple(sorted(_REQUIRED_FIELDS)),
    "record_fields_required_by_provider": (),
    "missing_record_fields": "preserved_as_unavailable",
    "duplicate_nonempty_document_ids": "reject",
    "returned_property_id": "must_match_query_when_present",
    "undocumented_envelope_and_record_fields": "reject",
    "request_mode": "explicit_caller_context_not_response_echo",
    "failure_billing_evidence": "independently_valid_cost_and_counts_before_rows",
    "recording_date_response_schema": "array_RelativeDate_ambiguous",
    "recording_date_scalar": "preserve_legacy_string_unverified",
    "recording_date_array": "preserve_string_tuple_never_convert",
    "party_identity_linkage": None,
    "snapshot_before_validation": True,
    "automatic_retries": False,
}
HISTORICAL_TRANSACTION_CONTRACT: Mapping[str, object] = MappingProxyType(
    {**_CONTRACT_SOURCE, "contract_fingerprint": _fingerprint(_CONTRACT_SOURCE)}
)
"""Immutable provenance and local safety policy, separate from older contracts."""


@dataclass(frozen=True, slots=True, repr=False)
class HistoricalTransactionDateRange:
    """An explicit recording-date range; provider boundary semantics are unspecified."""

    start: date
    end: date

    def __post_init__(self) -> None:
        """Reject datetimes and inverted or incomplete ranges."""
        if type(self.start) is not date or type(self.end) is not date:
            raise ValueError("recording date bounds must be exact date values")
        if self.start > self.end:
            raise ValueError("recording date start must not follow end")

    def as_provider_value(self) -> str:
        """Encode the documented RelativeDate from/to grammar."""
        return (
            f"from: {self.start.month:02}/{self.start.day:02}/{self.start.year:04} "
            f"to: {self.end.month:02}/{self.end.day:02}/{self.end.year:04}"
        )

    def __repr__(self) -> str:
        """Keep query dates out of routine representations."""
        return f"{type(self).__name__}(bounded=True)"


@dataclass(frozen=True, slots=True, repr=False)
class HistoricalTransactionQuery:
    """A property-scoped, explicitly bounded immutable transaction query.

    ``limit`` is a local safety cap of 1..500, not a claimed provider maximum.
    Multiple values within one document axis are ORed; axes are ANDed by the
    provider. Tuple order is retained in the exact request fingerprint.
    """

    radar_id: str
    recording_dates: HistoricalTransactionDateRange
    limit: int
    filter: HistoricalTransactionFilter = "All"
    doc_types: tuple[str, ...] = ()
    doc_groups: tuple[HistoricalTransactionDocGroup, ...] = ()

    def __post_init__(self) -> None:
        """Validate the entire scope before any caller can issue a request."""
        if (
            type(self.radar_id) is not str
            or not self.radar_id
            or len(self.radar_id) > 128
            or re.fullmatch(r"[A-Za-z0-9_-]+", self.radar_id) is None
        ):
            raise ValueError("radar_id must be a bounded opaque property identifier")
        if type(self.recording_dates) is not HistoricalTransactionDateRange:
            raise ValueError("recording_dates must be HistoricalTransactionDateRange")
        if type(self.limit) is not int or not 1 <= self.limit <= 500:
            raise ValueError("limit must be an integer between 1 and 500")
        if type(self.filter) is not str or self.filter not in ("All", "CurrentOwner"):
            raise ValueError("filter must be All or CurrentOwner")
        if (
            type(self.doc_types) is not tuple
            or len(self.doc_types) > 50
            or any(
                type(v) is not str or _DOC_TYPE.fullmatch(v) is None
                for v in self.doc_types
            )
            or len(set(self.doc_types)) != len(self.doc_types)
        ):
            raise ValueError("doc_types must be a unique tuple of three-letter codes")
        if (
            type(self.doc_groups) is not tuple
            or any(type(v) is not str or v not in _GROUPS for v in self.doc_groups)
            or len(set(self.doc_groups)) != len(self.doc_groups)
        ):
            raise ValueError("doc_groups must be a unique tuple of documented groups")

    def params(self, *, purchase: bool) -> dict[str, str | int]:
        """Return detached encoded parameters; authorization remains the caller's."""
        if type(purchase) is not bool:
            raise ValueError("purchase must be an exact boolean")
        params: dict[str, str | int] = {
            "Fields": ",".join(HISTORICAL_TRANSACTION_FIELDS),
            "Purchase": int(purchase),
            "Filter": self.filter,
            "RecDate": self.recording_dates.as_provider_value(),
            "Limit": self.limit,
        }
        if self.doc_types:
            params["DocType"] = ",".join(self.doc_types)
        if self.doc_groups:
            params["DocGroup"] = ",".join(self.doc_groups)
        return params

    @property
    def scope_fingerprint(self) -> str:
        """Bind property, fields, range, filters and limit across quote and result."""
        params = self.params(purchase=False)
        del params["Purchase"]
        return _fingerprint(
            {
                "contract": HISTORICAL_TRANSACTION_CONTRACT["contract_fingerprint"],
                "radar_id": self.radar_id,
                "params": params,
            }
        )

    def __repr__(self) -> str:
        """Expose query shape without the property identifier or filters."""
        return f"{type(self).__name__}(limit={self.limit})"


@dataclass(frozen=True, slots=True, repr=False)
class HistoricalTransactionRecord:
    """An immutable row with opaque displays and explicit date uncertainty.

    Missing fields remain missing. A scalar recording date is preserved for
    legacy compatibility but is not verified or parsed as a calendar date.
    A RelativeDate array is preserved separately, including an empty array.
    No party is associated with a buyer or current property owner.
    """

    fields: Mapping[HistoricalTransactionField, str | tuple[str, ...]]

    def __post_init__(self) -> None:
        """Snapshot and validate row values without retaining caller containers."""
        row = _snapshot(self.fields, "record", allow_date_tuple=True)
        if set(row).difference(HISTORICAL_TRANSACTION_FIELDS):
            _invalid("undocumented_record_fields")
        for key, value in row.items():
            if key == "RecDate" and type(value) in (tuple, list):
                values = tuple(cast(list[object] | tuple[object, ...], value))
                if any(type(item) is not str for item in values):
                    _invalid("recording_date_array")
                row[key] = values
            elif type(value) is not str:
                _invalid("record_field_type")
        if "Status" in row and row["Status"] not in _STATUSES:
            _invalid("record_status")
        if "DocGroup" in row and row["DocGroup"] not in _GROUPS:
            _invalid("record_doc_group")
        object.__setattr__(self, "fields", MappingProxyType(row))

    def _text(self, field: HistoricalTransactionField) -> str | None:
        value = self.fields.get(field)
        return value if isinstance(value, str) else None

    @property
    def document_id(self) -> str | None:
        """Return the provider document identifier, if supplied."""
        return self._text("DocumentID")

    @property
    def radar_id(self) -> str | None:
        """Return the provider property identifier, if supplied."""
        return self._text("RadarID")

    @property
    def document_type(self) -> str | None:
        """Return the raw document type, if supplied."""
        return self._text("DocType")

    @property
    def document_type_ui(self) -> str | None:
        """Return the opaque document display type, if supplied."""
        return self._text("DocTypeUI")

    @property
    def doc_group(self) -> str | None:
        """Return the provider document group, if supplied."""
        return self._text("DocGroup")

    @property
    def status(self) -> str | None:
        """Return the provider modification status, if supplied."""
        return self._text("Status")

    @property
    def recording_date(self) -> str | None:
        """Return only an unverified scalar; never convert array evidence."""
        return self._text("RecDate")

    @property
    def unverified_recording_dates(self) -> tuple[str, ...] | None:
        """Return the ambiguous provider array exactly, without interpretation."""
        value = self.fields.get("RecDate")
        return value if isinstance(value, tuple) else None

    @property
    def recording_date_status(self) -> HistoricalRecordingDateStatus:
        """Distinguish absent, legacy scalar, and ambiguous array evidence."""
        if "RecDate" not in self.fields:
            return "missing"
        if self.unverified_recording_dates is not None:
            return "ambiguous_array"
        return "scalar_unverified"

    @property
    def grantor_display(self) -> str | None:
        """Return the opaque seller display without parsing party boundaries."""
        return self._text("Grantor")

    @property
    def grantee_display(self) -> str | None:
        """Return the opaque buyer display without asserting buyer linkage."""
        return self._text("Grantee")

    @property
    def amount(self) -> str | None:
        """Preserve the provider's opaque amount display without money inference."""
        return self._text("Amount")

    @property
    def missing_fields(self) -> tuple[HistoricalTransactionField, ...]:
        """Report unavailable requested fields without inventing their values."""
        return tuple(
            name for name in HISTORICAL_TRANSACTION_FIELDS if name not in self.fields
        )

    def __repr__(self) -> str:
        """Return shape metadata without licensed row values."""
        return (
            f"{type(self).__name__}(field_count={len(self.fields)}, "
            f"recording_date_status={self.recording_date_status!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class _Selection:
    query: HistoricalTransactionQuery
    result_count: int
    total_result_count: int
    total_cost: Decimal

    def __post_init__(self) -> None:
        if type(self.query) is not HistoricalTransactionQuery:
            raise ValueError("query must be HistoricalTransactionQuery")
        for count in (self.result_count, self.total_result_count):
            if type(count) is not int or count < 0:
                raise ValueError("counts must be nonnegative integers")
        if self.result_count != min(self.query.limit, self.total_result_count):
            raise ValueError("selected count must equal the bounded total count")
        if not _valid_decimal(self.total_cost):
            raise ValueError("total_cost must be a bounded nonnegative decimal")
        if self.result_count == 0 and self.total_cost != 0:
            raise ValueError("an empty selection cannot have a per-record charge")

    @property
    def scope_fingerprint(self) -> str:
        """Return the exact request scope shared by quote and paid result."""
        return self.query.scope_fingerprint

    @property
    def truncated(self) -> bool:
        """Indicate that more filtered rows exist beyond the selected limit."""
        return self.result_count < self.total_result_count

    @property
    def currency(self) -> None:
        """Return unavailable: the provider does not document a currency field."""
        return None

    def __repr__(self) -> str:
        """Return bounded metadata without query or licensed record contents."""
        return (
            f"{type(self).__name__}(result_count={self.result_count}, "
            f"total_result_count={self.total_result_count}, "
            f"total_cost={self.total_cost!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class HistoricalTransactionQuote(_Selection):
    """Nonbillable preview counts and estimated cost, independent of row data."""

    quantity_free_remaining: int | None = None

    def __post_init__(self) -> None:
        """Validate preview metadata without treating a quote as a charge."""
        super(HistoricalTransactionQuote, self).__post_init__()
        if self.quantity_free_remaining is not None and (
            type(self.quantity_free_remaining) is not int
            or self.quantity_free_remaining < 0
        ):
            raise ValueError("quantity_free_remaining must be nonnegative or None")

    @property
    def purchase_requested(self) -> Literal[False]:
        """Identify the caller-selected nonbillable request mode."""
        return False

    @property
    def billing_status(self) -> Literal["preview"]:
        """Identify quoted cost, never paid cost."""
        return "preview"


@dataclass(frozen=True, slots=True, repr=False)
class HistoricalTransactionResult(_Selection):
    """Complete selected rows and returned cost from an explicit paid request.

    Completeness applies to the bounded selection, not to all filtered rows or
    to missing record fields. This type does not authorize a purchase.
    """

    records: tuple[HistoricalTransactionRecord, ...]

    def __post_init__(self) -> None:
        """Reject incomplete selections and mismatched property evidence."""
        super(HistoricalTransactionResult, self).__post_init__()
        if type(self.records) is not tuple or any(
            type(row) is not HistoricalTransactionRecord for row in self.records
        ):
            raise ValueError("records must be an immutable historical row tuple")
        if len(self.records) != self.result_count:
            raise ValueError("returned rows must exactly match the selected count")
        identifiers: set[str] = set()
        for row in self.records:
            if row.radar_id is not None and row.radar_id != self.query.radar_id:
                raise ValueError("returned property does not match query")
            if row.document_id:
                if row.document_id in identifiers:
                    raise ValueError("duplicate document identifiers are ambiguous")
                identifiers.add(row.document_id)

    @property
    def purchase_requested(self) -> Literal[True]:
        """Identify the caller-selected paid request mode."""
        return True

    @property
    def billing_status(self) -> Literal["charged"]:
        """Identify the provider-returned paid-request cost."""
        return "charged"


@dataclass(frozen=True, slots=True, repr=False)
class HistoricalTransactionBillingEvidence:
    """Independent billing metadata retained when response validation fails.

    Each nullable field is validated independently. Conflicting counts or
    incomplete rows cannot erase a valid returned cost. This is evidence from
    a known request mode, not a complete result or provider account settlement.
    """

    purchase_requested: bool
    scope_fingerprint: str
    total_cost: Decimal | None
    result_count: int | None
    total_result_count: int | None

    def __post_init__(self) -> None:
        """Reject mutable or malformed manually constructed evidence."""
        if type(self.purchase_requested) is not bool:
            raise ValueError("purchase_requested must be an exact boolean")
        if (
            type(self.scope_fingerprint) is not str
            or re.fullmatch(r"[0-9a-f]{64}", self.scope_fingerprint) is None
        ):
            raise ValueError("scope_fingerprint must be a SHA-256 digest")
        if self.total_cost is not None and not _valid_decimal(self.total_cost):
            raise ValueError("total_cost must be a bounded nonnegative decimal or None")
        for count in (self.result_count, self.total_result_count):
            if count is not None and (type(count) is not int or count < 0):
                raise ValueError("counts must be nonnegative integers or None")

    @property
    def currency(self) -> None:
        """Return unavailable; no currency is inferred from billing metadata."""
        return None

    def __repr__(self) -> str:
        """Expose metadata availability, never scope or source values."""
        return (
            f"{type(self).__name__}(purchase_requested={self.purchase_requested}, "
            f"cost_available={self.total_cost is not None}, "
            f"selected_count_available={self.result_count is not None}, "
            f"total_count_available={self.total_result_count is not None})"
        )


class HistoricalTransactionResponseError(InvalidResponseError):
    """A rejected response with independently valid, privacy-safe billing data."""

    def __init__(
        self, message: str, *, billing_evidence: HistoricalTransactionBillingEvidence
    ) -> None:
        """Attach immutable billing evidence without retaining the response."""
        super().__init__(message)
        self.billing_evidence = billing_evidence


def parse_historical_transaction_quote(
    envelope: Mapping[str, object], *, query: HistoricalTransactionQuery
) -> HistoricalTransactionQuote:
    """Parse a known Purchase=0 response; never infer request mode from a body."""
    outcome = _parse_response(envelope, query=query, purchase=False)
    del envelope, query
    if isinstance(outcome, (HistoricalTransactionResponseError, ValueError)):
        raise outcome from None
    return cast(HistoricalTransactionQuote, outcome)


def _parse_quote(
    envelope: Mapping[str, object], *, query: HistoricalTransactionQuery
) -> HistoricalTransactionQuote:
    snapshot = _envelope(envelope)
    if "results" in snapshot:
        rows = snapshot["results"]
        if type(rows) is not list or rows:
            _invalid("quote_results_not_omitted")
    try:
        return HistoricalTransactionQuote(
            query=query,
            result_count=_count(snapshot["resultCount"]),
            total_result_count=_count(snapshot["totalResultCount"]),
            total_cost=_cost(snapshot["totalCost"]),
            quantity_free_remaining=(
                _count(snapshot["quantityFreeRemaining"])
                if "quantityFreeRemaining" in snapshot
                else None
            ),
        )
    except ValueError:
        pass
    _invalid("quote_selection")


def parse_historical_transaction_result(
    envelope: Mapping[str, object], *, query: HistoricalTransactionQuery
) -> HistoricalTransactionResult:
    """Parse a known Purchase=1 response with all selected rows present.

    An absent/invalid result is never converted to an empty success. A returned
    row's scalar date remains unverified; array dates remain ambiguous.
    """
    outcome = _parse_response(envelope, query=query, purchase=True)
    del envelope, query
    if isinstance(outcome, (HistoricalTransactionResponseError, ValueError)):
        raise outcome from None
    return cast(HistoricalTransactionResult, outcome)


def _parse_result(
    envelope: Mapping[str, object], *, query: HistoricalTransactionQuery
) -> HistoricalTransactionResult:
    snapshot = _envelope(envelope)
    if "quantityFreeRemaining" in snapshot:
        _invalid("paid_preview_metadata")
    raw_rows = snapshot.get("results")
    if type(raw_rows) is not list:
        _invalid("paid_results_missing")
    if len(raw_rows) != _count(snapshot["resultCount"]) or len(raw_rows) > query.limit:
        _invalid("paid_selection_count")
    # Snapshot every row before parsing or validation can observe mutable input.
    row_snapshots = tuple(_snapshot(row, "record") for row in list.copy(raw_rows))
    records = tuple(
        HistoricalTransactionRecord(
            cast(Mapping[HistoricalTransactionField, str | tuple[str, ...]], row)
        )
        for row in row_snapshots
    )
    try:
        return HistoricalTransactionResult(
            query=query,
            result_count=_count(snapshot["resultCount"]),
            total_result_count=_count(snapshot["totalResultCount"]),
            total_cost=_cost(snapshot["totalCost"]),
            records=records,
        )
    except ValueError:
        pass
    _invalid("paid_selection")


def _parse_response(
    envelope: Mapping[str, object], *, query: HistoricalTransactionQuery, purchase: bool
) -> (
    HistoricalTransactionQuote
    | HistoricalTransactionResult
    | HistoricalTransactionResponseError
    | ValueError
):
    if type(query) is not HistoricalTransactionQuery:
        return ValueError("query must be HistoricalTransactionQuery")
    evidence = _billing_evidence({}, query=query, purchase=purchase)
    try:
        # One snapshot supplies both the independent metadata and strict parser.
        # Validate all keys in the strict parser after preserving known fields.
        snapshot = _snapshot(envelope, "envelope", validate_keys=False)
        evidence = _billing_evidence(snapshot, query=query, purchase=purchase)
        if purchase:
            return _parse_result(snapshot, query=query)
        return _parse_quote(snapshot, query=query)
    except InvalidResponseError as error:
        message = str(error)
    # Return unraised, outside the handler. Only the clean public frame raises;
    # neither the context nor the library traceback then retains source data.
    return HistoricalTransactionResponseError(message, billing_evidence=evidence)


def _billing_evidence(
    snapshot: Mapping[str, object], *, query: HistoricalTransactionQuery, purchase: bool
) -> HistoricalTransactionBillingEvidence:
    known = {key: value for key, value in snapshot.items() if type(key) is str}
    raw_cost = known.get("totalCost")
    cost = None
    if type(raw_cost) is str and len(raw_cost) <= 64 and _COST.fullmatch(raw_cost):
        cost = Decimal(raw_cost)
    selected = known.get("resultCount")
    total = known.get("totalResultCount")
    return HistoricalTransactionBillingEvidence(
        purchase_requested=purchase,
        scope_fingerprint=query.scope_fingerprint,
        total_cost=cost,
        result_count=selected if type(selected) is int and selected >= 0 else None,
        total_result_count=total if type(total) is int and total >= 0 else None,
    )


def _envelope(source: object) -> dict[str, object]:
    snapshot = _snapshot(source, "envelope")
    if not _REQUIRED_FIELDS.issubset(snapshot):
        _invalid("missing_envelope_fields")
    if set(snapshot).difference(_ENVELOPE_FIELDS):
        _invalid("undocumented_envelope_fields")
    return snapshot


def _snapshot(
    source: object,
    kind: str,
    *,
    allow_date_tuple: bool = False,
    validate_keys: bool = True,
) -> dict[str, object]:
    if not isinstance(source, Mapping):
        _invalid(f"{kind}_type")
    try:
        snapshot = dict.copy(source) if isinstance(source, dict) else dict(source)
    except Exception:
        snapshot = None
    if snapshot is None:
        _invalid(f"{kind}_snapshot")
    if validate_keys and any(type(key) is not str for key in snapshot):
        _invalid(f"{kind}_key_type")
    if kind == "record":
        recording_date = snapshot.get("RecDate")
        if type(recording_date) is list:
            snapshot["RecDate"] = tuple(list.copy(recording_date))
        elif type(recording_date) is tuple and not allow_date_tuple:
            _invalid("recording_date_array")
    return cast(dict[str, object], snapshot)


def _count(value: object) -> int:
    if type(value) is not int or value < 0:
        _invalid("count_type")
    return value


def _cost(value: object) -> Decimal:
    if type(value) is not str or len(value) > 64 or _COST.fullmatch(value) is None:
        _invalid("total_cost")
    return Decimal(value)


def _valid_decimal(value: object) -> bool:
    return (
        type(value) is Decimal
        and value.is_finite()
        and value >= 0
        and value.as_tuple().exponent in range(-63, 64)
        and len(value.as_tuple().digits) <= 64
        and len(format(value, "f")) <= 64
        and _COST.fullmatch(format(value, "f")) is not None
    )


def _invalid(reason: str) -> NoReturn:
    raise InvalidResponseError(
        f"PropertyRadar returned invalid historical transactions ({reason})."
    ) from None
