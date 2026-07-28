"""Base class shared by all PropertyRadar resource clients."""

from urllib.parse import quote

from .._transport import Transport
from ..exceptions import ConfigurationError


def encode_path_segment(value: str | int) -> str:
    """Return one safely percent-encoded API path segment.

    Args:
        value: Vendor identifier that occupies exactly one URL path segment.

    Returns:
        The identifier encoded without permitting reserved path characters.

    Raises:
        ConfigurationError: If the identifier is empty or is an exact dot
            segment.
    """
    segment = str(value)
    if segment in {"", ".", ".."}:
        raise ConfigurationError(
            "API path segments must be non-empty and cannot be '.' or '..'."
        )
    return quote(segment, safe="")


class BaseResource:
    """Give one resource access to the top-level client's shared transport."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport
