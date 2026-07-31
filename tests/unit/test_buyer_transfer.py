from __future__ import annotations

import hashlib
import json
import traceback
from collections.abc import Callable, Iterator, Mapping
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from types import MappingProxyType

import httpx
import pytest

from property_radar import (
    BUYER_TRANSFER_MATCH_CONTRACT,
    BUYER_TRANSFER_PROPERTY_FIELDS,
    BuyerTransferBillingEvidence,
    BuyerTransferLinkage,
    BuyerTransferMatchCriteria,
    BuyerTransferMatchResult,
    BuyerTransferProperty,
    ChargeNotAllowedError,
    InvalidResponseError,
    PropertyRadarClient,
    ServerError,
    build_buyer_transfer_match_criteria,
    buyer_transfer_scope_fingerprint,
    parse_buyer_transfer_match,
)


class FailingSnapshotMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise RuntimeError(f"SYNTHETIC PRIVATE VALUE FOR {key}")

    def __iter__(self) -> Iterator[str]:
        return iter(("results", "totalCost", "resultCount", "totalResultCount"))

    def __len__(self) -> int:
        return 4


class HostileList(list[object]):
    def __iter__(self) -> Iterator[object]:
        raise RuntimeError("SYNTHETIC PRIVATE LIST")

    def __len__(self) -> int:
        raise RuntimeError("SYNTHETIC PRIVATE LENGTH")


def criteria(**changes: object) -> BuyerTransferMatchCriteria:
    values: dict[str, object] = {
        "buyer_name": "Synthetic Buyer",
        "radar_id": "P-SYNTHETIC",
        "state_code": "UT",
        "county_fips": "49035",
        "publication_window": "Last 7 Days",
        "recording_window": "Last 30 Days",
        "most_recent_change_of_ownership_only": False,
    }
    values.update(changes)
    return BuyerTransferMatchCriteria(**values)  # type: ignore[arg-type]


def property_record(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "RadarID": "P-SYNTHETIC",
        "PType": "Single Family",
        "Address": "81 Synthetic Way",
        "City": "Example",
        "State": "Utah",
        "ZipFive": 84101,
        "County": "Synthetic County",
        "FIPS": "49035",
        "APN": "SYNTHETIC-81",
        "Latitude": 40.7608,
        "Longitude": -111.891,
    }
    values.update(changes)
    return values


def envelope(
    *,
    records: list[object] | None = None,
    result_count: object | None = None,
    total_result_count: object | None = None,
    purchase: bool = False,
) -> dict[str, object]:
    selected = records if records is not None else [property_record()]
    payload: dict[str, object] = {
        "results": selected,
        "totalCost": "0.50",
        "resultCount": len(selected) if result_count is None else result_count,
        "totalResultCount": (
            len(selected) if total_result_count is None else total_result_count
        ),
    }
    if not purchase:
        payload["quantityFreeRemaining"] = 99
    return payload


def thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: thaw(nested) for key, nested in value.items()}
    if isinstance(value, tuple):
        return tuple(thaw(item) for item in value)
    return value


def assert_deeply_immutable(value: object) -> None:
    if isinstance(value, Mapping):
        assert isinstance(value, MappingProxyType)
        for nested in value.values():
            assert_deeply_immutable(nested)
    elif isinstance(value, tuple):
        for nested in value:
            assert_deeply_immutable(nested)


