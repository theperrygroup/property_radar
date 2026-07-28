"""Account and account-preference API operations."""

from typing import Literal, cast

from ..types import ResponseEnvelope, StatusLabelsResponse
from ._base import BaseResource


class AccountsResource(BaseResource):
    """Access PropertyRadar account resources."""

    def members(self) -> ResponseEnvelope:
        """Return the members and invitations visible to the account.

        Returns:
            The PropertyRadar response envelope containing account members.
        """
        return self._transport.request("GET", "/v1/accounts/members")

    def status_labels(
        self,
        *,
        layout: Literal["edit", "menu", "compact"] | None = None,
    ) -> StatusLabelsResponse:
        """Return the account's configured property status labels.

        Args:
            layout: Vendor response layout. When omitted, PropertyRadar uses
                its documented ``menu`` default.

        Returns:
            The PropertyRadar response envelope containing status labels.
        """
        response = self._transport.request(
            "GET", "/v1/accounts/preferences/statuses", params={"Layout": layout}
        )
        return cast(StatusLabelsResponse, response)
