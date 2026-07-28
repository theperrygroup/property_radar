import httpx

from property_radar import PropertyRadarClient


def test_client_resources_are_lazy_cached_and_share_transport() -> None:
    client = PropertyRadarClient(
        api_key="synthetic-token",  # pragma: allowlist secret
    )

    resources = [
        client.accounts,
        client.automations,
        client.documents,
        client.imports,
        client.integrations,
        client.lists,
        client.persons,
        client.properties,
        client.suggestions,
    ]

    assert client.accounts is resources[0]
    assert client.automations is resources[1]
    assert client.documents is resources[2]
    assert client.imports is resources[3]
    assert client.integrations is resources[4]
    assert client.lists is resources[5]
    assert client.persons is resources[6]
    assert client.properties is resources[7]
    assert client.suggestions is resources[8]
    assert all(resource._transport is client._transport for resource in resources)
    client.close()


def test_context_manager_closes_internally_owned_client() -> None:
    with PropertyRadarClient(
        api_key="synthetic-token"  # pragma: allowlist secret
    ) as client:
        assert not client._transport.is_closed
    assert client._transport.is_closed


def test_injected_http_client_is_not_closed() -> None:
    injected = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))
    )
    with PropertyRadarClient(
        api_key="synthetic-token",  # pragma: allowlist secret
        http_client=injected,
    ):
        pass
    assert not injected.is_closed
    injected.close()


def test_client_repr_redacts_token() -> None:
    client = PropertyRadarClient(
        api_key="never-show-this-token",  # pragma: allowlist secret
    )
    assert "never-show-this-token" not in repr(client)
    client.close()