def test_contract_is_current_deeply_immutable_and_fingerprinted() -> None:
    assert BUYER_TRANSFER_MATCH_CONTRACT["api_version"] == "5.2.0.0"
    assert BUYER_TRANSFER_MATCH_CONTRACT["operation"] == "properties.search"
    assert BUYER_TRANSFER_MATCH_CONTRACT["relationship"] == (
        "provider_buyer_criterion_property_match"
    )
    assert (
        BUYER_TRANSFER_MATCH_CONTRACT["most_recent_change_of_ownership_semantics"]
        == "most_recent_ownership_change_market_or_non_market"
    )
    assert BUYER_TRANSFER_MATCH_CONTRACT["ordered_fields"] == (
        BUYER_TRANSFER_PROPERTY_FIELDS
    )
    limitations = BUYER_TRANSFER_MATCH_CONTRACT["provider_limitations"]
    assert isinstance(limitations, Mapping)
    assert limitations["transaction_party_boundaries"] is None
    assert limitations["scalar_grantor_grantee_parsing"] is False
    assert limitations["matched_transaction_identifier"] is None
    assert limitations["matched_structured_grantees"] is None
    assert_deeply_immutable(BUYER_TRANSFER_MATCH_CONTRACT)

    thawed_contract = thaw(BUYER_TRANSFER_MATCH_CONTRACT)
    assert isinstance(thawed_contract, Mapping)
    source = dict(thawed_contract)
    fingerprint = source.pop("contract_fingerprint")
    encoded = json.dumps(
        source, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    assert fingerprint == hashlib.sha256(encoded).hexdigest()
    assert fingerprint == (
        # pragma: allowlist nextline secret
        "299cfaba5ddfc8337a290352433969f1f1363fa1a545080773761c2c99d2c8be"
    )


def test_criteria_build_exact_provider_query_and_redact_identity() -> None:
    value = criteria(
        most_recent_change_of_ownership_only=True,
    )

    assert value.buyer_name == "Synthetic Buyer"
    assert "Synthetic Buyer" not in repr(value)
    assert "P-SYNTHETIC" not in repr(value)
    assert build_buyer_transfer_match_criteria(value) == (
        {"name": "State", "value": ["UT"]},
        {"name": "County", "value": [49035]},
        {"name": "Buyer", "value": ["Synthetic Buyer"]},
        {"name": "TransferPublishedDate", "value": ["Last 7 Days"]},
        {"name": "TransferRecDate", "value": ["Last 30 Days"]},
        {"name": "isMostRecentMarketTransfer", "value": [1]},
        {"name": "RadarID", "value": ["P-SYNTHETIC"]},
    )
    assert len(buyer_transfer_scope_fingerprint(value)) == 64


def test_scope_fingerprint_changes_with_each_configurable_criterion() -> None:
    base = criteria()
    variants = (
        criteria(buyer_name="Different Synthetic Buyer"),
        criteria(radar_id="P-DIFFERENT"),
        criteria(state_code="CO", county_fips="08031"),
        criteria(county_fips="49049"),
        criteria(recording_window=None),
        criteria(most_recent_change_of_ownership_only=True),
    )

    fingerprints = {
        buyer_transfer_scope_fingerprint(request_criteria)
        for request_criteria in (base, *variants)
    }
    assert len(fingerprints) == 1 + len(variants)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"buyer_name": ""}, "buyer_name"),
        ({"buyer_name": None}, "buyer_name"),
        ({"buyer_name": "Synthetic\nBuyer"}, "buyer_name"),
        ({"buyer_name": "  Synthetic Buyer  "}, "buyer_name"),
        ({"radar_id": ""}, "radar_id"),
        ({"state_code": "Ut"}, "state_code"),
        ({"county_fips": "49A35"}, "county_fips"),
        ({"publication_window": "Last 30 Days"}, "publication_window"),
        ({"recording_window": "Last 7 Days"}, "recording_window"),
        ({"most_recent_change_of_ownership_only": 1}, "most_recent"),
    ],
)
def test_criteria_reject_invalid_inputs(
    change: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        criteria(**change)


def test_criteria_does_not_invent_an_undocumented_buyer_name_limit() -> None:
    buyer_name = "X" * 161
    request_criteria = criteria(buyer_name=buyer_name)

    assert build_buyer_transfer_match_criteria(request_criteria)[2] == {
        "name": "Buyer",
        "value": [buyer_name],
    }


def test_parse_match_returns_typed_location_and_billing() -> None:
    request_criteria = criteria()
    result = parse_buyer_transfer_match(
        envelope(), criteria=request_criteria, purchase_requested=False
    )

    assert result.matched is True
    assert result.linkage is not None
    assert result.linkage.relationship == "provider_buyer_criterion_property_match"
    assert result.linkage.scope_fingerprint == (
        buyer_transfer_scope_fingerprint(request_criteria)
    )
    assert result.linkage.property.radar_id == "P-SYNTHETIC"
    assert result.linkage.property.address == "81 Synthetic Way"
    assert result.linkage.property.property_type == "Single Family"
    assert result.linkage.property.is_residential is True
    assert result.linkage.property.zip_five == 84101
    assert result.linkage.property.latitude == Decimal("40.7608")
    assert result.linkage.property.longitude == Decimal("-111.891")
    assert result.billing.status == "preview"
    assert result.billing.total_cost == Decimal("0.50")
    assert result.billing.quantity_free_remaining == 99
    assert (
        result.contract_fingerprint
        == (BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"])
    )


def test_parse_no_match_and_charged_match_are_distinct() -> None:
    no_match = parse_buyer_transfer_match(
        envelope(records=[]), criteria=criteria(), purchase_requested=False
    )
    charged = parse_buyer_transfer_match(
        envelope(purchase=True), criteria=criteria(), purchase_requested=True
    )

    assert no_match.matched is False
    assert no_match.linkage is None
    assert no_match.billing.result_count == 0
    assert charged.matched is True
    assert charged.billing.status == "charged"
    assert charged.billing.quantity_free_remaining is None


def test_present_provider_text_is_preserved_exactly() -> None:
    result = parse_buyer_transfer_match(
        envelope(
            records=[
                {
                    "RadarID": "P-SYNTHETIC",
                    "PType": "Unknown",
                    "Address": "",
                    "City": "",
                    "State": "",
                    "County": "",
                    "APN": "",
                }
            ]
        ),
        criteria=criteria(),
    )

    assert result.linkage is not None
    assert result.linkage.property.address == ""
    assert result.linkage.property.city == ""
    assert result.linkage.property.fips is None
    assert result.linkage.property.apn == ""
    assert result.linkage.property.is_residential is None


def test_documented_non_residential_property_type_is_not_a_home() -> None:
    result = parse_buyer_transfer_match(
        envelope(records=[property_record(PType="Commercial")]),
        criteria=criteria(),
    )

    assert result.linkage is not None
    assert result.linkage.property.is_residential is False


def test_missing_optional_property_fields_remain_unavailable() -> None:
    result = parse_buyer_transfer_match(
        envelope(records=[{"RadarID": "P-SYNTHETIC"}]),
        criteria=criteria(),
    )
    assert result.linkage is not None
    property_value = result.linkage.property
    assert property_value.returned_fields == ("RadarID",)
    assert property_value.property_type is None
    assert property_value.address is None
    assert property_value.zip_five is None
    assert property_value.latitude is None


@pytest.mark.parametrize(
    "payload",
    [
        {"results": [], "totalCost": "0.00", "resultCount": 0},
        {**envelope(), "unexpected": "value"},
        envelope(records=[property_record(), property_record()]),
        envelope(result_count=0),
        envelope(total_result_count=0),
        envelope(result_count=2, total_result_count=2),
        envelope(records=[{"RadarID": "P-DIFFERENT"}]),
        envelope(records=[{**property_record(), "Owner": "PRIVATE"}]),
        envelope(records=[{"Address": "81 Synthetic Way"}]),
        envelope(records=[property_record(ZipFive=True)]),
        envelope(records=[property_record(FIPS="49A35")]),
        envelope(records=[property_record(FIPS="49049")]),
        envelope(records=[property_record(PType="Spaceship")]),
        envelope(records=[property_record(Latitude=91)]),
        envelope(records=[property_record(Longitude=float("nan"))]),
    ],
)
def test_parser_rejects_invalid_or_ambiguous_shapes_without_values(
    payload: dict[str, object],
) -> None:
    with pytest.raises(InvalidResponseError) as caught:
        parse_buyer_transfer_match(
            payload,
            criteria=criteria(),
            purchase_requested=False,
        )
    rendered = str(caught.value)
    assert "Synthetic Buyer" not in rendered
    assert "81 Synthetic Way" not in rendered
    assert "PRIVATE" not in rendered


def test_parser_rejects_preview_metadata_on_a_charged_response() -> None:
    payload = {**envelope(purchase=True), "quantityFreeRemaining": 99}
    with pytest.raises(InvalidResponseError, match="charged_preview_metadata"):
        parse_buyer_transfer_match(
            payload,
            criteria=criteria(),
            purchase_requested=True,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {**envelope(), "resultCount": True},
        {**envelope(), "totalResultCount": -1},
        {**envelope(), "totalCost": 1.0},
        {**envelope(), "totalCost": "-1.00"},
        {**envelope(), "quantityFreeRemaining": False},
    ],
)
def test_parser_rejects_invalid_billing_shapes(payload: dict[str, object]) -> None:
    with pytest.raises(InvalidResponseError):
        parse_buyer_transfer_match(payload, criteria=criteria())


def test_parser_snapshots_hostile_inputs_and_sanitizes_failures() -> None:
    raw_results: list[object] = HostileList([property_record()])
    payload = envelope()
    payload["results"] = raw_results
    parsed = parse_buyer_transfer_match(payload, criteria=criteria())
    assert parsed.matched is True

    with pytest.raises(InvalidResponseError) as caught:
        parse_buyer_transfer_match(FailingSnapshotMapping(), criteria=criteria())
    rendered = "\n".join(
        (str(caught.value), "".join(traceback.format_exception(caught.value)))
    )
    assert "SYNTHETIC PRIVATE" not in rendered


def test_public_values_are_frozen_and_repr_redacts_property_values() -> None:
    result = parse_buyer_transfer_match(envelope(), criteria=criteria())
    assert result.linkage is not None
    with pytest.raises(FrozenInstanceError):
        result.linkage.property.address = "changed"  # type: ignore[misc]

    rendered = repr(result)
    assert "Synthetic Buyer" not in rendered
    assert "P-SYNTHETIC" not in rendered
    assert "81 Synthetic Way" not in rendered
    assert "SYNTHETIC-81" not in rendered


def test_manually_constructed_values_reject_contradictions() -> None:
    parsed = parse_buyer_transfer_match(envelope(), criteria=criteria())
    assert parsed.linkage is not None
    with pytest.raises(ValueError, match="scope_fingerprint"):
        replace(parsed.linkage, scope_fingerprint="bad")
    with pytest.raises(ValueError, match="counts"):
        replace(parsed.billing, total_result_count=0)
    with pytest.raises(ValueError, match="linkage presence"):
        replace(parsed, linkage=None)


def test_public_property_rejects_invalid_manual_states() -> None:
    parsed = parse_buyer_transfer_match(envelope(), criteria=criteria())
    assert parsed.linkage is not None
    property_value = parsed.linkage.property

    with pytest.raises(ValueError, match="immutable field tuple"):
        replace(property_value, returned_fields=["RadarID"])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="contract order"):
        replace(property_value, returned_fields=("Address", "RadarID"))
    with pytest.raises(ValueError, match="required RadarID"):
        replace(property_value, returned_fields=())
    with pytest.raises(ValueError, match="available property values"):
        replace(
            property_value,
            returned_fields=tuple(
                field_name
                for field_name in property_value.returned_fields
                if field_name != "Address"
            ),
        )
    with pytest.raises(ValueError, match="available property values"):
        replace(property_value, address=None)
    with pytest.raises(ValueError, match="radar_id"):
        replace(property_value, radar_id="")
    with pytest.raises(ValueError, match="property_type"):
        replace(property_value, property_type="Spaceship")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="address"):
        replace(property_value, address=81)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="zip_five"):
        replace(property_value, zip_five=100000)
    with pytest.raises(ValueError, match="fips"):
        replace(property_value, fips="49A35")
    with pytest.raises(ValueError, match="latitude"):
        replace(property_value, latitude=Decimal("NaN"))


