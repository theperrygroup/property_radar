"""Load typed synthetic-ID transaction evidence in preview mode.

Both requests send ``Purchase=0`` and are not billed. The person identity
fields are paid fields, so a persons preview can report its owners without
returning them. With ``property_persons_purchase_requested=False`` the
history then has ``current_owners=None`` and ``current_owners_withheld=True``.
This mirrors the transactions preview and has not been probed live.
"""

from property_radar import (
    PROPERTY_PERSON_IDENTITY_FIELDS,
    PropertyRadarClient,
)


def main() -> None:
    """Request preview evidence and print only non-personal metadata."""
    radar_id = "P-SYNTHETIC"
    with PropertyRadarClient() as client:
        persons = client.properties.persons(
            radar_id,
            fields=PROPERTY_PERSON_IDENTITY_FIELDS,
            purchase=False,
        )
        history = client.properties.transaction_history(
            radar_id,
            filter_by="CurrentOwner",
            purchase=False,
            property_persons=persons,
            property_persons_purchase_requested=False,
        )

    if history.purchase_requested is not False:
        raise RuntimeError("Preview-only transaction request invariant failed.")

    print("Preview transaction evidence parsed successfully.")
    print(f"Transaction rows withheld: {history.records_withheld}")
    print(f"Transaction history truncated: {history.truncated}")
    print(f"Current owners withheld: {history.current_owners_withheld}")


if __name__ == "__main__":
    main()
