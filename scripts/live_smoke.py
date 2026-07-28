"""Run one non-billable authenticated smoke check without printing API data."""

from property_radar import PropertyRadarClient


def main() -> None:
    """Validate authentication and the account-status response envelope."""
    with PropertyRadarClient(max_retries=0) as client:
        response = client.accounts.status_labels(layout="menu")

    results = response.get("results")
    if not isinstance(results, list):
        raise RuntimeError("The status-label response did not contain a results list.")
    print({"authenticated": True, "resultType": "list", "resultCount": len(results)})


if __name__ == "__main__":
    main()
