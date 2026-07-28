"""Resource clients exposed by :class:`property_radar.PropertyRadarClient`."""

from .accounts import AccountsResource
from .automations import AutomationsResource
from .documents import DocumentsResource
from .imports import ImportsResource
from .integrations import IntegrationsResource
from .lists import ListsResource
from .persons import PersonsResource
from .properties import PropertiesResource
from .suggestions import SuggestionsResource

__all__ = [
    "AccountsResource",
    "AutomationsResource",
    "DocumentsResource",
    "ImportsResource",
    "IntegrationsResource",
    "ListsResource",
    "PersonsResource",
    "PropertiesResource",
    "SuggestionsResource",
]
