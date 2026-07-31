"""Saved-list automation API operations."""

from __future__ import annotations

from typing import Literal

from ..exceptions import ConfigurationError
from ..types import JSONValue, ResponseEnvelope
from ._base import BaseResource, encode_path_segment

AutomationTriggers = Literal[
    "New Matches",
    "Status Changes",
    "New Matches,Status Changes",
]


class AutomationsResource(BaseResource):
    """Access PropertyRadar saved-list automations."""

    def get(self, list_id: int) -> ResponseEnvelope:
        """Return the automation configuration for a list.

        Args:
            list_id: Unique PropertyRadar list identifier.

        Returns:
            The PropertyRadar response envelope.
        """
        return self._transport.request(
            "GET",
            f"/v1/lists/{encode_path_segment(list_id)}/automations",
        )

    def update(
        self,
        list_id: int,
        *,
        confirm_full_replacement: bool = False,
        is_enabled: bool | None = None,
        triggers: AutomationTriggers | None = None,
        daily_email_member_ids: str | None = None,
        immediate_email_member_ids: str | None = None,
        export_to_webhook_ids: str | None = None,
        direct_mail_order_id: str | None = None,
        email_marketing_order_id: str | None = None,
        mobile_notification_member_ids: str | None = None,
        set_interest_level: int | None = None,
        set_status_level: int | None = None,
        add_to_lists: str | None = None,
        remove_from_lists: str | None = None,
        purchase_phone: bool | None = None,
        purchase_email: bool | None = None,
    ) -> ResponseEnvelope:
        """Fully replace the automation configuration for a list.

        PropertyRadar treats this PUT as a full replacement, not a partial
        update. Fetch the current configuration, modify it, and pass every value
        that must be retained. Omitted arguments are absent from the replacement
        body and may therefore clear existing vendor configuration.

        Args:
            list_id: Unique PropertyRadar list identifier.
            confirm_full_replacement: Must be exactly true to acknowledge that
                omitted settings can be cleared.
            is_enabled: Whether the replacement automation is enabled.
            triggers: Events that trigger the replacement automation.
            daily_email_member_ids: Comma-delimited daily-email member IDs.
            immediate_email_member_ids: Comma-delimited immediate-email IDs.
            export_to_webhook_ids: Comma-delimited webhook IDs.
            direct_mail_order_id: Direct-mail order identifier.
            email_marketing_order_id: Email-marketing order identifier.
            mobile_notification_member_ids: Comma-delimited mobile member IDs.
            set_interest_level: Interest level assigned by the automation.
            set_status_level: Status level assigned by the automation.
            add_to_lists: Comma-delimited destination list IDs.
            remove_from_lists: Comma-delimited list IDs to remove from.
            purchase_phone: Whether triggered records purchase phone data.
            purchase_email: Whether triggered records purchase email data.

        Returns:
            The PropertyRadar response envelope.

        Raises:
            ChargeNotAllowedError: If a purchase flag is true but charges are
                disabled.
            ConfigurationError: If full replacement is not acknowledged or no
                replacement fields are supplied.
            MutationNotAllowedError: If persistent mutations are disabled.
        """
        if confirm_full_replacement is not True:
            raise ConfigurationError(
                "Automation updates require explicit full-replacement confirmation."
            )
        for field_name, value in (
            ("is_enabled", is_enabled),
            ("purchase_phone", purchase_phone),
            ("purchase_email", purchase_email),
        ):
            if value is not None and type(value) is not bool:
                raise ConfigurationError(f"{field_name} must be a boolean or None.")
        body: dict[str, JSONValue] = {}
        if is_enabled is not None:
            body["isEnabled"] = int(is_enabled)
        if triggers is not None:
            body["Triggers"] = triggers
        if daily_email_member_ids is not None:
            body["DailyEmailMemberIDs"] = daily_email_member_ids
        if immediate_email_member_ids is not None:
            body["ImmediateEmailMemberIDs"] = immediate_email_member_ids
        if export_to_webhook_ids is not None:
            body["ExportToWebhookIDs"] = export_to_webhook_ids
        if direct_mail_order_id is not None:
            body["DirectMailOrderID"] = direct_mail_order_id
        if email_marketing_order_id is not None:
            body["EmailMarketingOrderID"] = email_marketing_order_id
        if mobile_notification_member_ids is not None:
            body["MobileNotificationMemberIDs"] = mobile_notification_member_ids
        if set_interest_level is not None:
            body["SetInterestLevel"] = set_interest_level
        if set_status_level is not None:
            body["SetStatusLevel"] = set_status_level
        if add_to_lists is not None:
            body["AddToLists"] = add_to_lists
        if remove_from_lists is not None:
            body["RemoveFromLists"] = remove_from_lists
        if purchase_phone is not None:
            body["PurchasePhone"] = int(purchase_phone)
        if purchase_email is not None:
            body["PurchaseEmail"] = int(purchase_email)
        if not body:
            raise ConfigurationError(
                "Automation replacement requires at least one configuration field."
            )
        return self._transport.request(
            "PUT",
            f"/v1/lists/{encode_path_segment(list_id)}/automations",
            json=body,
            mutation=True,
            charge=bool(purchase_phone or purchase_email),
        )
