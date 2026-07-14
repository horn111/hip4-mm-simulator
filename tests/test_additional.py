import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from hl_paper_trading import BaseStrategy
from hl_paper_trading.cli import main, parse_duration
from hl_paper_trading.hyperliquid_ws import HyperliquidInfo, HyperliquidWS
from hl_paper_trading.matching_engine import MatchingEngine
from hl_paper_trading.mock_ws import MockHyperliquidWS
from hl_paper_trading.recording import RecordedEvent, iter_recording, record_stream
from hl_paper_trading.types import (
    OrderBookLevel,
    OrderBookSnapshot,
    OutcomeMarket,
    OutcomeToken,
    Side,
)
from hl_paper_trading.utils import Config, decimal_round, get_logger, setup_logging
from hl_paper_trading.virtual_oms import VirtualOMS
from hl_paper_trading.virtual_wallet import VirtualWallet

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def make_oms(*, latency="0", max_open="50"):
    wallet = VirtualWallet(
        quote_balances={"USDC": Decimal("100")},
        token_balances={"#8050": Decimal("100")},
        token_quotes={"#8050": "USDC"},
    )
    engine = MatchingEngine("#8050")
    oms = VirtualOMS(
        wallet,
        engine,
        Config(latency_ms=latency, max_open_orders=max_open),
    )
    return wallet, engine, oms


def snapshot(at=NOW):
    return OrderBookSnapshot(
        coin="#8050",
        bids=(OrderBookLevel(price=Decimal("0.49"), size=Decimal("0")),),
        asks=(OrderBookLevel(price=Decimal("0.51"), size=Decimal("0")),),
        timestamp=at,
    )


def test_mock_streams_are_seeded_and_replayable():
    async def run():
        source = MockHyperliquidWS("#8050", seed=7)
        trades = [event async for event in source.stream_trades(3)]
        assert [event.trade_id for event in trades] == [
            "synthetic-1",
            "synthetic-2",
            "synthetic-3",
        ]
        mixed = [event async for event in source.stream_with_orderbook(2, book_every=1)]
        assert len(mixed) == 4
        assert source.current_price > 0

    asyncio.run(run())


def test_mock_replays_recording():
    fixture = Path(__file__).parent / "fixtures" / "sample_recording.jsonl"

    async def run():
        events = [
            event async for event in MockHyperliquidWS().replay_from_file(fixture)
        ]
        assert len(events) == 5

    asyncio.run(run())


def test_record_stream_and_async_iterator(tmp_path):
    async def source():
        yield snapshot()

    destination = tmp_path / "recording.jsonl"

    async def run():
        count = await record_stream(
            source(),
            destination,
            duration=timedelta(seconds=1),
            metadata={"quote_token": "USDC"},
            coin="#8050",
        )
        events = [event async for event in iter_recording(destination)]
        assert count == 1
        assert [event.event_type for event in events] == ["metadata", "book"]

    asyncio.run(run())


def test_strategy_helpers_and_lifecycle():
    wallet, _, oms = make_oms()
    strategy = BaseStrategy(oms, wallet, "test")
    oms.process_book(snapshot())
    strategy.on_start()
    strategy.on_orderbook_update(snapshot())
    strategy.on_trade(None)  # type: ignore[arg-type]
    assert strategy.name == "test"
    assert strategy.oms is oms and strategy.wallet is wallet
    assert strategy.get_mid_price(snapshot()) == Decimal("0.50")
    assert strategy.get_position() == Decimal("100")
    assert strategy.cancel_all_orders() == 0
    strategy.on_stop()


def test_config_resolution_and_helpers(monkeypatch):
    monkeypatch.setenv("HL_PAPER_LATENCY_MS", "75")
    config = Config(log_json="yes")
    assert config.get_int("latency_ms") == 75
    assert config.get_decimal("initial_balance") == Decimal("10000")
    assert config.get_bool("log_json") is True
    assert config.get("unknown", default="fallback") == "fallback"
    with pytest.raises(KeyError):
        config.get("missing")
    assert decimal_round(Decimal("1.23456"), 2) == Decimal("1.23")
    setup_logging(json_output=True, level="DEBUG")
    setup_logging(json_output=False, level="INVALID")
    assert get_logger("test") is not None


def test_async_submit_cancel_and_open_limit():
    async def run():
        wallet, _, oms = make_oms(max_open="1")
        oms.process_book(snapshot(datetime.now(UTC)))
        order_id = await oms.submit_order(Side.BUY, Decimal("0.49"), Decimal("1"))
        assert order_id is not None
        assert oms.get_open_orders_by_side(Side.BUY)
        assert oms.submit_order_sync(Side.SELL, Decimal("0.51"), Decimal("1")) is None
        assert await oms.cancel_order(order_id)
        assert wallet.reserved_balance("USDC") == 0

    asyncio.run(run())


def test_cli_duration_errors():
    with pytest.raises(argparse.ArgumentTypeError):
        parse_duration("24")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_duration("xxh")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_duration("0h")


def test_cli_markets_with_mocked_discovery(monkeypatch, capsys):
    token = OutcomeToken(
        outcome_id=805,
        side_index=0,
        label="Yes",
        quote_token="USDC",
    )
    market = OutcomeMarket(
        outcome_id=805,
        name="Recurring",
        quote_token="USDC",
        tokens=(token,),
    )

    async def discover(_self):
        return [market]

    monkeypatch.setattr(HyperliquidInfo, "discover_outcomes", discover)
    assert main(["markets"]) == 0
    assert "Recurring" in capsys.readouterr().out
    assert main(["markets", "--json"]) == 0
    assert '"outcome_id": 805' in capsys.readouterr().out


def test_info_discovery_with_fake_aiohttp(monkeypatch):
    payload = {
        "outcomes": [
            {
                "outcome": 1,
                "name": "Test",
                "sideSpecs": [{"name": "A"}, {"name": "B"}],
                "quoteToken": "USDC",
            }
        ],
        "questions": [],
    }

    class Response:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def raise_for_status(self):
            return None

        async def json(self):
            return payload

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setitem(sys.modules, "aiohttp", SimpleNamespace(ClientSession=Session))
    markets = asyncio.run(HyperliquidInfo().discover_outcomes())
    assert markets[0].tokens[1].label == "B"


def test_websocket_configuration_and_subscription_shapes():
    token = OutcomeToken(
        outcome_id=805,
        side_index=0,
        label="Yes",
        quote_token="USDC",
    )
    source = HyperliquidWS(token)
    assert [item["subscription"]["type"] for item in source._build_subscriptions()] == [
        "trades",
        "l2Book",
    ]
    with pytest.raises(ValueError):
        HyperliquidWS(token, coin="#wrong")


def test_recorded_metadata_has_no_market_event():
    event = RecordedEvent(
        event_type="metadata",
        exchange_timestamp=NOW,
        received_timestamp=NOW,
        coin="#8050",
        payload={},
    )
    assert event.to_market_event() is None
