"""Synthetic pickle and copy round trips of the two billing-evidence errors."""

from __future__ import annotations

import copy
import dataclasses
import pickle
import socket
import sys
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import NoReturn

import pytest

from property_radar import (
    BuyerTransferBillingEvidence,
    BuyerTransferMatchCriteria,
    BuyerTransferResponseError,
    HistoricalTransactionBillingEvidence,
    HistoricalTransactionDateRange,
    HistoricalTransactionQuery,
    HistoricalTransactionResponseError,
    InvalidResponseError,
    PropertyRadarError,
    parse_buyer_transfer_match,
    parse_historical_transaction_quote,
    parse_historical_transaction_result,
)

BillingEvidence = BuyerTransferBillingEvidence | HistoricalTransactionBillingEvidence
BillingResponseError = BuyerTransferResponseError | HistoricalTransactionResponseError
ErrorFactory = Callable[[], BillingResponseError]
RoundTrip = Callable[[object], object]

BUYER_TRANSFER_MESSAGE = (
    "PropertyRadar returned invalid buyer-transfer match (radar_id_mismatch)."
)
HISTORICAL_TRANSACTION_MESSAGE = (
    "PropertyRadar returned invalid historical transactions (paid_selection)."
)
ADD_NOTE_SKIP_REASON = (
    "BaseException.add_note() and __notes__ exist only on Python 3.11 and later"
)


class SyntheticBuyerTransferResponseError(BuyerTransferResponseError):
    """A caller's module-level subclass, which pickle finds by its name."""


class SyntheticHistoricalTransactionResponseError(HistoricalTransactionResponseError):
    """A caller's module-level subclass, which pickle finds by its name."""


@pytest.fixture(autouse=True)
def _deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> NoReturn:
        raise AssertionError("synthetic tests must not open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def pickle_round_trip(protocol: int) -> RoundTrip:
    def round_trip(value: object) -> object:
        return pickle.loads(pickle.dumps(value, protocol=protocol))

    return round_trip


# Every pickle protocol of this Python, then the shallow and the deep copy.
ROUND_TRIPS = [
    *(
        pytest.param(pickle_round_trip(protocol), id=f"pickle-protocol-{protocol}")
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1)
    ),
    pytest.param(copy.copy, id="copy.copy"),
    pytest.param(copy.deepcopy, id="copy.deepcopy"),
]


def preview_evidence() -> BuyerTransferBillingEvidence:
    # A one-hit preview: resultCount counts purchased rows (zero) and
    # totalResultCount counts matches.
    return BuyerTransferBillingEvidence(
        purchase_requested=False,
        status="preview",
        total_cost=Decimal("0"),
        currency=None,
        quantity_free_remaining=9866,
        result_count=0,
        total_result_count=1,
    )


def bare_preview_evidence() -> BuyerTransferBillingEvidence:
    # The bare zero-hit preview, with the keyword-only omitted-metadata marker.
    return BuyerTransferBillingEvidence(
        purchase_requested=False,
        status="preview",
        total_cost=Decimal("0"),
        currency=None,
        quantity_free_remaining=None,
        result_count=0,
        total_result_count=0,
        provider_metadata_omitted=True,
    )


def charged_evidence() -> BuyerTransferBillingEvidence:
    return BuyerTransferBillingEvidence(
        purchase_requested=True,
        status="charged",
        total_cost=Decimal("2.50"),
        currency=None,
        quantity_free_remaining=None,
        result_count=1,
        total_result_count=1,
    )


def historical_query() -> HistoricalTransactionQuery:
    return HistoricalTransactionQuery(
        radar_id="P-SYNTHETIC",
        recording_dates=HistoricalTransactionDateRange(
            date(2020, 1, 1), date(2020, 12, 31)
        ),
        limit=2,
        doc_types=("GRT", "WRT"),
        doc_groups=("Deed",),
    )


