"""Saved-list and list-item API operations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, cast

from .._transport import RepeatedQuery
from ..types import Criterion, JSONValue, ResponseEnvelope
from ._base import BaseResource, encode_path_segment

ListType = Literal["dynamic", "static", "import"]
ImportSource = Literal["file", "zapier", "api"]
ImportType = Literal["property", "person"]
SortDirection = Literal["asc", "desc"]


class ListsResource(BaseResource):
    """Access PropertyRadar saved-list resources."""

    def all(
        self,
        *,
        fields: Sequence[str] | None = None,
        list_type: ListType | None = None,
        is_monitored: bool | None = None,
        import_type: ImportType | None = None,
        group_name: str | None = None,
        display_order: int | None = None,
        limit: int = 1000,
        sort: str = "TotalCount",
        direction: SortDirection = "desc",
    ) -> ResponseEnvelope:
        """Return the account's saved lists.

        Args:
            fields: Vendor fields to include or suppress.
            list_type: Dynamic, static, or import list filter.
            is_monitored: Filter by monitoring state.
            import_type: Property- or person-focused import filter.
            group_name: List-group name filter.
            display_order: Display-order filter.
            limit: Maximum number of lists to return.
            sort: Vendor field used to sort results.
            direction: Ascending or descending sort direction.

        Returns:
            The PropertyRadar response envelope.
        """
        return self._transport.request(
            "GET",
            "/v1/lists",
            params={
                "Fields": fields,
                "ListType": list_type,
                "isMonitored": is_monitored,
                "ImportType": import_type,
                "GroupName": group_name,
                "DisplayOrder": display_order,
                "Limit": limit,
                "Sort": sort,
                "Dir": direction,
            },
        )

    def create(
        self,
        *,
        list_name: str,
        criteria: Sequence[Criterion] | None = None,
        list_type: ListType | None = None,
        is_monitored: bool | None = None,
        import_source: ImportSource | None = None,
        import_match_threshold: int | None = None,
        import_type: ImportType | None = None,
        import_contact_options: Mapping[str, bool] | None = None,
        group_name: str | None = None,
    ) -> ResponseEnvelope:
        """Create a saved list.

        Args:
            list_name: Display name for the list.
            criteria: Criteria used to populate a dynamic or static list.
            list_type: Dynamic, static, or import list type.
            is_monitored: Whether monitoring and automations are enabled.
            import_source: Source used to populate an import list.
            import_match_threshold: Match threshold for an import list.
            import_type: Property- or person-focused import type.
            import_contact_options: Vendor import-contact option mapping.
            group_name: List-group name.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            MutationNotAllowedError: If persistent mutations are disabled.
        """
        body: dict[str, JSONValue] = {"ListName": list_name}
        if criteria is not None:
            body["Criteria"] = cast(JSONValue, list(criteria))
        if list_type is not None:
            body["ListType"] = list_type
        if is_monitored is not None:
            body["isMonitored"] = int(is_monitored)
        if import_source is not None:
            body["ImportSource"] = import_source
        if import_match_threshold is not None:
            body["ImportMatchThreshold"] = import_match_threshold
        if import_type is not None:
            body["ImportType"] = import_type
        if import_contact_options is not None:
            body["ImportContactOptions"] = cast(
                JSONValue,
                dict(import_contact_options),
            )
        if group_name is not None:
            body["GroupName"] = group_name
        return self._transport.request(
            "POST",
            "/v1/lists",
            json=body,
            mutation=True,
        )

    def get(self, list_id: int) -> ResponseEnvelope:
        """Return one saved list.

        Args:
            list_id: Unique PropertyRadar list identifier.

        Returns:
            The PropertyRadar response envelope.
        """
        return self._transport.request(
            "GET",
            f"/v1/lists/{encode_path_segment(list_id)}",
        )

    def update(
        self,
        list_id: int,
        *,
        list_name: str | None = None,
        is_monitored: bool | None = None,
        import_match_threshold: int | None = None,
        import_type: ImportType | None = None,
        import_contact_options: Mapping[str, bool] | None = None,
        display_order: int | None = None,
    ) -> ResponseEnvelope:
        """Update the supplied fields on a saved list.

        Args:
            list_id: Unique PropertyRadar list identifier.
            list_name: Replacement display name.
            is_monitored: Replacement monitoring state.
            import_match_threshold: Replacement import match threshold.
            import_type: Replacement property- or person-focused import type.
            import_contact_options: Replacement import-contact option mapping.
            display_order: Replacement display order.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            MutationNotAllowedError: If persistent mutations are disabled.
        """
        body: dict[str, JSONValue] = {}
        if list_name is not None:
            body["ListName"] = list_name
        if is_monitored is not None:
            body["isMonitored"] = int(is_monitored)
        if import_match_threshold is not None:
            body["ImportMatchThreshold"] = import_match_threshold
        if import_type is not None:
            body["ImportType"] = import_type
        if import_contact_options is not None:
            body["ImportContactOptions"] = cast(
                JSONValue,
                dict(import_contact_options),
            )
        if display_order is not None:
            body["DisplayOrder"] = display_order
        return self._transport.request(
            "PATCH",
            f"/v1/lists/{encode_path_segment(list_id)}",
            json=body,
            mutation=True,
        )

    def delete(self, list_id: int) -> ResponseEnvelope:
        """Delete a saved list.

        Args:
            list_id: Unique PropertyRadar list identifier.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            MutationNotAllowedError: If persistent mutations are disabled.
        """
        return self._transport.request(
            "DELETE",
            f"/v1/lists/{encode_path_segment(list_id)}",
            mutation=True,
        )

    def items(
        self,
        list_id: int,
        *,
        start: int = 0,
        limit: int = 1000,
        interest_levels: Sequence[int] | None = None,
        status_level: int | None = None,
        has_photos: bool | None = None,
        has_notes: bool | None = None,
        has_analysis: bool | None = None,
        has_docs: bool | None = None,
        property_types: Sequence[str] | None = None,
        last_transfer_record_dates: Sequence[str] | None = None,
        added_since: str | None = None,
        most_recent_calls: Sequence[str] | None = None,
        most_recent_texts: Sequence[str] | None = None,
        most_recent_voicemails: Sequence[str] | None = None,
        most_recent_direct_mail: Sequence[str] | None = None,
        most_recent_emails: Sequence[str] | None = None,
    ) -> ResponseEnvelope:
        """Return properties saved to a list.

        Args:
            list_id: Unique PropertyRadar list identifier.
            start: Zero-based result offset.
            limit: Maximum number of items to return.
            interest_levels: Interest levels, serialized comma-delimited.
            status_level: Account-specific saved status level.
            has_photos: Filter by saved photos.
            has_notes: Filter by saved notes.
            has_analysis: Filter by saved analysis.
            has_docs: Filter by saved documents.
            property_types: Property types, serialized comma-delimited.
            last_transfer_record_dates: Relative-date filters.
            added_since: Date or timestamp after which the item was added.
            most_recent_calls: Most-recent-call relative-date filters.
            most_recent_texts: Most-recent-text relative-date filters.
            most_recent_voicemails: Most-recent-voicemail relative-date filters.
            most_recent_direct_mail: Most-recent-mail relative-date filters.
            most_recent_emails: Most-recent-email relative-date filters.

        Returns:
            The PropertyRadar response envelope.

        Note:
            Relative-date and activity arrays use repeated query keys, matching
            the official OpenAPI default. ``InterestLevel`` and ``PType`` are
            comma-delimited because the contract marks them ``explode: false``.
        """
        return self._transport.request(
            "GET",
            f"/v1/lists/{encode_path_segment(list_id)}/items",
            params={
                "Start": start,
                "Limit": limit,
                "InterestLevel": interest_levels,
                "StatusLevel": status_level,
                "hasPhotos": has_photos,
                "hasNotes": has_notes,
                "hasAnalysis": has_analysis,
                "hasDocs": has_docs,
                "PType": property_types,
                "LastTransferRecDate": (
                    None
                    if last_transfer_record_dates is None
                    else RepeatedQuery(last_transfer_record_dates)
                ),
                "AddedSince": added_since,
                "MostRecentCall": (
                    None
                    if most_recent_calls is None
                    else RepeatedQuery(most_recent_calls)
                ),
                "MostRecentText": (
                    None
                    if most_recent_texts is None
                    else RepeatedQuery(most_recent_texts)
                ),
                "MostRecentVoicemail": (
                    None
                    if most_recent_voicemails is None
                    else RepeatedQuery(most_recent_voicemails)
                ),
                "MostRecentDirectMail": (
                    None
                    if most_recent_direct_mail is None
                    else RepeatedQuery(most_recent_direct_mail)
                ),
                "MostRecentEmail": (
                    None
                    if most_recent_emails is None
                    else RepeatedQuery(most_recent_emails)
                ),
            },
        )

    def add_items(
        self,
        list_id: int,
        *,
        criteria: Sequence[Criterion],
    ) -> ResponseEnvelope:
        """Add properties matching criteria to a saved list.

        Args:
            list_id: Unique PropertyRadar list identifier.
            criteria: Criteria selecting the properties to add.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            MutationNotAllowedError: If persistent mutations are disabled.
        """
        return self._transport.request(
            "PUT",
            f"/v1/lists/{encode_path_segment(list_id)}/items",
            json={"Criteria": cast(JSONValue, list(criteria))},
            mutation=True,
        )

    def delete_item(self, list_id: int, radar_id: str) -> ResponseEnvelope:
        """Delete one property from a saved list.

        Args:
            list_id: Unique PropertyRadar list identifier.
            radar_id: Unique PropertyRadar property identifier.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            MutationNotAllowedError: If persistent mutations are disabled.
        """
        return self._transport.request(
            "DELETE",
            (
                f"/v1/lists/{encode_path_segment(list_id)}/items/"
                f"{encode_path_segment(radar_id)}"
            ),
            mutation=True,
        )
