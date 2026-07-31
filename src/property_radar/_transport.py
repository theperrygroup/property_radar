"""Shared HTTP transport, response mapping, retries, and safety controls."""

from __future__ import annotations

import math
import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, TypeAlias, cast
from urllib.parse import urlsplit

import httpx

from .exceptions import (
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
from .types import JSONValue, ResponseEnvelope

DEFAULT_BASE_URL = "https://api.propertyradar.com"
DEFAULT_TIMEOUT = 30.0
MAX_RETRY_AFTER = 60.0
MAX_REQUEST_ID_LENGTH = 128
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9]+-[A-Za-z0-9]+-[A-Za-z0-9]+")

QueryScalar: TypeAlias = str | int | float | bool


@dataclass(frozen=True)
class RepeatedQuery:
    """Mark values that OpenAPI serializes as repeated query keys."""

    values: Sequence[QueryScalar]


QueryValue: TypeAlias = QueryScalar | Sequence[QueryScalar] | RepeatedQuery | None


class Transport:
    """One shared HTTP connection pool and PropertyRadar request boundary."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        token_provider: Callable[[], str] | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        allow_mutations: bool = False,
        allow_charges: bool = False,
        max_retries: int = 2,
        http_client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialize one transport and its safety policy."""
        if api_key is not None and token_provider is not None:
            raise ConfigurationError(
                "Provide either api_key or token_provider, not both."
            )
        if type(allow_mutations) is not bool:
            raise ConfigurationError("allow_mutations must be a boolean.")
        if type(allow_charges) is not bool:
            raise ConfigurationError("allow_charges must be a boolean.")
        if max_retries < 0:
            raise ConfigurationError("max_retries must be zero or greater.")
        clean_base_url = _validated_base_url(base_url)
        if token_provider is None:
            static_token = (
                api_key
                if api_key is not None
                else (
                    os.getenv("PROPERTY_RADAR_API_KEY")
                    or os.getenv("PROPERTYRADAR_API_KEY")
                )
            )
            if static_token is None or not static_token.strip():
                raise ConfigurationError(
                    "A PropertyRadar API key or token provider is required."
                )
            clean_token = static_token.strip()

            def static_provider() -> str:
                return clean_token

            self._token_provider = static_provider
        else:
            self._token_provider = token_provider
        self._base_url = clean_base_url
        self._allow_mutations = allow_mutations
        self._allow_charges = allow_charges
        self._max_retries = max_retries
        self._sleeper = sleeper
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)

    @property
    def is_closed(self) -> bool:
        """Return whether the underlying HTTP client has been closed."""
        return self._client.is_closed

    def __repr__(self) -> str:
        """Return configuration metadata without credentials."""
        return (
            f"{type(self).__name__}(base_url={self._base_url!r}, "
            f"allow_mutations={self._allow_mutations!r}, "
            f"allow_charges={self._allow_charges!r})"
        )

    def close(self) -> None:
        """Close an internally created HTTP client."""
        if self._owns_client and not self._client.is_closed:
            self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, QueryValue] | None = None,
        json: JSONValue | None = None,
        mutation: bool = False,
        charge: bool = False,
        retryable: bool | None = None,
    ) -> ResponseEnvelope:
        """Send one guarded API request and return its JSON envelope.

        Args:
            method: HTTP method.
            path: API path beginning with a slash.
            params: Vendor query parameters.
            json: Optional JSON request body.
            mutation: Whether the operation changes persistent external state.
            charge: Whether this invocation can consume quota or balance.
            retryable: Explicit safe-retry classification. GET/HEAD/OPTIONS are
                retryable by default when they are neither mutations nor paid.

        Returns:
            Parsed PropertyRadar response envelope.

        Raises:
            ConfigurationError: If a safety-classification flag is not an
                exact boolean.
            MutationNotAllowedError: If a mutation was not enabled.
            ChargeNotAllowedError: If a paid request was not enabled.
            PropertyRadarError: For transport, response, or API failures.
        """
        if type(mutation) is not bool:
            raise ConfigurationError("mutation must be a boolean.")
        if type(charge) is not bool:
            raise ConfigurationError("charge must be a boolean.")
        if retryable is not None and type(retryable) is not bool:
            raise ConfigurationError("retryable must be a boolean or None.")
        if mutation and not self._allow_mutations:
            raise MutationNotAllowedError(
                "Persistent PropertyRadar mutations are disabled."
            )
        if charge and not self._allow_charges:
            raise ChargeNotAllowedError("Paid PropertyRadar requests are disabled.")
        if self._client.is_closed:
            raise ConfigurationError("The PropertyRadar client is closed.")

        normalized_method = method.upper()
        is_retryable = (
            retryable
            if retryable is not None
            else normalized_method in {"GET", "HEAD", "OPTIONS"}
        )
        is_retryable = is_retryable and not mutation and not charge
        encoded_params = _encode_params(params)

        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.request(
                    normalized_method,
                    f"{self._base_url}{path}",
                    params=encoded_params,
                    json=json,
                    headers=self._headers(),
                )
            except httpx.TimeoutException:
                if is_retryable and attempt < self._max_retries:
                    self._sleeper(_backoff_delay(attempt))
                    continue
                raise RequestTimeoutError("PropertyRadar request timed out.") from None
            except httpx.RequestError:
                if is_retryable and attempt < self._max_retries:
                    self._sleeper(_backoff_delay(attempt))
                    continue
                raise NetworkError("PropertyRadar network request failed.") from None

            if (
                is_retryable
                and attempt < self._max_retries
                and (response.status_code == 429 or response.status_code >= 500)
            ):
                retry_after = _retry_after_seconds(response)
                self._sleeper(
                    retry_after if retry_after is not None else _backoff_delay(attempt)
                )
                continue
            return _decode_response(response)

        raise AssertionError(  # pragma: no cover - loop always returns or raises
            "request retry loop exhausted unexpectedly"
        )

    def _headers(self) -> dict[str, str]:
        provider_failed = False
        try:
            token = self._token_provider().strip()
        except Exception:
            provider_failed = True
            token = ""
        if provider_failed:
            raise ConfigurationError("The token provider failed.")
        if not token:
            raise ConfigurationError("The token provider returned an empty token.")
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "property-radar-python/0.3.0",
        }


