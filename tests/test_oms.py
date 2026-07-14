from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hl_paper_trading.matching_engine import MatchingEngine
from hl_paper_trading.types import (
    OrderBookLevel,
    OrderBookSnapshot,
    OrderStatus,
    RejectionReason,
    Side,
    Trade,
)
from hl_paper_trading.utils import Config
from hl_paper_trading.virtual_oms import VirtualOMS
from hl_paper_trading.virtual_wallet import VirtualWallet

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def components(*, latency="50", quote="100", tokens="20"):
    wallet = VirtualWallet(
        quote_balances={"USDC": Decimal(quote)},
        token_balances={"#8050": Decimal(tokens)},
        token_quotes={"#8050": "USDC"},
    )
    engine = MatchingEngine("#8050")
    oms = VirtualOMS(wallet, engine, Config(latency_ms=latency, max_order_size="100"))
    return wallet, engine, oms


def book(at=NOW, bid_size="0", ask_size="0"):
    return OrderBookSnapshot(
        coin="#8050",
        bids=(OrderBookLevel(price=Decimal("0.49"), size=Decimal(bid_size)),),
        asks=(OrderBookLevel(price=Decimal("0.51"), size=Decimal(ask_size)),),
        timestamp=at,
    )


def test_submission_reserves_and_activates_after_latency():
    wallet, _, oms = components()
    oms.process_book(book())
    oid = oms.submit_order_sync(
        Side.BUY, Decimal("0.49"), Decimal("10"), current_time=NOW
    )
    assert oid is not None
    assert wallet.reserved_balance("USDC") == Decimal("4.90")
    assert oms.activate_pending(NOW + timedelta(milliseconds=49)) == 0
    assert oms.activate_pending(NOW + timedelta(milliseconds=50)) == 1
    assert oms.get_order(oid).status is OrderStatus.OPEN  # type: ignore[union-attr]


def test_stale_book_rejects_and_releases_reservation():
    wallet, _, oms = components()
    oms.process_book(book(NOW - timedelta(seconds=6)))
    oid = oms.submit_order_sync(
        Side.BUY, Decimal("0.49"), Decimal("10"), current_time=NOW
    )
    assert oid is not None
    oms.activate_pending(NOW + timedelta(milliseconds=50))
    rejected = oms.get_order(oid)
    assert rejected.status is OrderStatus.REJECTED  # type: ignore[union-attr]
    assert rejected.rejection_reason is RejectionReason.BOOK_STALE  # type: ignore[union-attr]
    assert wallet.reserved_balance("USDC") == 0


def test_insufficient_buy_and_naked_sell_are_rejected():
    _, _, oms = components(quote="1", tokens="0")
    assert oms.submit_order_sync(Side.BUY, Decimal("0.5"), Decimal("10")) is None
    assert oms.submit_order_sync(Side.SELL, Decimal("0.5"), Decimal("1")) is None
    assert oms.stats["total_rejected"] == 2


def test_max_order_size_is_rejected():
    _, _, oms = components()
    assert oms.submit_order_sync(Side.BUY, Decimal("0.5"), Decimal("101")) is None
    assert oms.all_orders[-1].rejection_reason is RejectionReason.MAX_ORDER_SIZE


def test_cancel_pending_releases_balance():
    wallet, _, oms = components()
    oid = oms.submit_order_sync(Side.BUY, Decimal("0.5"), Decimal("10"))
    assert oid is not None and oms.cancel_order_sync(oid)
    assert wallet.reserved_balance("USDC") == 0
    assert oms.get_order(oid).status is OrderStatus.CANCELLED  # type: ignore[union-attr]


def test_fill_is_applied_and_callback_runs_once():
    wallet, _, oms = components(latency="0")
    oms.process_book(book())
    received = []
    oms.set_fill_callback(received.append)
    oid = oms.submit_order_sync(
        Side.BUY, Decimal("0.49"), Decimal("10"), current_time=NOW
    )
    assert oid is not None
    event = Trade(
        coin="#8050",
        price=Decimal("0.49"),
        size=Decimal("10"),
        side=Side.SELL,
        timestamp=NOW,
        trade_id="t1",
    )
    fills = oms.process_trade(event)
    assert len(fills) == len(received) == 1
    assert wallet.total_balance("#8050") == Decimal("30")
    assert oms.process_trade(event) == []


def test_cancel_all_releases_buy_and_sell_reservations():
    wallet, _, oms = components()
    oms.submit_order_sync(Side.BUY, Decimal("0.49"), Decimal("10"))
    oms.submit_order_sync(Side.SELL, Decimal("0.51"), Decimal("10"))
    assert oms.cancel_all() == 2
    assert all(value == 0 for value in wallet.snapshot().reserved_balances.values())
