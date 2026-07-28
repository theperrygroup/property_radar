from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import httpx
import pytest

from property_radar import PropertyRadarClient
from property_radar.exceptions import (
    ChargeNotAllowedError,
    ForbiddenError,
    NotFoundError,
)

Handler = Callable[[httpx.Request], httpx.Response]


def make_client(
    handler: Handler,
    *,
    allow_charges: bool = False,
    max_retries: int = 0,
) -> tuple[PropertyRadarClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PropertyRadarClient(
        api_key="synthetic-token",  # pragma: allowlist secret
        allow_charges=allow_charges,
        max_retries=max_retries,
        http_client=http_client,
    )
    return client, http_client


def test_accounts_members_and_status_labels_requests() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path == "/v1/accounts/members":
            return httpx.Response(
                200,
                json={"results": [{"MemberKey": 101, "Status": "Active"}]},
            )
        return httpx.Response(
            200,
            json={"results": [{"Value": "8", "Label": "Synthetic lead"}]},
        )

    client, http_client = make_client(handler)
    members = client.accounts.members()
    labels = client.accounts.status_labels(layout="menu")

    assert members["results"] == [{"MemberKey": 101, "Status": "Active"}]
    assert labels["results"] == [{"Value": "8", "Label": "Synthetic lead"}]
    assert [
        (request.method, request.url.path, request.url.params.multi_items())
        for request in captured
    ] == [
        ("GET", "/v1/accounts/members", []),
        (
            "GET",
            "/v1/accounts/preferences/statuses",
            [("Layout", "menu")],
        ),
    ]
    assert all(request.content == b"" for request in captured)
    http_client.close()


@pytest.mark.parametrize(
    ("layout", "results"),
    [
        ("menu", [{"Value": "8", "Label": "Synthetic lead"}]),
        ("edit", {"label8": "Synthetic lead"}),
        ("compact", "Synthetic lead,Synthetic client"),
    ],
)
def test_status_label_layouts_preserve_their_documented_result_shape(
    layout: Literal["menu", "edit", "compact"],
    results: object,
) -> None:
    client, http_client = make_client(
        lambda _: httpx.Response(200, json={"results": results})
    )

    response = client.accounts.status_labels(layout=layout)

    assert response["results"] == results
    http_client.close()


def test_account_error_is_propagated() -> None:
    client, http_client = make_client(
        lambda _: httpx.Response(403, json={"message": "private vendor detail"})
    )

    with pytest.raises(ForbiddenError):
        client.accounts.members()

    http_client.close()


def test_document_preview_encodes_exact_query() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"results": [{"DocumentID": "D-SYNTHETIC"}], "totalCost": "0.00"},
        )

    client, http_client = make_client(handler)
    result = client.documents.get(
        "D-SYNTHETIC",
        fields=("DocumentID", "DocType"),
        radar_id="P-SYNTHETIC",
        dry_run=False,
    )

    assert result["results"] == [{"DocumentID": "D-SYNTHETIC"}]
    request = captured[0]
    assert request.method == "GET"
    assert request.url.path == "/v1/documents/D-SYNTHETIC"
    assert request.url.params.multi_items() == [
        ("Fields", "DocumentID,DocType"),
        ("RadarID", "P-SYNTHETIC"),
        ("DryRun", "0"),
        ("Purchase", "0"),
    ]
    assert request.content == b""
    http_client.close()


def test_document_purchase_requires_charge_opt_in_before_network_io() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"results": []})

    client, http_client = make_client(handler)

    with pytest.raises(ChargeNotAllowedError):
        client.documents.get("D-SYNTHETIC", purchase=True)

    assert captured == []
    http_client.close()


def test_enabled_document_purchase_sends_purchase_one() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"results": [{"DocumentID": "D-SYNTHETIC"}], "totalCost": "1.00"},
        )

    client, http_client = make_client(handler, allow_charges=True)
    client.documents.get("D-SYNTHETIC", purchase=True)

    assert captured[0].url.params.multi_items() == [("Purchase", "1")]
    http_client.close()


def test_document_error_is_propagated() -> None:
    client, http_client = make_client(
        lambda _: httpx.Response(404, json={"message": "private vendor detail"})
    )

    with pytest.raises(NotFoundError):
        client.documents.get("D-MISSING")

    http_client.close()