def historical_paid_evidence() -> HistoricalTransactionBillingEvidence:
    return HistoricalTransactionBillingEvidence(
        purchase_requested=True,
        scope_fingerprint=historical_query().scope_fingerprint,
        total_cost=Decimal("0.0000001"),
        result_count=2,
        total_result_count=5,
    )


def historical_quote_evidence_without_metadata() -> (
    HistoricalTransactionBillingEvidence
):
    return HistoricalTransactionBillingEvidence(
        purchase_requested=False,
        scope_fingerprint=historical_query().scope_fingerprint,
        total_cost=None,
        result_count=None,
        total_result_count=None,
    )


def buyer_transfer_error(
    evidence: BuyerTransferBillingEvidence,
    error_type: type[BuyerTransferResponseError] = BuyerTransferResponseError,
) -> BuyerTransferResponseError:
    return error_type(BUYER_TRANSFER_MESSAGE, billing_evidence=evidence)


def historical_transaction_error(
    evidence: HistoricalTransactionBillingEvidence,
    error_type: type[HistoricalTransactionResponseError] = (
        HistoricalTransactionResponseError
    ),
) -> HistoricalTransactionResponseError:
    return error_type(HISTORICAL_TRANSACTION_MESSAGE, billing_evidence=evidence)


# Factories, so that no test sees another test's notes or attributes.
ERROR_CASES = [
    pytest.param(
        lambda: buyer_transfer_error(preview_evidence()),
        BUYER_TRANSFER_MESSAGE,
        id="buyer-transfer-preview",
    ),
    pytest.param(
        lambda: buyer_transfer_error(bare_preview_evidence()),
        BUYER_TRANSFER_MESSAGE,
        id="buyer-transfer-bare-preview",
    ),
    pytest.param(
        lambda: buyer_transfer_error(charged_evidence()),
        BUYER_TRANSFER_MESSAGE,
        id="buyer-transfer-charged",
    ),
    pytest.param(
        lambda: historical_transaction_error(historical_paid_evidence()),
        HISTORICAL_TRANSACTION_MESSAGE,
        id="historical-transaction-paid",
    ),
    pytest.param(
        lambda: historical_transaction_error(
            historical_quote_evidence_without_metadata()
        ),
        HISTORICAL_TRANSACTION_MESSAGE,
        id="historical-transaction-quote-without-metadata",
    ),
]
SUBCLASS_CASES = [
    pytest.param(
        lambda: buyer_transfer_error(
            charged_evidence(), SyntheticBuyerTransferResponseError
        ),
        BUYER_TRANSFER_MESSAGE,
        id="buyer-transfer-subclass",
    ),
    pytest.param(
        lambda: historical_transaction_error(
            historical_paid_evidence(), SyntheticHistoricalTransactionResponseError
        ),
        HISTORICAL_TRANSACTION_MESSAGE,
        id="historical-transaction-subclass",
    ),
]


def assert_same_evidence(restored: object, original: BillingEvidence) -> None:
    assert type(restored) is type(original)
    assert restored == original
    for item in dataclasses.fields(original):
        restored_value = getattr(restored, item.name)
        original_value = getattr(original, item.name)
        assert type(restored_value) is type(original_value)
        assert restored_value == original_value
        if isinstance(original_value, Decimal):
            # Equal Decimals can differ in exponent; keep the exact value.
            assert restored_value.as_tuple() == original_value.as_tuple()


def assert_round_trip(
    restored: object, original: BillingResponseError, message: str
) -> None:
    assert restored is not original
    assert type(restored) is type(original)
    assert isinstance(
        restored, (BuyerTransferResponseError, HistoricalTransactionResponseError)
    )
    assert isinstance(restored, InvalidResponseError)
    assert original.args == (message,)
    assert restored.args == (message,)
    assert str(restored) == str(original) == message
    assert repr(restored) == repr(original)
    assert_same_evidence(restored.billing_evidence, original.billing_evidence)
    assert restored.status_code == original.status_code
    assert restored.request_id == original.request_id
    assert restored.retry_after == original.retry_after
    assert vars(restored) == vars(original)
    assert vars(restored) is not vars(original)


