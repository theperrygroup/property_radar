from importlib.resources import files

import property_radar


def test_installed_version_uses_package_metadata() -> None:
    assert property_radar.__version__ == "0.1.0"


def test_typing_marker_is_packaged() -> None:
    assert files("property_radar").joinpath("py.typed").is_file()