def test_public_linkage_rejects_unavailable_or_mismatched_values() -> None:
    parsed = parse_buyer_transfer_match(envelope(), criteria=criteria())
    assert parsed.linkage is not None
    linkage = parsed.linkage
    assert "P-SYNTHETIC" not in repr(linkage)

    with pytest.raises(ValueError, match="property"):
        replace(linkage, property=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="relationship"):
        replace(linkage, relationship="confirmed_grantee")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="transaction_identifier"):
        replace(linkage, matched_transaction_identifier="synthetic")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="matched_grantees"):
        replace(linkage, matched_grantees=())  # type: ignore[arg-type]


def test_public_billing_rejects_invalid_manual_states() -> None:
    parsed = parse_buyer_transfer_match(envelope(), criteria=criteria())
    billing = parsed.billing

    with pytest.raises(ValueError, match="purchase_requested"):
        replace(billing, purchase_requested=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="status"):
        replace(billing, status="charged")
    with pytest.raises(ValueError, match="total_cost"):
        replace(billing, total_cost=Decimal("-1"))
    with pytest.raises(ValueError, match="currency"):
        replace(billing, currency="USD")
    with pytest.raises(ValueError, match="result_count"):
        replace(billing, result_count=2, total_result_count=2)
    with pytest.raises(ValueError, match="quantity_free_remaining"):
        replace(billing, quantity_free_remaining=-1)
    with pytest.raises(ValueError, match="charged evidence"):
        BuyerTransferBillingEvidence(
            purchase_requested=True,
            status="charged",
            total_cost=Decimal("0.50"),
            currency=None,
            quantity_free_remaining=1,
            result_count=1,
            total_result_count=1,
        )


