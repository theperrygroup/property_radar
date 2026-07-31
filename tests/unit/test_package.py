from importlib.resources import files

import property_radar


def test_installed_version_uses_package_metadata() -> None:
    assert property_radar.__version__ == "0.2.0"


def test_typing_marker_is_packaged() -> None:
    assert files("property_radar").joinpath("py.typed").is_file()


def test_transaction_history_public_exports_are_available() -> None:
    expected = {
        "PROPERTY_PERSON_IDENTITY_FIELDS",
        "TRANSACTION_HISTORY_CONTRACT",
        "TRANSACTION_HISTORY_FIELDS",
        "PropertyOwnershipRole",
        "PropertyPersonIdentityField",
        "ProviderPersonType",
        "TransactionBillingEvidence",
        "TransactionBillingStatus",
        "TransactionHistory",
        "TransactionHistoryField",
        "TransactionHistoryRecord",
        "TransactionHistoryStatus",
        "TransactionParty",
        "TransactionPartyKind",
        "parse_transaction_history",
    }

    assert expected.issubset(property_radar.__all__)
    assert all(hasattr(property_radar, name) for name in expected)
