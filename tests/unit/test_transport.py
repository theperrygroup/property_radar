from __future__ import annotations

import traceback
from collections.abc import Callable

import httpx
import pytest

from property_radar._transport import MAX_RETRY_AFTER, RepeatedQuery, Transport
from property_radar.exceptions import (
    AuthenticationError,
    BadRequestError,
    ChargeNotAllowedError,
    ConfigurationError,
    ConflictError,
    ForbiddenError,
    InvalidResponseError,
    MutationNotAllowedError,
    NetworkError,
    NotFoundError,
    PaymentRequiredError,
    PropertyRadarHTTPError,
    RateLimitError,
    RequestTimeoutError,
    ServerError,
    ValidationError,
)

Handler = Callable[[httpx.Request], httpx.Response]


def make_transport(
    handler: Handler,
    *,
    api_key: str | None = "synthetic-token",
    token_provider: Callable[[], str] | None = None,
) -> tuple[Transport, httpx.Client]:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = Transport(
        api_key=api_key,
        token_provider=token_provider,
        http_client=client,
        max_retries=0,
    )
    return transport, client


def test_success_request_headers_and_query_encoding() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(201, json={"results": [{"RadarID": "P0000000"}]})

    transport, client = make_transport(handler)
    result = transport.request(
        "get",
        "/v1/example",
        params={
            "Fields": ["RadarID", "APN"],
            "Dates": RepeatedQuery(["Today", "Yesterday"]),
            "Enabled": True,
            "Disabled": False,
            "Limit": 5,
            "Omitted": None,
        },
    )

    assert result["results"] == [{"RadarID": "P0000000"}]
    request = captured[0]
    assert request.headers["Authorization"] == "Bearer synthetic-token"
    assert request.headers["Accept"] == "application/json"
    assert request.headers["User-Agent"] == "property-radar-python/0.1.0"
    assert request.url.params.multi_items() == [
        ("Fields", "RadarID,APN"),
        ("Dates", "Today"),
        ("Dates", "Yesterday"),
        ("Enabled", "1"),
        ("Disabled", "0"),
        ("Limit", "5"),
    ]
    client.close()


@pytest.mark.parametrize("status_code", [204, 205])
def test_empty_success_responses(status_code: int) -> None:
    transport, client = make_transport(
        lambda _: httpx.Response(status_code, content=b"")
    )
    assert transport.request("DELETE", "/v1/example") == {}
    client.close()


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(200, content=b"not-json"), "invalid JSON"),
        (httpx.Response(200, json=["not", "an", "object"]), "non-object"),
    ],
)
def test_invalid_success_payloads(
    response: httpx.Response,
    message: str,
) -> None:
    transport, client = make_transport(lambda _: response)
    with pytest.raises(InvalidResponseError, match=message):
        transport.request("GET", "/v1/example")
    client.close()


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (400, BadRequestError),
        (401, AuthenticationError),
        (402, PaymentRequiredError),
        (403, ForbiddenError),
        (404, NotFoundError),
        (409, ConflictError),
        (418, PropertyRadarHTTPError),
        (422, ValidationError),
        (429, RateLimitError),
        (503, ServerError),
    ],
)
def test_http_error_mapping(
    status_code: int,
    error_type: type[PropertyRadarHTTPError],
) -> None:
    transport, client = make_transport(
        lambda _: httpx.Response(
            status_code,
            json={
                "eventid": "synthetic-event",
                "message": "body must remain private",
            },
            headers={"Retry-After": "2.5"},
        )
    )

    with pytest.raises(error_type) as captured:
        transport.request("GET", "/v1/example")

    error = captured.value
    assert error.status_code == status_code
    assert error.request_id == "synthetic-event"
    assert error.retry_after == 2.5
    assert "body must remain private" not in str(error)
    client.close()


def test_request_id_header_wins_and_invalid_retry_after_is_ignored() -> None:
    transport, client = make_transport(
        lambda _: httpx.Response(
            400,
            json={"eventid": "body-id"},
            headers={
                "X-Radar-Request-Id": "header-id",
                "Retry-After": "not-a-date",
            },
        )
    )
    with pytest.raises(BadRequestError) as captured:
        transport.request("GET", "/v1/example")
    assert captured.value.request_id == "header-id"
    assert captured.value.retry_after is None
    client.close()


