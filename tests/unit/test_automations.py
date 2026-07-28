from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from property_radar import PropertyRadarClient
from property_radar.exceptions import (
    ChargeNotAllowedError,
    ConfigurationError,
    MutationNotAllowedError,
    ServerError,
)

Handler = Callable[[httpx.Request], httpx.Response]


def make_client(
    handler: Handler,
    *,
    allow_mutations: bool = False,
    allow_charges: bool = False,
    max_retries: int = 0,
) -> tuple[PropertyRadarClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PropertyRadarClient(
        api_key="synthetic-token",
        allow_mutations=allow_mutations,
        allow_charges=allow_charges,
        max_retries=max_retries,
        http_client=http_client,
    )
    return client, http_client


def request_body(request: httpx.Request) -> object:
    payload: object = json.loads(request.content)
    return payload


def test_both_automation_operations_construct_exact_requests() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    client, http_client = make_client(handler, allow_mutations=True)
    client.automations.get(1001)
    client.automations.update(
        1001,
        confirm_full_replacement=True,
        is_enabled=True,
        triggers="New Matches,Status Changes",
        daily_email_member_ids="11,12",
        immediate_email_member_ids="13",
        export_to_webhook_ids="21,22",
        direct_mail_order_id="31",
        email_marketing_order_id="41",
        mobile_notification_member_ids="14,15",
        set_interest_level=4,
        set_status_level=6,
        add_to_lists="2001,2002",
        remove_from_lists="2003",
        purchase_phone=False,
        purchase_email=False,
    )

    assert [(request.method, request.url.path) for request in captured] == [
        ("GET", "/v1/lists/1001/automations"),
        ("PUT", "/v1/lists/1001/automations"),
    ]
    assert request_body(captured[1]) == {
        "isEnabled": 1,
        "Triggers": "New Matches,Status Changes",
        "DailyEmailMemberIDs": "11,12",
        "ImmediateEmailMemberIDs": "13",
        "ExportToWebhookIDs": "21,22",
        "DirectMailOrderID": "31",
        "EmailMarketingOrderID": "41",
        "MobileNotificationMemberIDs": "14,15",
        "SetInterestLevel": 4,
        "SetStatusLevel": 6,
        "AddToLists": "2001,2002",
        "RemoveFromLists": "2003",
        "PurchasePhone": 0,
        "PurchaseEmail": 0,
    }
    http_client.close()


def test_update_is_a_full_replacement_and_omits_unspecified_fields() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    client, http_client = make_client(handler, allow_mutations=True)
    client.automations.update(
        1002,
        confirm_full_replacement=True,
        is_enabled=False,
        purchase_phone=False,
    )

    assert request_body(captured[0]) == {
        "isEnabled": 0,
        "PurchasePhone": 0,
    }
    assert "full replacement" in (client.automations.update.__doc__ or "").lower()
    assert "may therefore clear" in (client.automations.update.__doc__ or "")
    http_client.close()


def test_automation_update_is_blocked_before_network_io() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client, http_client = make_client(handler)
    with pytest.raises(MutationNotAllowedError):
        client.automations.update(
            1003,
            confirm_full_replacement=True,
            is_enabled=True,
        )

    assert calls == 0
    http_client.close()


@pytest.mark.parametrize(
    ("purchase_phone", "purchase_email"),
    [(True, False), (False, True), (True, True)],
)
def test_any_truthy_automation_purchase_flag_requires_charge_opt_in(
    purchase_phone: bool,
    purchase_email: bool,
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client, http_client = make_client(handler, allow_mutations=True)
    with pytest.raises(ChargeNotAllowedError):
        client.automations.update(
            1004,
            confirm_full_replacement=True,
            purchase_phone=purchase_phone,
            purchase_email=purchase_email,
        )

    assert calls == 0
    http_client.close()


def test_charged_automation_mutation_is_never_retried() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={})

    client, http_client = make_client(
        handler,
        allow_mutations=True,
        allow_charges=True,
        max_retries=3,
    )
    with pytest.raises(ServerError):
        client.automations.update(
            1005,
            confirm_full_replacement=True,
            is_enabled=True,
            purchase_email=True,
        )

    assert calls == 1
    http_client.close()


def test_automation_replacement_requires_acknowledgement_and_content() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client, http_client = make_client(handler, allow_mutations=True)
    with pytest.raises(ConfigurationError, match="explicit full-replacement"):
        client.automations.update(1006, is_enabled=True)
    with pytest.raises(ConfigurationError, match="at least one"):
        client.automations.update(1006, confirm_full_replacement=True)

    assert calls == 0
    http_client.close()
