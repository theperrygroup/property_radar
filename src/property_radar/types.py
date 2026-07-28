"""Shared public typing contracts for PropertyRadar requests and responses."""

from typing import TypeAlias, TypedDict

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONDict: TypeAlias = dict[str, JSONValue]


class _RequiredCriterion(TypedDict):
    """Required fields in a PropertyRadar criteria object."""

    name: str
    value: JSONValue


class Criterion(_RequiredCriterion, total=False):
    """A generic PropertyRadar criteria object.

    Criterion-specific values evolve independently in the vendor catalog, so
    this type preserves that value while enforcing the stable object shape.
    """

    menuLabels: list[str] | None
    chipLabel: str | None


class ResponseEnvelope(TypedDict, total=False):
    """Stable fields shared by documented PropertyRadar response envelopes."""

    results: list[JSONDict]
    totalCost: str
    quantityFreeRemaining: int
    resultCount: int
    totalResultCount: int
    maxDistanceMiles: int | float
    updateCount: int
    deleteCount: int


class StatusLabelsResponse(TypedDict, total=False):
    """Response shapes selected by the status-label ``Layout`` parameter."""

    results: list[JSONDict] | JSONDict | str


class ImportItem(TypedDict, total=False):
    """One item accepted by the list import matching endpoint."""

    FirstName: str
    LastName: str
    FullName: str
    Email: str
    EmailStatus: str
    Phone: str
    PhoneType: str
    PhoneStatus: str
    Address: str
    City: str
    State: str
    ZipFive: int
    County: str
    APN: str
