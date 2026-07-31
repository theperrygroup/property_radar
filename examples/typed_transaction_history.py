"""Load typed synthetic-ID transaction evidence in preview mode."""

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
        )

    if history.purchase_requested is not False:
        raise RuntimeError("Preview-only transaction request invariant failed.")

    print("Preview transaction evidence parsed successfully.")


if __name__ == "__main__":
    main()
