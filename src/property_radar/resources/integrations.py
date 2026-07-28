"""Integration and webhook API operations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, cast
from urllib.parse import urlsplit

from ..exceptions import ConfigurationError
from ..types import JSONValue, ResponseEnvelope
from ._base import BaseResource, encode_path_segment

SortDirection = Literal["asc", "desc"]


class IntegrationsResource(BaseResource):
    """Access PropertyRadar integration resources."""

    def webhooks(
        self,
        *,
        fields: Sequence[str] | None = None,
        limit: int = 100,
        sort: str = "WebhookID",
        direction: SortDirection = "asc",
        start: int = 0,
    ) -> ResponseEnvelope:
        """Return active webhook integrations.

        Args:
            fields: Vendor fields to include or suppress.
            limit: Maximum number of webhooks to return.
            sort: Vendor field used to sort results.
            direction: Ascending or descending sort direction.
            start: Zero-based result offset.

        Returns:
            The PropertyRadar response envelope.
        """
        return self._transport.request(
            "GET",
            "/v1/integrations/webhooks",
            params={
                "Fields": fields,
                "Limit": limit,
                "Sort": sort,
                "Dir": direction,
                "Start": start,
            },
        )

    def create_webhook(
        self,
        *,
        hook_url: str,
        webhook_name: str,
        secret: str | None = None,
        list_ids: Sequence[int] | None = None,
    ) -> ResponseEnvelope:
        """Register a webhook integration.

        Args:
            hook_url: HTTPS destination called by PropertyRadar.
            webhook_name: Display name for the webhook.
            secret: Optional bearer secret sent only in the request body.
            list_ids: Lists for which automations should be created.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            ConfigurationError: If ``hook_url`` is not an absolute HTTPS URL
                without embedded credentials.
            MutationNotAllowedError: If persistent mutations are disabled.

        Note:
            The secret is passed directly to the guarded transport and is never
            retained on this resource or included in its representation.
        """
        _validate_webhook_url(hook_url)
        body: dict[str, JSONValue] = {
            "HookUrl": hook_url,
            "WebhookName": webhook_name,
        }
        if secret is not None:
            body["Secret"] = secret
        if list_ids is not None:
            body["Lists"] = cast(JSONValue, list(list_ids))
        return self._transport.request(
            "POST",
            "/v1/integrations/webhooks",
            json=body,
            mutation=True,
        )

    def delete_webhook(self, webhook_id: int) -> ResponseEnvelope:
        """Delete a webhook integration.

        Args:
            webhook_id: Unique PropertyRadar webhook identifier.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            MutationNotAllowedError: If persistent mutations are disabled.
        """
        return self._transport.request(
            "DELETE",
            f"/v1/integrations/webhooks/{encode_path_segment(webhook_id)}",
            mutation=True,
        )


def _validate_webhook_url(hook_url: str) -> None:
    invalid = False
    try:
        parsed = urlsplit(hook_url)
        hostname, _port = parsed.hostname, parsed.port
    except ValueError:
        invalid = True
        parsed = None
        hostname = None
    if invalid or parsed is None:
        raise ConfigurationError("Webhook URL is invalid.")
    if (
        parsed.scheme.lower() != "https"
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ConfigurationError(
            "Webhook URL must be absolute HTTPS without embedded credentials."
        )
