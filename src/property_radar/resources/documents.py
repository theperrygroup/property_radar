"""Recorded-document API operations."""

from collections.abc import Sequence

from ..types import ResponseEnvelope
from ._base import BaseResource, encode_path_segment


class DocumentsResource(BaseResource):
    """Access PropertyRadar recorded-document resources."""

    def get(
        self,
        document_id: str,
        *,
        fields: Sequence[str] | None = None,
        radar_id: str | None = None,
        dry_run: bool | None = None,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Return one recorded document in preview or purchased form.

        Args:
            document_id: PropertyRadar document identifier.
            fields: Fields or fieldsets to return. Values are encoded as one
                comma-delimited ``Fields`` query parameter.
            radar_id: Optional property identifier used to scope the document.
            dry_run: Optional vendor ``DryRun`` flag.
            purchase: Whether to purchase the returned record. The client must
                also be configured with ``allow_charges=True``.

        Returns:
            The PropertyRadar response envelope for the document.

        Raises:
            ChargeNotAllowedError: If ``purchase`` is true without the
                client-level charge opt-in.
        """
        return self._transport.request(
            "GET",
            f"/v1/documents/{encode_path_segment(document_id)}",
            params={
                "Fields": fields,
                "RadarID": radar_id,
                "DryRun": dry_run,
                "Purchase": purchase,
            },
            charge=purchase,
        )