def test_public_result_and_entrypoints_reject_wrong_types() -> None:
    parsed = parse_buyer_transfer_match(envelope(), criteria=criteria())
    assert parsed.linkage is not None

    with pytest.raises(ValueError, match="contract_fingerprint"):
        replace(parsed, contract_fingerprint="bad")
    with pytest.raises(ValueError, match="scope_fingerprint"):
        replace(parsed, scope_fingerprint="bad")
    with pytest.raises(ValueError, match="exact scope"):
        replace(
            parsed,
            linkage=replace(parsed.linkage, scope_fingerprint="0" * 64),
        )
    with pytest.raises(ValueError, match="billing"):
        replace(parsed, billing=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="criteria"):
        build_buyer_transfer_match_criteria(object())  # type: ignore[arg-type]
    with pytest.raises(InvalidResponseError, match="criteria_type"):
        parse_buyer_transfer_match(
            envelope(),
            criteria=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(InvalidResponseError, match="purchase_requested"):
        parse_buyer_transfer_match(
            envelope(),
            criteria=criteria(),
            purchase_requested=1,  # type: ignore[arg-type]
        )
    with pytest.raises(InvalidResponseError, match="results_type"):
        parse_buyer_transfer_match(
            {**envelope(), "results": {}},
            criteria=criteria(),
        )
    with pytest.raises(InvalidResponseError, match="envelope_type"):
        parse_buyer_transfer_match([], criteria=criteria())  # type: ignore[arg-type]
    with pytest.raises(InvalidResponseError, match="envelope_key_type"):
        parse_buyer_transfer_match(
            {1: "invalid"},  # type: ignore[dict-item]
            criteria=criteria(),
        )


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    allow_charges: bool = False,
    max_retries: int = 0,
) -> tuple[PropertyRadarClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PropertyRadarClient(
        api_key="synthetic-token",  # pragma: allowlist secret
        allow_charges=allow_charges,
        max_retries=max_retries,
        http_client=http_client,
    )
    return client, http_client


def test_resource_convenience_makes_one_exact_preview_request() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=envelope())

    client, http_client = make_client(handler)
    try:
        result = client.properties.buyer_transfer_match(criteria=criteria())
    finally:
        http_client.close()

    assert result.matched is True
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/v1/properties"
    assert request.url.params.multi_items() == [
        ("Fields", ",".join(BUYER_TRANSFER_PROPERTY_FIELDS)),
        ("Limit", "1"),
        ("Start", "0"),
        ("Purchase", "0"),
    ]
    assert json.loads(request.content) == {
        "Criteria": list(build_buyer_transfer_match_criteria(criteria()))
    }