@pytest.mark.parametrize("round_trip", ROUND_TRIPS)
@pytest.mark.parametrize(("make_error", "message"), ERROR_CASES)
def test_billing_errors_round_trip_with_their_billing_evidence(
    make_error: ErrorFactory, message: str, round_trip: RoundTrip
) -> None:
    original = make_error()

    restored = round_trip(original)

    assert_round_trip(restored, original, message)
    assert isinstance(restored, PropertyRadarError)
    assert restored.status_code is None
    assert restored.request_id is None
    assert restored.retry_after is None
    assert not hasattr(restored, "__notes__")


@pytest.mark.parametrize("round_trip", ROUND_TRIPS)
@pytest.mark.parametrize(("make_error", "message"), ERROR_CASES)
def test_round_trips_keep_error_metadata_set_after_construction(
    make_error: ErrorFactory, message: str, round_trip: RoundTrip
) -> None:
    original = make_error()
    original.status_code = 200
    original.request_id = "req-synthetic-0001"
    original.retry_after = 2.5

    restored = round_trip(original)

    assert_round_trip(restored, original, message)
    assert isinstance(restored, PropertyRadarError)
    assert restored.status_code == 200
    assert restored.request_id == "req-synthetic-0001"
    assert restored.retry_after == 2.5


@pytest.mark.parametrize("round_trip", ROUND_TRIPS)
@pytest.mark.parametrize(("make_error", "message"), SUBCLASS_CASES)
def test_module_level_subclasses_round_trip_as_the_subclass(
    make_error: ErrorFactory, message: str, round_trip: RoundTrip
) -> None:
    original = make_error()
    assert type(original) in (
        SyntheticBuyerTransferResponseError,
        SyntheticHistoricalTransactionResponseError,
    )

    restored = round_trip(original)

    assert_round_trip(restored, original, message)
    assert repr(restored) == f"{type(original).__name__}({message!r})"


@pytest.mark.skipif(sys.version_info < (3, 11), reason=ADD_NOTE_SKIP_REASON)
@pytest.mark.parametrize("round_trip", ROUND_TRIPS)
@pytest.mark.parametrize(("make_error", "message"), [*ERROR_CASES, *SUBCLASS_CASES])
def test_add_note_notes_survive_every_round_trip(
    make_error: ErrorFactory, message: str, round_trip: RoundTrip
) -> None:
    original = make_error()
    notes = ["synthetic note: queued for a retry", "synthetic note: second"]
    # mypy checks this file as Python 3.10, which has no add_note().
    if sys.version_info >= (3, 11):
        for note in notes:
            original.add_note(note)

    restored = round_trip(original)

    assert_round_trip(restored, original, message)
    assert vars(original)["__notes__"] == notes
    assert vars(restored)["__notes__"] == notes


def buyer_transfer_criteria() -> BuyerTransferMatchCriteria:
    return BuyerTransferMatchCriteria(
        buyer_name="Synthetic Buyer",
        radar_id="P-SYNTHETIC",
        state_code="UT",
        county_fips="49035",
        publication_window="Last 7 Days",
        recording_window="Last 30 Days",
    )


