from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from property_radar import PropertyRadarClient
from property_radar.exceptions import MutationNotAllowedError, ServerError
from property_radar.types import Criterion

Handler = Callable[[httpx.Request], httpx.Response]
ClientOperation = Callable[[PropertyRadarClient], object]


def make_client(
    handler: Handler,
    *,
    allow_mutations: bool = False,
    max_retries: int = 0,
) -> tuple[PropertyRadarClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PropertyRadarClient(
        api_key="synthetic-token",
        allow_mutations=allow_mutations,
        max_retries=max_retries,
        http_client=http_client,
    )
    return client, http_client


def request_body(request: httpx.Request) -> object:
    payload: object = json.loads(request.content)
    return payload


def test_all_eight_list_operations_construct_exact_requests() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    client, http_client = make_client(handler, allow_mutations=True)
    criteria: list[Criterion] = [{"name": "RadarID", "value": ["PTEST0001"]}]

    client.lists.all(
        fields=["ListID", "-GroupName"],
        list_type="dynamic",
        is_monitored=False,
        import_type="property",
        group_name="Synthetic Group",
        display_order=7,
        limit=25,
        sort="ListName",
        direction="asc",
    )
    client.lists.create(
        list_name="Synthetic Dynamic",
        criteria=criteria,
        list_type="dynamic",
        is_monitored=True,
        group_name="Synthetic Group",
    )
    client.lists.get(101)
    client.lists.update(
        101,
        list_name="Synthetic Import",
        is_monitored=False,
        import_match_threshold=82,
        import_type="person",
        import_contact_options={
            "add_as_primary_contact": True,
            "set_as_primary_contact": False,
        },
        display_order=4,
    )
    client.lists.delete(101)
    client.lists.items(
        101,
        start=5,
        limit=20,
        interest_levels=[1, 3],
        status_level=2,
        has_photos=True,
        has_notes=False,
        has_analysis=True,
        has_docs=False,
        property_types=["SFR", "CND"],
        last_transfer_record_dates=["Today", "Yesterday"],
        added_since="2026-01-01T00:00:00Z",
        most_recent_calls=["This Week", "None"],
        most_recent_texts=["Last 7 Days", "None"],
        most_recent_voicemails=["Last 30 Days", "None"],
        most_recent_direct_mail=["This Month", "Last Month"],
        most_recent_emails=["This Year", "None"],
    )
    client.lists.add_items(101, criteria=criteria)
    client.lists.delete_item(101, "PTEST0001")

    assert [(request.method, request.url.path) for request in captured] == [
        ("GET", "/v1/lists"),
        ("POST", "/v1/lists"),
        ("GET", "/v1/lists/101"),
        ("PATCH", "/v1/lists/101"),
        ("DELETE", "/v1/lists/101"),
        ("GET", "/v1/lists/101/items"),
        ("PUT", "/v1/lists/101/items"),
        ("DELETE", "/v1/lists/101/items/PTEST0001"),
    ]
    assert captured[0].url.params.multi_items() == [
        ("Fields", "ListID,-GroupName"),
        ("ListType", "dynamic"),
        ("isMonitored", "0"),
        ("ImportType", "property"),
        ("GroupName", "Synthetic Group"),
        ("DisplayOrder", "7"),
        ("Limit", "25"),
        ("Sort", "ListName"),
        ("Dir", "asc"),
    ]
    assert request_body(captured[1]) == {
        "Criteria": criteria,
        "ListName": "Synthetic Dynamic",
        "ListType": "dynamic",
        "isMonitored": 1,
        "GroupName": "Synthetic Group",
    }
    assert request_body(captured[3]) == {
        "ListName": "Synthetic Import",
        "isMonitored": 0,
        "ImportMatchThreshold": 82,
        "ImportType": "person",
        "ImportContactOptions": {
            "add_as_primary_contact": True,
            "set_as_primary_contact": False,
        },
        "DisplayOrder": 4,
    }
    assert captured[5].url.params.multi_items() == [
        ("Start", "5"),
        ("Limit", "20"),
        ("InterestLevel", "1,3"),
        ("StatusLevel", "2"),
        ("hasPhotos", "1"),
        ("hasNotes", "0"),
        ("hasAnalysis", "1"),
        ("hasDocs", "0"),
        ("PType", "SFR,CND"),
        ("LastTransferRecDate", "Today"),
        ("LastTransferRecDate", "Yesterday"),
        ("AddedSince", "2026-01-01T00:00:00Z"),
        ("MostRecentCall", "This Week"),
        ("MostRecentCall", "None"),
        ("MostRecentText", "Last 7 Days"),
        ("MostRecentText", "None"),
        ("MostRecentVoicemail", "Last 30 Days"),
        ("MostRecentVoicemail", "None"),
        ("MostRecentDirectMail", "This Month"),
        ("MostRecentDirectMail", "Last Month"),
        ("MostRecentEmail", "This Year"),
        ("MostRecentEmail", "None"),
    ]
    assert request_body(captured[6]) == {"Criteria": criteria}
    http_client.close()


def test_create_import_list_preserves_casing_and_omits_unset_values() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    client, http_client = make_client(handler, allow_mutations=True)
    client.lists.create(
        list_name="Synthetic Import",
        list_type="import",
        import_source="api",
        import_match_threshold=77,
        import_type="property",
        import_contact_options={"add_as_primary_contact": False},
    )

    assert request_body(captured[0]) == {
        "ListName": "Synthetic Import",
        "ListType": "import",
        "ImportSource": "api",
        "ImportMatchThreshold": 77,
        "ImportType": "property",
        "ImportContactOptions": {"add_as_primary_contact": False},
    }
    http_client.close()


def test_update_omits_every_unset_field() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    client, http_client = make_client(handler, allow_mutations=True)
    client.lists.update(202, is_monitored=False)

    assert request_body(captured[0]) == {"isMonitored": 0}
    http_client.close()


def test_every_list_mutation_is_blocked_before_network_io() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client, http_client = make_client(handler)
    criteria: list[Criterion] = [{"name": "RadarID", "value": ["PTEST0002"]}]
    operations: list[ClientOperation] = [
        lambda value: value.lists.create(list_name="Blocked"),
        lambda value: value.lists.update(202, list_name="Blocked"),
        lambda value: value.lists.delete(202),
        lambda value: value.lists.add_items(202, criteria=criteria),
        lambda value: value.lists.delete_item(202, "PTEST0002"),
    ]

    for operation in operations:
        with pytest.raises(MutationNotAllowedError):
            operation(client)

    assert calls == 0
    http_client.close()


@pytest.mark.parametrize(
    "operation",
    [
        lambda client: client.lists.create(list_name="Synthetic"),
        lambda client: client.lists.update(303, list_name="Synthetic"),
        lambda client: client.lists.delete(303),
        lambda client: client.lists.add_items(
            303,
            criteria=[{"name": "RadarID", "value": ["PTEST0003"]}],
        ),
        lambda client: client.lists.delete_item(303, "PTEST0003"),
    ],
)
def test_list_mutations_are_never_retried(operation: ClientOperation) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={})

    client, http_client = make_client(
        handler,
        allow_mutations=True,
        max_retries=3,
    )
    with pytest.raises(ServerError):
        operation(client)

    assert calls == 1
    http_client.close()