def test_resource_convenience_denies_unapproved_charge_before_network() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=envelope(purchase=True))

    client, http_client = make_client(handler)
    try:
        with pytest.raises(ChargeNotAllowedError):
            client.properties.buyer_transfer_match(criteria=criteria(), purchase=True)
    finally:
        http_client.close()
    assert calls == 0


@pytest.mark.parametrize("purchase", [1, 0, None, "true"])
def test_resource_convenience_rejects_non_boolean_purchase_before_network(
    purchase: object,
) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=envelope())

    client, http_client = make_client(handler, allow_charges=True)
    try:
        with pytest.raises(TypeError, match="purchase must be a boolean"):
            client.properties.buyer_transfer_match(
                criteria=criteria(),
                purchase=purchase,  # type: ignore[arg-type]
            )
    finally:
        http_client.close()
    assert calls == 0


def test_paid_resource_convenience_is_not_retried() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"message": "synthetic failure"})

    client, http_client = make_client(handler, allow_charges=True, max_retries=3)
    try:
        with pytest.raises(ServerError):
            client.properties.buyer_transfer_match(criteria=criteria(), purchase=True)
    finally:
        http_client.close()
    assert calls == 1


def test_public_dataclass_construction_smoke() -> None:
    property_value = BuyerTransferProperty(
        returned_fields=("RadarID",),
        radar_id="P-SYNTHETIC",
        property_type=None,
        address=None,
        city=None,
        state=None,
        zip_five=None,
        county=None,
        fips=None,
        apn=None,
        latitude=None,
        longitude=None,
    )
    fingerprint = buyer_transfer_scope_fingerprint(criteria())
    linkage = BuyerTransferLinkage(
        scope_fingerprint=fingerprint,
        property=property_value,
    )
    billing = BuyerTransferBillingEvidence(
        purchase_requested=False,
        status="preview",
        total_cost=Decimal("0.00"),
        currency=None,
        quantity_free_remaining=100,
        result_count=1,
        total_result_count=1,
    )
    result = BuyerTransferMatchResult(
        contract_fingerprint=str(BUYER_TRANSFER_MATCH_CONTRACT["contract_fingerprint"]),
        scope_fingerprint=fingerprint,
        linkage=linkage,
        billing=billing,
    )
    assert result.matched is True
