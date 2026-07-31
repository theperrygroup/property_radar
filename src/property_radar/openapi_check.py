"""Compare the checked-in endpoint manifest with an official OpenAPI document."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeAlias, cast

DEFAULT_SPEC_URL = "https://developers.propertyradar.com/_spec/api.json"
HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"}
)
Operation: TypeAlias = tuple[str, str]


def _load_manifest() -> Mapping[str, Any]:
    """Load the packaged endpoint manifest."""
    manifest_file = files("property_radar").joinpath("endpoint_manifest.json")
    payload: Any = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Endpoint manifest is not an object.")
    return cast(Mapping[str, Any], payload)


def manifest_operations() -> set[Operation]:
    """Load documented method/path pairs from the packaged endpoint manifest."""
    payload = _load_manifest()
    operations: Any = payload["operations"]
    return {
        (str(item["method"]).upper(), str(item["path"]))
        for item in operations
        if isinstance(item, Mapping)
    }


def openapi_operations(document: Mapping[str, Any]) -> set[Operation]:
    """Extract method/path pairs from an OpenAPI mapping."""
    paths = document.get("paths")
    if not isinstance(paths, Mapping):
        raise ValueError("OpenAPI document does not contain a paths mapping.")
    operations: set[Operation] = set()
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, Mapping):
            continue
        for method in path_item:
            normalized = str(method).upper()
            if normalized in HTTP_METHODS:
                operations.add((normalized, path))
    return operations


def _load_openapi_bytes(
    *,
    spec_url: str = DEFAULT_SPEC_URL,
    spec_file: Path | None = None,
) -> bytes:
    """Load raw OpenAPI bytes from HTTPS or an explicit local file."""
    if spec_file is not None:
        return spec_file.read_bytes()
    if not spec_url.startswith("https://"):
        raise ValueError("The remote OpenAPI URL must use HTTPS.")
    request = urllib.request.Request(
        spec_url,
        headers={"User-Agent": "property-radar-openapi-check/0.3.0"},
    )
    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:
        return cast(bytes, response.read())


def _decode_openapi(raw: bytes) -> Mapping[str, Any]:
    """Decode one raw OpenAPI JSON object."""
    try:
        document: Any = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("OpenAPI content is not valid JSON.") from exc
    if not isinstance(document, Mapping):
        raise ValueError("OpenAPI content is not an object.")
    return cast(Mapping[str, Any], document)


def load_openapi(
    *,
    spec_url: str = DEFAULT_SPEC_URL,
    spec_file: Path | None = None,
) -> Mapping[str, Any]:
    """Load an OpenAPI document from an HTTPS URL or explicit local file."""
    return _decode_openapi(_load_openapi_bytes(spec_url=spec_url, spec_file=spec_file))


def source_metadata_mismatches(
    manifest: Mapping[str, Any],
    document: Mapping[str, Any],
    raw: bytes,
) -> tuple[str, ...]:
    """Return stable reason codes for source metadata drift."""
    mismatches: list[str] = []
    if manifest.get("openapi_version") != document.get("openapi"):
        mismatches.append("openapi_version")
    info = document.get("info")
    api_version = info.get("version") if isinstance(info, Mapping) else None
    if manifest.get("api_version") != api_version:
        mismatches.append("api_version")
    if manifest.get("source_sha256") != hashlib.sha256(raw).hexdigest():
        mismatches.append("source_sha256")
    return tuple(mismatches)


def compare_operations(
    expected: set[Operation],
    actual: set[Operation],
) -> tuple[set[Operation], set[Operation]]:
    """Return operations missing from and added to the checked-in manifest."""
    return actual - expected, expected - actual


def _format_operations(operations: set[Operation]) -> str:
    return "\n".join(f"  {method} {path}" for method, path in sorted(operations))


def main(argv: list[str] | None = None) -> int:
    """Run the endpoint drift check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec-url", default=DEFAULT_SPEC_URL)
    parser.add_argument("--spec-file", type=Path)
    arguments = parser.parse_args(argv)

    manifest = _load_manifest()
    raw = _load_openapi_bytes(
        spec_url=arguments.spec_url,
        spec_file=arguments.spec_file,
    )
    document = _decode_openapi(raw)
    expected = manifest_operations()
    actual = openapi_operations(document)
    added, removed = compare_operations(expected, actual)
    metadata_mismatches = (
        ()
        if arguments.spec_file is not None
        else source_metadata_mismatches(manifest, document, raw)
    )
    if added or removed or metadata_mismatches:
        if added:
            print("Operations added by the official specification:")
            print(_format_operations(added))
        if removed:
            print("Operations absent from the official specification:")
            print(_format_operations(removed))
        if metadata_mismatches:
            print("Official specification metadata changed:")
            print("\n".join(f"  {reason}" for reason in metadata_mismatches))
        return 1

    suffix = " and stored source metadata." if arguments.spec_file is None else "."
    print(f"Endpoint manifest matches {len(actual)} official operations{suffix}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through console entry
    sys.exit(main())
