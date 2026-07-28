"""Preview a synthetic PropertyRadar search without purchasing records."""

from property_radar import PropertyRadarClient


def main() -> None:
    """Run a non-billable preview and print envelope metadata only."""
    criteria = [{"name": "RadarID", "value": ["P0000000"]}]
    with PropertyRadarClient() as client:
        preview = client.properties.search(criteria=criteria, purchase=False)
    print(
        {
            "resultCount": preview.get("resultCount"),
            "totalCost": preview.get("totalCost"),
        }
    )


if __name__ == "__main__":
    main()