def test_http_date_retry_after_is_parsed() -> None:
    transport, client = make_transport(
        lambda _: httpx.Response(
            429,
            json={"error": "rate"},
            headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"},
        )
    )
    with pytest.raises(RateLimitError) as captured:
        transport.request("GET", "/v1/example")
    assert captured.value.retry_after == MAX_RETRY_AFTER
    client.close()


def test_safe_status_retry_honors_retry_after() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "1.25"})
        return httpx.Response(200, json={"results": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = Transport(
        api_key="synthetic-token",  # pragma: allowlist secret
        http_client=client,
        max_retries=1,
        sleeper=sleeps.append,
    )
    assert transport.request("GET", "/v1/example") == {"results": []}
    assert calls == 2
    assert sleeps == [1.25]
    client.close()


@pytest.mark.parametrize(
    ("retry_after", "expected_sleep"),
    [
        ("0", 0.0),
        ("inf", 0.5),
    ],
)
def test_retry_after_zero_is_honored_and_non_finite_is_ignored(
    retry_after: str,
    expected_sleep: float,
) -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": retry_after})
        return httpx.Response(200, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = Transport(
        api_key="synthetic-token",
        http_client=client,
        max_retries=1,
        sleeper=sleeps.append,
    )
    transport.request("GET", "/v1/example")

    assert sleeps == [expected_sleep]
    client.close()


def test_safe_network_and_timeout_retries_then_raise() -> None:
    network_calls = 0
    timeout_calls = 0
    sleeps: list[float] = []

    def network_handler(request: httpx.Request) -> httpx.Response:
        nonlocal network_calls
        network_calls += 1
        raise httpx.ConnectError("private network detail", request=request)

    network_client = httpx.Client(transport=httpx.MockTransport(network_handler))
    network_transport = Transport(
        api_key="synthetic-token",
        http_client=network_client,
        max_retries=1,
        sleeper=sleeps.append,
    )
    with pytest.raises(NetworkError, match="network request failed") as network_error:
        network_transport.request("GET", "/v1/example")
    assert network_calls == 2
    assert "private network detail" not in "".join(
        traceback.format_exception(network_error.value)
    )

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        nonlocal timeout_calls
        timeout_calls += 1
        raise httpx.ReadTimeout("private timeout detail", request=request)

    timeout_client = httpx.Client(transport=httpx.MockTransport(timeout_handler))
    timeout_transport = Transport(
        api_key="synthetic-token",
        http_client=timeout_client,
        max_retries=1,
        sleeper=sleeps.append,
    )
    with pytest.raises(RequestTimeoutError, match="timed out") as timeout_error:
        timeout_transport.request("GET", "/v1/example")
    assert timeout_calls == 2
    assert sleeps == [0.5, 0.5]
    assert "private timeout detail" not in "".join(
        traceback.format_exception(timeout_error.value)
    )
    network_client.close()
    timeout_client.close()


def test_mutation_and_paid_calls_are_not_retried() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": "temporary"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = Transport(
        api_key="synthetic-token",
        http_client=client,
        allow_mutations=True,
        allow_charges=True,
        max_retries=3,
        sleeper=lambda _: pytest.fail("unsafe request should not sleep"),
    )
    with pytest.raises(ServerError):
        transport.request("POST", "/v1/mutation", mutation=True, retryable=True)
    with pytest.raises(ServerError):
        transport.request("GET", "/v1/paid", charge=True, retryable=True)
    assert calls == 2
    client.close()


def test_read_like_post_can_be_explicitly_retried() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500)
        return httpx.Response(200, json={"results": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = Transport(
        api_key="synthetic-token",
        http_client=client,
        max_retries=1,
        sleeper=lambda _: None,
    )
    assert transport.request(
        "POST",
        "/v1/search",
        json={"Criteria": []},
        retryable=True,
    ) == {"results": []}
    assert calls == 2
    client.close()


def test_safety_guards_run_before_network_io() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    transport, client = make_transport(handler)
    with pytest.raises(MutationNotAllowedError, match="mutations are disabled"):
        transport.request("DELETE", "/v1/lists/1", mutation=True)
    with pytest.raises(ChargeNotAllowedError, match="requests are disabled"):
        transport.request("GET", "/v1/properties/P0000000", charge=True)
    assert calls == 0
    client.close()


def test_environment_and_token_provider_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tokens.append(request.headers["Authorization"])
        return httpx.Response(200, json={})

    monkeypatch.setenv("PROPERTY_RADAR_API_KEY", " environment-token ")
    environment_transport, environment_client = make_transport(handler, api_key=None)
    environment_transport.request("GET", "/v1/example")

    provider_transport, provider_client = make_transport(
        handler,
        api_key=None,
        token_provider=lambda: " provider-token ",
    )
    provider_transport.request("GET", "/v1/example")

    assert tokens == [
        "Bearer environment-token",
        "Bearer provider-token",
    ]
    environment_client.close()
    provider_client.close()


def test_configuration_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROPERTY_RADAR_API_KEY", raising=False)
    monkeypatch.delenv("PROPERTYRADAR_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="API key"):
        Transport()
    with pytest.raises(ConfigurationError, match="either api_key"):
        Transport(
            api_key="one",  # pragma: allowlist secret
            token_provider=lambda: "two",
        )
    with pytest.raises(ConfigurationError, match="zero or greater"):
        Transport(api_key="token", max_retries=-1)  # pragma: allowlist secret
    for invalid_base_url in (
        "api.propertyradar.com",
        "http://api.propertyradar.com",
        "https://user:password@api.propertyradar.com",  # pragma: allowlist secret
        "https://api.propertyradar.com:invalid-port",
        "https://api.propertyradar.com?credential=value",
        "https://api.propertyradar.com#fragment",
    ):
        with pytest.raises(ConfigurationError, match="absolute HTTPS URL"):
            Transport(api_key="token", base_url=invalid_base_url)


def test_empty_explicit_api_key_never_falls_back_to_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROPERTY_RADAR_API_KEY", "ambient-account-token")
    with pytest.raises(ConfigurationError, match="API key"):
        Transport(api_key=" ")


def test_legacy_environment_name_is_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PROPERTY_RADAR_API_KEY", raising=False)
    monkeypatch.setenv("PROPERTYRADAR_API_KEY", "legacy-token")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
        return httpx.Response(200, json={})

    transport, client = make_transport(handler, api_key=None)
    transport.request("GET", "/v1/example")
    assert seen == ["Bearer legacy-token"]
    client.close()


def empty_provider() -> str:
    return ""


def test_empty_token_provider() -> None:
    transport, client = make_transport(
        lambda _: httpx.Response(200, json={}),
        api_key=None,
        token_provider=empty_provider,
    )
    with pytest.raises(ConfigurationError, match="token provider"):
        transport.request("GET", "/v1/example")
    client.close()


def test_token_provider_failure_does_not_retain_sensitive_cause() -> None:
    private_detail = "private-provider-value"

    def failing_provider() -> str:
        raise RuntimeError(private_detail)

    transport, client = make_transport(
        lambda _: httpx.Response(200, json={}),
        api_key=None,
        token_provider=failing_provider,
    )
    with pytest.raises(ConfigurationError, match="token provider") as captured:
        transport.request("GET", "/v1/example")

    formatted = "".join(traceback.format_exception(captured.value))
    assert private_detail not in formatted
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    client.close()


def test_closed_internal_transport_rejects_requests() -> None:
    transport = Transport(api_key="synthetic-token", max_retries=0)
    transport.close()
    assert transport.is_closed
    with pytest.raises(ConfigurationError, match="client is closed"):
        transport.request("GET", "/v1/example")


def test_injected_client_lifecycle_remains_with_caller() -> None:
    transport, client = make_transport(lambda _: httpx.Response(200, json={}))
    transport.close()
    assert not client.is_closed
    client.close()


def test_transport_repr_redacts_token() -> None:
    transport = Transport(api_key="never-show-this-token")
    representation = repr(transport)
    assert "never-show-this-token" not in representation
    assert "api.propertyradar.com" in representation
    transport.close()
