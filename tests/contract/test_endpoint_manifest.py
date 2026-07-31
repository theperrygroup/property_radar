import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Any

import property_radar.resources as resources

RESOURCE_CLASSES = {
    "accounts": resources.AccountsResource,
    "automations": resources.AutomationsResource,
    "documents": resources.DocumentsResource,
    "imports": resources.ImportsResource,
    "integrations": resources.IntegrationsResource,
    "lists": resources.ListsResource,
    "persons": resources.PersonsResource,
    "properties": resources.PropertiesResource,
    "suggestions": resources.SuggestionsResource,
}


def load_manifest() -> Mapping[str, Any]:
    manifest_path = files("property_radar").joinpath("endpoint_manifest.json")
    payload: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(payload, Mapping)
    return payload


def test_manifest_has_the_current_official_operation_set_and_source() -> None:
    manifest = load_manifest()
    operations = manifest["operations"]
    assert isinstance(operations, list)
    pairs = {(item["method"], item["path"]) for item in operations}

    assert manifest["openapi_version"] == "3.1.0"
    assert manifest["api_version"] == "5.2.0.0"
    assert manifest["inspected_at"] == "2026-07-31"
    assert manifest["source_sha256"] == (
        # pragma: allowlist nextline secret
        "f3808349c387cc1190ae41b24fec37962361b8149fde687179c84a72048e6bd4"
    )
    assert len(operations) == 37
    assert len(pairs) == 37


def test_every_manifest_operation_has_a_public_resource_method() -> None:
    operations = load_manifest()["operations"]
    assert isinstance(operations, list)

    for operation in operations:
        resource_name = operation["resource"]
        public_method = operation["public_method"]
        resource_class = RESOURCE_CLASSES[resource_name]
        assert callable(getattr(resource_class, public_method))
        typed_public_method = operation.get("typed_public_method")
        if typed_public_method is not None:
            assert callable(getattr(resource_class, typed_public_method))


def test_manifest_safety_classification_totals_are_stable() -> None:
    operations = load_manifest()["operations"]
    assert isinstance(operations, list)

    # Seventeen operations expose a Purchase parameter. Automation replacement
    # is the eighteenth charge-capable operation through PurchasePhone and
    # PurchaseEmail settings.
    assert sum(item["billable"] is True for item in operations) == 18
    assert sum(item["mutation"] is True for item in operations) == 11
