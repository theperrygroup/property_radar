"""Property search, detail, comparable, and history API operations."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Literal, cast

from ..buyer_transfer import (
    BUYER_TRANSFER_PROPERTY_FIELDS,
    BuyerTransferMatchCriteria,
    BuyerTransferMatchResult,
    build_buyer_transfer_match_criteria,
    parse_buyer_transfer_match,
)
from ..exceptions import InvalidResponseError
from ..transaction_history import (
    TRANSACTION_HISTORY_FIELDS,
    TransactionHistory,
    parse_transaction_history,
)
from ..types import Criterion, JSONDict, JSONValue, ResponseEnvelope
from ._base import BaseResource, encode_path_segment


class PropertiesResource(BaseResource):
    """Access PropertyRadar property resources."""

    def get(
        self,
        radar_id: str,
        *,
        fields: Sequence[str] | None = None,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Return one property in preview or purchased form.

        Args:
            radar_id: Unique PropertyRadar property identifier.
            fields: Fields or fieldsets to return. Values are encoded as one
                comma-delimited ``Fields`` query parameter.
            purchase: Whether to purchase the returned record. The client must
                also be configured with ``allow_charges=True``.

        Returns:
            The PropertyRadar response envelope for the property.

        Raises:
            ChargeNotAllowedError: If ``purchase`` is true without the
                client-level charge opt-in.
        """
        return self._transport.request(
            "GET",
            f"/v1/properties/{encode_path_segment(radar_id)}",
            params={"Fields": fields, "Purchase": purchase},
            charge=purchase,
        )

    def search(
        self,
        *,
        criteria: Sequence[Criterion],
        fields: Sequence[str] | None = None,
        limit: int | None = None,
        sort: str | None = None,
        start: int | None = None,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Search properties with a generic PropertyRadar criteria body.

        Args:
            criteria: PropertyRadar criteria objects placed under the vendor
                ``Criteria`` request-body key.
            fields: Fields or fieldsets to return. Values are encoded as one
                comma-delimited ``Fields`` query parameter.
            limit: Maximum records to return for this page.
            sort: Vendor sort expression.
            start: Zero-based record offset.
            purchase: Whether to purchase the returned records. The client
                must also be configured with ``allow_charges=True``.

        Returns:
            The PropertyRadar response envelope for the search page.

        Raises:
            ChargeNotAllowedError: If ``purchase`` is true without the
                client-level charge opt-in.
        """
        body = cast(JSONValue, {"Criteria": list(criteria)})
        return self._transport.request(
            "POST",
            "/v1/properties",
            params={
                "Fields": fields,
                "Limit": limit,
                "Sort": sort,
                "Start": start,
                "Purchase": purchase,
            },
            json=body,
            charge=purchase,
            retryable=not purchase,
        )

    def iter_search(
        self,
        *,
        criteria: Sequence[Criterion],
        fields: Sequence[str] | None = None,
        page_size: int = 500,
        max_results: int | None = 500,
        sort: str | None = None,
        start: int = 0,
        purchase: bool = False,
    ) -> Iterator[JSONDict]:
        """Yield property search records across deterministic offset pages.

        Iteration stops at ``max_results`` by default, when PropertyRadar
        reports that all results have been read, or when a page proves the end
        of an uncounted result set. An error from any page is propagated instead
        of returning partial success silently.

        Args:
            criteria: PropertyRadar criteria objects.
            fields: Fields or fieldsets to return.
            page_size: Positive page size. Defaults to the vendor's documented
                maximum page size.
            max_results: Maximum records yielded across all pages. Defaults to
                one maximum-size page. Pass ``None`` only for an explicitly
                unbounded non-purchased iteration.
            sort: Vendor sort expression.
            start: Non-negative initial record offset.
            purchase: Whether every fetched page should be purchased. The
                client must also be configured with ``allow_charges=True``.

        Yields:
            Property dictionaries from each response page.

        Raises:
            ValueError: If pagination bounds are invalid or a purchased
                iteration is explicitly unbounded.
            InvalidResponseError: If pagination metadata or records have an
                unexpected shape.
            ChargeNotAllowedError: If ``purchase`` is true without the
                client-level charge opt-in.
            PropertyRadarError: If any requested page fails.
        """
        if page_size <= 0:
            raise ValueError("page_size must be greater than zero")
        if max_results is not None and max_results < 0:
            raise ValueError("max_results must be zero or greater")
        if start < 0:
            raise ValueError("start must be zero or greater")
        if purchase and max_results is None:
            raise ValueError("purchased iteration requires a finite max_results")
        if max_results == 0:
            return

        next_start = start
        yielded = 0
        while True:
            request_limit = (
                page_size
                if max_results is None
                else min(page_size, max_results - yielded)
            )
            page = self.search(
                criteria=criteria,
                fields=fields,
                limit=request_limit,
                sort=sort,
                start=next_start,
                purchase=purchase,
            )
            results = page.get("results", [])
            if not isinstance(results, list) or any(
                not isinstance(item, dict) for item in results
            ):
                raise InvalidResponseError(
                    "PropertyRadar returned invalid property-search results."
                )
            result_count = len(results)
            records = results
            if max_results is not None:
                records = records[: max_results - yielded]
            yield from records
            yielded += len(records)

            if max_results is not None and yielded >= max_results:
                return
            next_start += result_count
            total_result_count = page.get("totalResultCount")
            if total_result_count is not None:
                if (
                    isinstance(total_result_count, bool)
                    or not isinstance(total_result_count, int)
                    or total_result_count < 0
                ):
                    raise InvalidResponseError(
                        "PropertyRadar returned invalid property-search pagination."
                    )
                if next_start >= total_result_count:
                    return
            if result_count == 0:
                return
            if total_result_count is None and result_count < request_limit:
                return

    def persons(
        self,
        radar_id: str,
        *,
        fields: Sequence[str] | None = None,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Return people associated with a property.

        Args:
            radar_id: Unique PropertyRadar property identifier.
            fields: Fields or fieldsets to return as comma-delimited
                ``Fields``.
            purchase: Whether to purchase the returned records. The client
                must also be configured with ``allow_charges=True``.

        Returns:
            The PropertyRadar response envelope containing people.

        Raises:
            ChargeNotAllowedError: If ``purchase`` is true without the
                client-level charge opt-in.
        """
        return self._transport.request(
            "GET",
            f"/v1/properties/{encode_path_segment(radar_id)}/persons",
            params={"Fields": fields, "Purchase": purchase},
            charge=purchase,
        )

    def evictions(
        self,
        radar_id: str,
        *,
        fields: Sequence[str] | None = None,
        limit: int | None = None,
        start: int | None = None,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Return eviction filings associated with a property.

        Args:
            radar_id: Unique PropertyRadar property identifier.
            fields: Fields to return as comma-delimited ``Fields``.
            limit: Maximum eviction records to return.
            start: Zero-based record offset.
            purchase: Whether to purchase the returned records. The client
                must also be configured with ``allow_charges=True``.

        Returns:
            The PropertyRadar response envelope containing eviction filings.

        Raises:
            ChargeNotAllowedError: If ``purchase`` is true without the
                client-level charge opt-in.
        """
        return self._transport.request(
            "GET",
            f"/v1/properties/{encode_path_segment(radar_id)}/evictions",
            params={
                "Fields": fields,
                "Limit": limit,
                "Start": start,
                "Purchase": purchase,
            },
            charge=purchase,
        )

    def comparable_sales(
        self,
        radar_id: str,
        *,
        fields: Sequence[str] | None = None,
        limit: int | None = None,
        p_type: Sequence[str] | None = None,
        beds: int | None = None,
        baths: str | None = None,
        units: int | None = None,
        sq_ft: int | None = None,
        lot_size: int | None = None,
        year_built: str | None = None,
        transfer_type: Sequence[str] | None = None,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Return comparable property sales.

        Args:
            radar_id: Unique PropertyRadar property identifier.
            fields: Fields to return as comma-delimited ``Fields``.
            limit: Maximum comparable records to return.
            p_type: Property types encoded as comma-delimited ``PType``.
            beds: Bedroom comparison filter.
            baths: Vendor bathroom comparison expression.
            units: Unit-count comparison filter.
            sq_ft: Square-footage comparison filter.
            lot_size: Lot-size comparison filter.
            year_built: Vendor year-built comparison expression.
            transfer_type: Sale transfer types encoded as comma-delimited
                ``TransferType``.
            purchase: Whether to purchase the returned records. The client
                must also be configured with ``allow_charges=True``.

        Returns:
            The PropertyRadar response envelope containing comparable sales.

        Raises:
            ChargeNotAllowedError: If ``purchase`` is true without the
                client-level charge opt-in.
        """
        return self._transport.request(
            "GET",
            f"/v1/properties/{encode_path_segment(radar_id)}/comps/sales",
            params={
                "Fields": fields,
                "Purchase": purchase,
                "Limit": limit,
                "PType": p_type,
                "Beds": beds,
                "Baths": baths,
                "Units": units,
                "SqFt": sq_ft,
                "LotSize": lot_size,
                "YearBuilt": year_built,
                "TransferType": transfer_type,
            },
            charge=purchase,
        )

    def comparable_listings(
        self,
        radar_id: str,
        *,
        fields: Sequence[str] | None = None,
        limit: int | None = None,
        p_type: Sequence[str] | None = None,
        beds: int | None = None,
        baths: str | None = None,
        units: int | None = None,
        sq_ft: int | None = None,
        lot_size: int | None = None,
        year_built: str | None = None,
        listing_type: Sequence[str] | None = None,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Return comparable properties currently listed for sale.

        Args:
            radar_id: Unique PropertyRadar property identifier.
            fields: Fields to return as comma-delimited ``Fields``.
            limit: Maximum comparable records to return.
            p_type: Property types encoded as comma-delimited ``PType``.
            beds: Bedroom comparison filter.
            baths: Vendor bathroom comparison expression.
            units: Unit-count comparison filter.
            sq_ft: Square-footage comparison filter.
            lot_size: Lot-size comparison filter.
            year_built: Vendor year-built comparison expression.
            listing_type: Listing types encoded as comma-delimited
                ``ListingType``.
            purchase: Whether to purchase the returned records. The client
                must also be configured with ``allow_charges=True``.

        Returns:
            The PropertyRadar response envelope containing comparable
            listings.

        Raises:
            ChargeNotAllowedError: If ``purchase`` is true without the
                client-level charge opt-in.
        """
        return self._transport.request(
            "GET",
            f"/v1/properties/{encode_path_segment(radar_id)}/comps/forsale",
            params={
                "Fields": fields,
                "Purchase": purchase,
                "Limit": limit,
                "PType": p_type,
                "Beds": beds,
                "Baths": baths,
                "Units": units,
                "SqFt": sq_ft,
                "LotSize": lot_size,
                "YearBuilt": year_built,
                "ListingType": listing_type,
            },
            charge=purchase,
        )

    def parcels(
        self,
        radar_id: str,
        *,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Return parcel records associated with a property.

        Args:
            radar_id: Unique PropertyRadar property identifier.
            purchase: Whether to purchase the returned records. The client
                must also be configured with ``allow_charges=True``.

        Returns:
            The PropertyRadar response envelope containing parcels.

        Raises:
            ChargeNotAllowedError: If ``purchase`` is true without the
                client-level charge opt-in.
        """
        return self._transport.request(
            "GET",
            f"/v1/properties/{encode_path_segment(radar_id)}/parcels",
            params={"Purchase": purchase},
            charge=purchase,
        )

    def transactions(
        self,
        radar_id: str,
        *,
        fields: Sequence[str] | None = None,
        filter_by: Literal["CurrentOwner", "All"] | None = None,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Return recorded transactions associated with a property.

        Args:
            radar_id: Unique PropertyRadar property identifier.
            fields: Fields to return as comma-delimited ``Fields``.
            filter_by: Limit results to the current owner or return all
                transactions. When omitted, PropertyRadar uses ``All``.
            purchase: Whether to purchase the returned records. The client
                must also be configured with ``allow_charges=True``.

        Returns:
            The PropertyRadar response envelope containing transactions.

        Raises:
            ChargeNotAllowedError: If ``purchase`` is true without the
                client-level charge opt-in.
        """
        return self._transport.request(
            "GET",
            f"/v1/properties/{encode_path_segment(radar_id)}/transactions",
            params={
                "Fields": fields,
                "Filter": filter_by,
                "Purchase": purchase,
            },
            charge=purchase,
        )

    def transaction_history(
        self,
        radar_id: str,
        *,
        filter_by: Literal["CurrentOwner", "All"] | None = None,
        purchase: bool = False,
        property_persons: Mapping[str, object] | None = None,
    ) -> TransactionHistory:
        """Return strictly parsed transaction history without changing raw calls.

        The method requests the exact public transaction field catalog and
        supplies the known purchase flag to the billing parser. For structured
        current-owner evidence, first call :meth:`persons` with
        ``PROPERTY_PERSON_IDENTITY_FIELDS`` and pass that raw envelope as
        ``property_persons``. The parser verifies every returned ``RadarID``
        and keeps current owners separate from unlinked transaction parties.

        Args:
            radar_id: Unique PropertyRadar property identifier.
            filter_by: Limit results to the current owner or return all
                transactions. When omitted, PropertyRadar uses ``All``.
            purchase: Whether to purchase the transaction records. The client
                must also be configured with ``allow_charges=True``.
            property_persons: Optional raw dedicated property-person response
                for the same ``radar_id``.

        Returns:
            Immutable typed transaction history and billing evidence.

        Raises:
            TypeError: If ``purchase`` is not exactly a boolean. This is
                rejected before any network request.
            ChargeNotAllowedError: If ``purchase`` is true without the
                client-level charge opt-in.
            InvalidResponseError: If the provider response or optional
                composition violates the bound public contract.
        """
        if type(purchase) is not bool:
            raise TypeError("purchase must be a boolean")
        envelope = self.transactions(
            radar_id,
            fields=TRANSACTION_HISTORY_FIELDS,
            filter_by=filter_by,
            purchase=purchase,
        )
        return parse_transaction_history(
            envelope,
            purchase_requested=purchase,
            property_persons=property_persons,
            radar_id=radar_id,
        )

    def buyer_transfer_match(
        self,
        *,
        criteria: BuyerTransferMatchCriteria,
        purchase: bool = False,
    ) -> BuyerTransferMatchResult:
        """Return one typed Buyer-criterion linkage to an exact property.

        The method builds the bounded public criteria, requests only the
        immutable property identity/location field catalog, limits the search
        to one exact RadarID, and strictly parses the response. A returned
        linkage means that PropertyRadar matched the documented Buyer Name
        (Grantee) criterion; it does not invent exact-name semantics or parse
        scalar transaction-party displays.

        Args:
            criteria: Exact buyer, property, geography, and transfer windows.
            purchase: Whether to purchase the returned property record. The
                client must also be configured with ``allow_charges=True``.

        Returns:
            Immutable linkage, property location, and billing evidence.

        Raises:
            TypeError: If ``purchase`` is not exactly a boolean. This is
                rejected before any network request.
            ChargeNotAllowedError: If ``purchase`` is true without the
                client-level charge opt-in.
            InvalidResponseError: If the response violates the public contract.
        """
        if type(purchase) is not bool:
            raise TypeError("purchase must be a boolean")
        envelope = self.search(
            criteria=build_buyer_transfer_match_criteria(criteria),
            fields=BUYER_TRANSFER_PROPERTY_FIELDS,
            limit=1,
            start=0,
            purchase=purchase,
        )
        return parse_buyer_transfer_match(
            envelope,
            criteria=criteria,
            purchase_requested=purchase,
        )
