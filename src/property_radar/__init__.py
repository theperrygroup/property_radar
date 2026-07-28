"""Public package for the PropertyRadar API client."""

from importlib.metadata import PackageNotFoundError, version

from .client import PropertyRadarClient
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
    PropertyRadarError,
    PropertyRadarHTTPError,
    RateLimitError,
    RequestTimeoutError,
    ServerError,
    ValidationError,
)
from .types import (
    Criterion,
    ImportItem,
    JSONDict,
    JSONValue,
    ResponseEnvelope,
    StatusLabelsResponse,
)

try:
    __version__ = version("property-radar")
except PackageNotFoundError:  # pragma: no cover - source tree without an install
    __version__ = "0+unknown"

__all__ = [
    "AuthenticationError",
    "BadRequestError",
    "ChargeNotAllowedError",
    "ConfigurationError",
    "ConflictError",
    "Criterion",
    "ForbiddenError",
    "ImportItem",
    "InvalidResponseError",
    "JSONDict",
    "JSONValue",
    "MutationNotAllowedError",
    "NetworkError",
    "NotFoundError",
    "PaymentRequiredError",
    "PropertyRadarClient",
    "PropertyRadarError",
    "PropertyRadarHTTPError",
    "RateLimitError",
    "RequestTimeoutError",
    "ResponseEnvelope",
    "ServerError",
    "StatusLabelsResponse",
    "ValidationError",
    "__version__",
]