BUYER_TRANSFER_PREVIEW_REJECTIONS = [
    pytest.param(
        # The live one-hit RadarID-only preview shape, with a returned PType
        # outside the preview's residential PropertyType criterion.
        {
            "results": [{"RadarID": "P-SYNTHETIC", "PType": "Commercial"}],
            "totalCost": 0,
            "resultCount": 0,
            "totalResultCount": 1,
        },
        "property_type_outside_criterion",
        BuyerTransferBillingEvidence(
            purchase_requested=False,
            status="preview",
            total_cost=Decimal("0"),
            currency=None,
            quantity_free_remaining=None,
            result_count=0,
            total_result_count=1,
        ),
        id="one-hit-preview-outside-the-criterion",
    ),
    pytest.param(
        {
            "results": [
                {
                    "RadarID": "P-DIFFERENT",
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
            ],
            "totalCost": "0.50",
            "resultCount": 1,
            "totalResultCount": 1,
            "quantityFreeRemaining": 99,
        },
        "radar_id_mismatch",
        BuyerTransferBillingEvidence(
            purchase_requested=False,
            status="preview",
            total_cost=Decimal("0.50"),
            currency=None,
            quantity_free_remaining=99,
            result_count=1,
            total_result_count=1,
        ),
        id="preview-with-another-radar-id",
    ),
]


@pytest.mark.parametrize("round_trip", ROUND_TRIPS)
@pytest.mark.parametrize(
    ("payload", "reason", "evidence"), BUYER_TRANSFER_PREVIEW_REJECTIONS
)
def test_buyer_transfer_preview_parser_error_survives_round_trips(
    payload: dict[str, object],
    reason: str,
    evidence: BuyerTransferBillingEvidence,
    round_trip: RoundTrip,
) -> None:
    with pytest.raises(BuyerTransferResponseError) as caught:
        parse_buyer_transfer_match(
            payload, criteria=buyer_transfer_criteria(), purchase_requested=False
        )
    original = caught.value
    assert type(original) is BuyerTransferResponseError
    assert original.billing_evidence == evidence

    restored = round_trip(original)

    assert_round_trip(
        restored,
        original,
        f"PropertyRadar returned invalid buyer-transfer match ({reason}).",
    )
    assert isinstance(restored, BuyerTransferResponseError)
    assert restored.billing_evidence == evidence
    assert restored.status_code is None
    assert restored.request_id is None
    assert restored.retry_after is None


HISTORICAL_TRANSACTION_REJECTIONS = [
    pytest.param(
        parse_historical_transaction_result,
        # A paid response without its selected rows.
        {"totalCost": "0.0000001", "resultCount": 2, "totalResultCount": 5},
        "paid_results_missing",
        True,
        id="paid-result-without-rows",
    ),
    pytest.param(
        parse_historical_transaction_quote,
        # A quote that returned rows, which a quote must omit.
        {
            "results": [{"DocumentID": "D-SYNTHETIC-1", "RadarID": "P-SYNTHETIC"}],
            "totalCost": "0.0000001",
            "resultCount": 2,
            "totalResultCount": 5,
        },
        "quote_results_not_omitted",
        False,
        id="quote-with-returned-rows",
    ),
]


@pytest.mark.parametrize("round_trip", ROUND_TRIPS)
@pytest.mark.parametrize(
    ("parser", "payload", "reason", "purchase_requested"),
    HISTORICAL_TRANSACTION_REJECTIONS,
)
def test_historical_transaction_parser_error_survives_round_trips(
    parser: Callable[..., object],
    payload: dict[str, object],
    reason: str,
    purchase_requested: bool,
    round_trip: RoundTrip,
) -> None:
    request = historical_query()
    evidence = HistoricalTransactionBillingEvidence(
        purchase_requested=purchase_requested,
        scope_fingerprint=request.scope_fingerprint,
        total_cost=Decimal("0.0000001"),
        result_count=2,
        total_result_count=5,
    )
    with pytest.raises(HistoricalTransactionResponseError) as caught:
        parser(payload, query=request)
    original = caught.value
    assert type(original) is HistoricalTransactionResponseError
    assert original.billing_evidence == evidence

    restored = round_trip(original)

    assert_round_trip(
        restored,
        original,
        f"PropertyRadar returned invalid historical transactions ({reason}).",
    )
    assert isinstance(restored, HistoricalTransactionResponseError)
    assert restored.billing_evidence == evidence
    assert restored.status_code is None
    assert restored.request_id is None
    assert restored.retry_after is None