def _encode_params(
    params: Mapping[str, QueryValue] | None,
) -> httpx.QueryParams:
    encoded: list[tuple[str, str | int | float | bool | None]] = []
    for key, value in (params or {}).items():
        if value is None:
            continue
        if isinstance(value, RepeatedQuery):
            encoded.extend((key, _stringify(item)) for item in value.values)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            encoded.append((key, ",".join(_stringify(item) for item in value)))
        else:
            encoded.append((key, _stringify(cast(QueryScalar, value))))
    return httpx.QueryParams(encoded)


def _stringify(value: QueryScalar) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _decode_response(response: httpx.Response) -> ResponseEnvelope:
    if 200 <= response.status_code < 300:
        if response.status_code in {204, 205} or not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError:
            raise InvalidResponseError(
                "PropertyRadar returned invalid JSON.",
                status_code=response.status_code,
                request_id=_request_id(response),
            ) from None
        if not isinstance(payload, dict):
            raise InvalidResponseError(
                "PropertyRadar returned a non-object JSON response.",
                status_code=response.status_code,
                request_id=_request_id(response),
            )
        return cast(ResponseEnvelope, payload)
    raise _http_error(response)


def _http_error(response: httpx.Response) -> PropertyRadarHTTPError:
    status = response.status_code
    request_id = _request_id(response)
    retry_after = _retry_after_seconds(response)
    error_type: type[PropertyRadarHTTPError]
    if status == 400:
        error_type = BadRequestError
    elif status == 401:
        error_type = AuthenticationError
    elif status == 402:
        error_type = PaymentRequiredError
    elif status == 403:
        error_type = ForbiddenError
    elif status == 404:
        error_type = NotFoundError
    elif status == 409:
        error_type = ConflictError
    elif status == 422:
        error_type = ValidationError
    elif status == 429:
        error_type = RateLimitError
    elif status >= 500:
        error_type = ServerError
    else:
        error_type = PropertyRadarHTTPError
    return error_type(
        f"PropertyRadar request failed with HTTP {status}.",
        status_code=status,
        request_id=request_id,
        retry_after=retry_after,
    )


def _request_id(response: httpx.Response) -> str | None:
    header_id = response.headers.get("X-Radar-Request-Id")
    sanitized_header_id = _sanitize_request_id(header_id)
    if sanitized_header_id is not None:
        return sanitized_header_id
    try:
        payload: Any = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        event_id = payload.get("eventid")
        return _sanitize_request_id(event_id)
    return None


def _sanitize_request_id(value: object) -> str | None:
    """Return a bounded correlation identifier without arbitrary text."""
    if (
        type(value) is not str
        or len(value) > MAX_REQUEST_ID_LENGTH
        or REQUEST_ID_PATTERN.fullmatch(value) is None
    ):
        return None
    return value


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        seconds = (parsed - datetime.now(timezone.utc)).total_seconds()
    if not math.isfinite(seconds):
        return None
    return min(MAX_RETRY_AFTER, max(0.0, seconds))


def _backoff_delay(attempt: int) -> float:
    delay = 0.5 * (2**attempt)
    return delay if delay < 8.0 else 8.0


def _validated_base_url(base_url: str) -> str:
    invalid = False
    try:
        parsed = urlsplit(base_url)
        hostname, _port = parsed.hostname, parsed.port
    except ValueError:
        invalid = True
        parsed = None
        hostname = None
    if (
        invalid
        or parsed is None
        or parsed.scheme.lower() != "https"
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or bool(parsed.query)
        or bool(parsed.fragment)
    ):
        raise ConfigurationError(
            "base_url must be an absolute HTTPS URL without credentials, "
            "a query, or a fragment."
        )
    return base_url.rstrip("/")
