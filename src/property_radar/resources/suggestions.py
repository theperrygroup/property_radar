"""Address and county suggestion API operations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from ..types import Criterion, JSONValue, ResponseEnvelope
from ._base import BaseResource


class SuggestionsResource(BaseResource):
    """Access PropertyRadar suggestion resources."""

    def site_addresses(
        self,
        suggestion_input: str | None = None,
        *,
        criteria: Sequence[Criterion] = (),
        limit: int = 255,
        start: int = 0,
    ) -> ResponseEnvelope:
        """Return site-address suggestions.

        Args:
            suggestion_input: Partial address text used to filter suggestions.
            criteria: Optional PropertyRadar criteria restricting suggestions.
            limit: Maximum number of suggestions to return.
            start: Zero-based result offset.

        Returns:
            The PropertyRadar response envelope.
        """
        return self._transport.request(
            "POST",
            "/v1/suggestions/SiteAddress",
            params={
                "SuggestionInput": suggestion_input,
                "Limit": limit,
                "Start": start,
            },
            json=_criteria_body(criteria),
            retryable=True,
        )

    def counties(
        self,
        suggestion_input: str | None = None,
        *,
        criteria: Sequence[Criterion] = (),
    ) -> ResponseEnvelope:
        """Return county and FIPS suggestions.

        Args:
            suggestion_input: Partial county text used to filter suggestions.
            criteria: Optional PropertyRadar criteria restricting suggestions.

        Returns:
            The PropertyRadar response envelope.
        """
        return self._transport.request(
            "POST",
            "/v1/suggestions/County",
            params={"SuggestionInput": suggestion_input},
            json=_criteria_body(criteria),
            retryable=True,
        )


def _criteria_body(criteria: Sequence[Criterion]) -> JSONValue:
    return cast(JSONValue, {"Criteria": list(criteria)})
