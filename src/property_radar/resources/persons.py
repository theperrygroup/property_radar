"""Person, event, relative, and contact API operations."""

from __future__ import annotations

from collections.abc import Sequence

from .._transport import QueryValue
from ..types import ResponseEnvelope
from ._base import BaseResource, encode_path_segment


class PersonsResource(BaseResource):
    """Access PropertyRadar person resources."""

    def bankruptcies(
        self,
        person_key: str,
        *,
        fields: Sequence[str] | None = None,
        limit: int = 100,
        start: int = 0,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Return bankruptcy records for a person.

        Args:
            person_key: Vendor identifier for the person.
            fields: Fields to include or suppress, encoded as one comma-delimited
                query value.
            limit: Maximum number of records to return.
            start: Zero-based result offset.
            purchase: Whether to purchase returned records. The default is a
                non-billable preview.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            ChargeNotAllowedError: If a purchase is requested without enabling
                charges on the client.
        """
        return self._event_records(
            person_key,
            "bankruptcies",
            fields=fields,
            limit=limit,
            start=start,
            purchase=purchase,
        )

    def divorces(
        self,
        person_key: str,
        *,
        fields: Sequence[str] | None = None,
        limit: int = 100,
        start: int = 0,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Return divorce records for a person.

        Args:
            person_key: Vendor identifier for the person.
            fields: Fields to include or suppress, encoded as one comma-delimited
                query value.
            limit: Maximum number of records to return.
            start: Zero-based result offset.
            purchase: Whether to purchase returned records. The default is a
                non-billable preview.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            ChargeNotAllowedError: If a purchase is requested without enabling
                charges on the client.
        """
        return self._event_records(
            person_key,
            "divorces",
            fields=fields,
            limit=limit,
            start=start,
            purchase=purchase,
        )

    def liens(
        self,
        person_key: str,
        *,
        fields: Sequence[str] | None = None,
        limit: int = 500,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Return lien records for a person.

        Args:
            person_key: Vendor identifier for the person.
            fields: Fields to include or suppress, encoded as one comma-delimited
                query value.
            limit: Maximum number of records to return.
            purchase: Whether to purchase returned records. The default is a
                non-billable preview.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            ChargeNotAllowedError: If a purchase is requested without enabling
                charges on the client.
        """
        return self._event_records(
            person_key,
            "liens",
            fields=fields,
            limit=limit,
            start=None,
            purchase=purchase,
        )

    def probates(
        self,
        person_key: str,
        *,
        fields: Sequence[str] | None = None,
        limit: int = 100,
        start: int = 0,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Return probate records for a person.

        Args:
            person_key: Vendor identifier for the person.
            fields: Fields to include or suppress, encoded as one comma-delimited
                query value.
            limit: Maximum number of records to return.
            start: Zero-based result offset.
            purchase: Whether to purchase returned records. The default is a
                non-billable preview.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            ChargeNotAllowedError: If a purchase is requested without enabling
                charges on the client.
        """
        return self._event_records(
            person_key,
            "probates",
            fields=fields,
            limit=limit,
            start=start,
            purchase=purchase,
        )

    def relatives(
        self,
        person_key: str,
        *,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Return relatives for a person.

        Args:
            person_key: Vendor identifier for the person.
            purchase: Whether to purchase returned records. The default is a
                non-billable preview.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            ChargeNotAllowedError: If a purchase is requested without enabling
                charges on the client.
        """
        return self._transport.request(
            "GET",
            f"/v1/persons/{encode_path_segment(person_key)}/relatives",
            params={"Purchase": purchase},
            charge=purchase,
        )

    def phone(
        self,
        person_key: str,
        *,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Preview or purchase a phone lookup for a person.

        Args:
            person_key: Vendor identifier for the person.
            purchase: Whether to purchase the lookup. The default is a
                non-billable preview.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            ChargeNotAllowedError: If a purchase is requested without enabling
                charges on the client.
        """
        return self._contact_lookup(person_key, "Phone", purchase=purchase)

    def email(
        self,
        person_key: str,
        *,
        purchase: bool = False,
    ) -> ResponseEnvelope:
        """Preview or purchase an email lookup for a person.

        Args:
            person_key: Vendor identifier for the person.
            purchase: Whether to purchase the lookup. The default is a
                non-billable preview.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            ChargeNotAllowedError: If a purchase is requested without enabling
                charges on the client.
        """
        return self._contact_lookup(person_key, "Email", purchase=purchase)

    def _event_records(
        self,
        person_key: str,
        endpoint: str,
        *,
        fields: Sequence[str] | None,
        limit: int,
        start: int | None,
        purchase: bool,
    ) -> ResponseEnvelope:
        params: dict[str, QueryValue] = {
            "Fields": fields,
            "Limit": limit,
            "Start": start,
            "Purchase": purchase,
        }
        return self._transport.request(
            "GET",
            f"/v1/persons/{encode_path_segment(person_key)}/{endpoint}",
            params=params,
            charge=purchase,
        )

    def _contact_lookup(
        self,
        person_key: str,
        endpoint: str,
        *,
        purchase: bool,
    ) -> ResponseEnvelope:
        return self._transport.request(
            "POST",
            f"/v1/persons/{encode_path_segment(person_key)}/{endpoint}",
            params={"Purchase": purchase},
            charge=purchase,
            retryable=not purchase,
        )
