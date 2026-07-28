"""Typed and sanitized exceptions raised by the PropertyRadar client."""


class PropertyRadarError(Exception):
    """Base exception for client and API failures.

    Args:
        message: Sanitized failure description.
        status_code: HTTP status code, when a response was received.
        request_id: Vendor request identifier suitable for support correlation.
        retry_after: Suggested retry delay in seconds, when provided.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Initialize sanitized exception metadata."""
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id
        self.retry_after = retry_after


class ConfigurationError(PropertyRadarError):
    """Raised when client configuration is missing or contradictory."""


class MutationNotAllowedError(PropertyRadarError):
    """Raised before a persistent API mutation that was not enabled."""


class ChargeNotAllowedError(PropertyRadarError):
    """Raised before a paid API request that was not enabled."""


class PropertyRadarHTTPError(PropertyRadarError):
    """Base exception for non-successful HTTP responses."""


class BadRequestError(PropertyRadarHTTPError):
    """Raised for HTTP 400 responses."""


class AuthenticationError(PropertyRadarHTTPError):
    """Raised for invalid or expired credentials."""


class PaymentRequiredError(PropertyRadarHTTPError):
    """Raised when the account balance cannot cover a paid request."""


class ForbiddenError(PropertyRadarHTTPError):
    """Raised when valid credentials lack access to an operation."""


class NotFoundError(PropertyRadarHTTPError):
    """Raised for missing or account-invisible resources."""


class ConflictError(PropertyRadarHTTPError):
    """Raised for HTTP 409 responses."""


class ValidationError(PropertyRadarHTTPError):
    """Raised for HTTP 422 responses."""


class RateLimitError(PropertyRadarHTTPError):
    """Raised for HTTP 429 responses."""


class ServerError(PropertyRadarHTTPError):
    """Raised for HTTP 5xx responses."""


class NetworkError(PropertyRadarError):
    """Raised when the request cannot reach the API."""


class RequestTimeoutError(NetworkError):
    """Raised when an API request times out."""


class InvalidResponseError(PropertyRadarError):
    """Raised when a success response violates the JSON envelope contract."""
