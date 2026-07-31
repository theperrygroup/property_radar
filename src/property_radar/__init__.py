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
from .transaction_history import (
    PROPERTY_PERSON_IDENTITY_FIELDS,
    TRANSACTION_HISTORY_CONTRACT,
    TRANSACTION_HISTORY_FIELDS,
    PropertyOwnershipRole,
    PropertyPersonIdentityField,
    ProviderPersonType,
    TransactionBillingEvidence,
    TransactionBillingStatus,
    TransactionHistory,
    TransactionHistoryField,
    TransactionHistoryRecord,
    TransactionHistoryStatus,
    TransactionParty,
    TransactionPartyKind,
    parse_transaction_history,
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
    "PROPERTY_PERSON_IDENTITY_FIELDS",
    "TRANSACTION_HISTORY_CONTRACT",
    "TRANSACTION_HISTORY_FIELDS",
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
    "PropertyOwnershipRole",
    "PropertyPersonIdentityField",
    "PropertyRadarClient",
    "PropertyRadarError",
    "PropertyRadarHTTPError",
    "ProviderPersonType",
    "RateLimitError",
    "RequestTimeoutError",
    "ResponseEnvelope",
    "ServerError",
    "StatusLabelsResponse",
    "TransactionBillingEvidence",
    "TransactionBillingStatus",
    "TransactionHistory",
    "TransactionHistoryField",
    "TransactionHistoryRecord",
    "TransactionHistoryStatus",
    "TransactionParty",
    "TransactionPartyKind",
    "ValidationError",
    "__version__",
    "parse_transaction_history",
]
