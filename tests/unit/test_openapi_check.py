import json
from pathlib import Path

import pytest

from property_radar.openapi_check import (
    compare_operations,
    load_openapi,
    main,
    manifest_operations,
    openapi_operations,
)


def test_manifest_operation_loader_returns_all_pairs() -> None:
    operations = manifest_operations()
    assert len(operations) == 37
    assert ("POST", "/v1/properties") in operations


def test_openapi_operation_extraction_ignores_non_operations() -> None:
    document = {
        "paths": {
            "/v1/example": {
                "parameters": [],
                "get": {"summary": "read"},
                "POST": {"summary": "search"},
            },
            42: {"get": {}},
            "/v1/invalid": "not-an-object",
        }
    }
    assert openapi_operations(document) == {
        ("GET", "/v1/example"),
        ("POST", "/v1/example"),
    }


def test_openapi_operation_extraction_requires_paths() -> None:
    with pytest.raises(ValueError, match="paths mapping"):
        openapi_operations({})


def test_compare_operations_reports_additions_and_removals() -> None:
    expected = {("GET", "/old"), ("POST", "/same")}
    actual = {("GET", "/new"), ("POST", "/same")}
    assert compare_operations(expected, actual) == (
        {("GET", "/new")},
        {("GET", "/old")},
    )


def test_load_openapi_from_file_and_main_success(tmp_path: Path) -> None:
    manifest = manifest_operations()
    paths: dict[str, dict[str, object]] = {}
    for method, path in manifest:
        paths.setdefault(path, {})[method.lower()] = {}
    spec_file = tmp_path / "openapi.json"
    spec_file.write_text(
        json.dumps({"openapi": "3.1.0", "paths": paths}),
        encoding="utf-8",
    )

    assert len(openapi_operations(load_openapi(spec_file=spec_file))) == 37
    assert main(["--spec-file", str(spec_file)]) == 0


def test_load_openapi_rejects_non_https_and_non_object(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must use HTTPS"):
        load_openapi(spec_url="http://example.test/openapi.json")

    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text('["not", "an", "object"]', encoding="utf-8")
    with pytest.raises(ValueError, match="not an object"):
        load_openapi(spec_file=invalid_file)

    malformed_file = tmp_path / "malformed.json"
    malformed_file.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_openapi(spec_file=malformed_file)


def test_main_reports_drift(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    spec_file = tmp_path / "drift.json"
    spec_file.write_text(
        '{"openapi":"3.1.0","paths":{"/v1/new":{"get":{}}}}',
        encoding="utf-8",
    )
    assert main(["--spec-file", str(spec_file)]) == 1
    output = capsys.readouterr().out
    assert "Operations added" in output
    assert "Operations absent" in output
