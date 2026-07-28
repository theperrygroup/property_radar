"""List import and matching API operations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, cast

from ..types import ImportItem, JSONValue, ResponseEnvelope
from ._base import BaseResource, encode_path_segment

SortDirection = Literal["asc", "desc"]
PropertyStatus = Literal["Selected", "Matched", "Pending", "Not Found"]
PersonStatus = Literal[
    "Matched Primary",
    "Matched Set as Primary",
    "Added as Primary",
    "Matched",
    "Selected as Primary",
    "Selected",
    "Not Found",
    "No Longer at Property",
]


class ImportsResource(BaseResource):
    """Access PropertyRadar list-import resources."""

    def items(
        self,
        list_id: int,
        *,
        fields: Sequence[str] | None = None,
        limit: int = 100,
        sort: str = "ListImportItemID",
        direction: SortDirection = "asc",
        start: int = 0,
        match_score: int | None = None,
        property_status: PropertyStatus | None = None,
        person_status: PersonStatus | None = None,
    ) -> ResponseEnvelope:
        """Return imported items and their match status.

        Args:
            list_id: Unique PropertyRadar import-list identifier.
            fields: Vendor fields to include or suppress.
            limit: Maximum number of items to return.
            sort: Vendor field used to sort results.
            direction: Ascending or descending sort direction.
            start: Zero-based result offset.
            match_score: Match-score filter.
            property_status: Property matching-status filter.
            person_status: Person matching-status filter.

        Returns:
            The PropertyRadar response envelope.
        """
        return self._transport.request(
            "GET",
            f"/v1/lists/{encode_path_segment(list_id)}/import/items",
            params={
                "Fields": fields,
                "Limit": limit,
                "Sort": sort,
                "Dir": direction,
                "Start": start,
                "MatchScore": match_score,
                "PropertyStatus": property_status,
                "PersonStatus": person_status,
            },
        )

    def match(
        self,
        list_id: int,
        import_items: Sequence[ImportItem],
        *,
        fields: Sequence[str] | None = None,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Add and match imported records against PropertyRadar data.

        Args:
            list_id: Unique PropertyRadar import-list identifier.
            import_items: Synthetic or caller-owned records to import and match.
            fields: Vendor fields to include or suppress.
            purchase: Whether to purchase the matched records. Defaults to a
                non-billable cost preview.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            ChargeNotAllowedError: If ``purchase`` is true but charges are
                disabled.
            MutationNotAllowedError: If persistent mutations are disabled.
        """
        return self._transport.request(
            "POST",
            f"/v1/lists/{encode_path_segment(list_id)}/import/items",
            params={"Fields": fields, "Purchase": purchase},
            json=cast(JSONValue, list(import_items)),
            mutation=True,
            charge=purchase,
        )

    def update_match(
        self,
        list_id: int,
        list_import_item_id: int,
        *,
        person_key: str | None = None,
        radar_id: str | None = None,
    ) -> ResponseEnvelope:
        """Update the selected person or property for an imported item.

        Args:
            list_id: Unique PropertyRadar import-list identifier.
            list_import_item_id: Unique imported-item identifier.
            person_key: Replacement PropertyRadar person key.
            radar_id: Replacement PropertyRadar property identifier.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            MutationNotAllowedError: If persistent mutations are disabled.
        """
        body: dict[str, JSONValue] = {}
        if person_key is not None:
            body["PersonKey"] = person_key
        if radar_id is not None:
            body["RadarID"] = radar_id
        return self._transport.request(
            "PATCH",
            (
                f"/v1/lists/{encode_path_segment(list_id)}/import/items/"
                f"{encode_path_segment(list_import_item_id)}"
            ),
            json=body,
            mutation=True,
        )

    def delete_match(
        self,
        list_id: int,
        list_import_item_id: int,
    ) -> ResponseEnvelope:
        """Delete one imported match from a list.

        Args:
            list_id: Unique PropertyRadar import-list identifier.
            list_import_item_id: Unique imported-item identifier.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            MutationNotAllowedError: If persistent mutations are disabled.
        """
        return self._transport.request(
            "DELETE",
            (
                f"/v1/lists/{encode_path_segment(list_id)}/import/items/"
                f"{encode_path_segment(list_import_item_id)}"
            ),
            mutation=True,
        )
