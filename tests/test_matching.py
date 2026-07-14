from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hl_paper_trading.matching_engine import BookUnavailableError, MatchingEngine
from hl_paper_trading.types import (
    Order,
    OrderBookLevel,
    OrderBookSnapshot,
    OrderStatus,
    Side,
    Trade,
)

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def book(*, bid_size: str = "25", ask_size: str = "25", at=NOW):
    return OrderBookSnapshot(
        coin="#8050",
        bids=(OrderBookLevel(price=Decimal("0.49"), size=Decimal(bid_size)),),
        asks=(OrderBookLevel(price=Decimal("0.51"), size=Decimal(ask_size)),),
        timestamp=at,
    )


def order(side: Side, price: str, size: str = "10", *, at=NOW):
    return Order(
        coin="#8050",
        quote_token="USDC",
        side=side,
        price=Decimal(price),
        size=Decimal(size),
        status=OrderStatus.OPEN,
        activated_at=at,
    )


def trade(side: Side, price: str, size: str, trade_id: str = "t1"):
    return Trade(
        coin="#8050",
        side=side,
        price=Decimal(price),
        size=Decimal(size),
        timestamp=NOW + timedelta(seconds=1),
        trade_id=trade_id,
    )


def test_requires_a_fresh_book():
    engine = MatchingEngine("#8050")
    with pytest.raises(BookUnavailableError):
        engine.register_order(order(Side.BUY, "0.49"))
    engine.process_book(book(at=NOW - timedelta(seconds=6)))
    with pytest.raises(BookUnavailableError):
        engine.register_order(order(Side.BUY, "0.49"))


def test_queue_is_seeded_from_visible_l2():
    engine = MatchingEngine("#8050")
    engine.process_book(book(bid_size="17"))
    resting = order(Side.BUY, "0.49")
    engine.register_order(resting)
    assert resting.queue_ahead == Decimal("17")


def test_aggressor_side_filters_passive_orders():
    engine = MatchingEngine("#8050")
    engine.process_book(book(bid_size="0"))
    resting = order(Side.BUY, "0.49")
    engine.register_order(resting)
    assert engine.process_trade(trade(Side.BUY, "0.49", "10")) == []
    assert len(engine.process_trade(trade(Side.SELL, "0.49", "10", "t2"))) == 1


def test_queue_consumption_produces_partial_fill():
    engine = MatchingEngine("#8050")
    engine.process_book(book(bid_size="25"))
    resting = order(Side.BUY, "0.49", "10")
    engine.register_order(resting)
    fills = engine.process_trade(trade(Side.SELL, "0.49", "30"))
    assert fills[0].fill_size == Decimal("5")
    assert resting.status is OrderStatus.PARTIALLY_FILLED
    assert resting.queue_ahead == 0


def test_one_trade_volume_is_conserved_across_fifo_orders():
    engine = MatchingEngine("#8050")
    engine.process_book(book(bid_size="0"))
    first = order(Side.BUY, "0.49", "8")
    second = order(Side.BUY, "0.49", "8", at=NOW + timedelta(milliseconds=1))
    engine.register_order(first)
    engine.register_order(second)
    fills = engine.process_trade(trade(Side.SELL, "0.49", "10"))
    assert [fill.fill_size for fill in fills] == [Decimal("8"), Decimal("2")]
    assert sum((fill.fill_size for fill in fills), Decimal("0")) == Decimal("10")
    assert first.status is OrderStatus.FILLED
    assert second.queue_ahead == 0


def test_price_priority_precedes_time_priority():
    engine = MatchingEngine("#8050")
    engine.process_book(book(bid_size="0"))
    worse = order(Side.BUY, "0.49", "10")
    better = order(Side.BUY, "0.50", "10")
    engine.register_order(worse)
    engine.register_order(better)
    fills = engine.process_trade(trade(Side.SELL, "0.48", "10"))
    assert fills[0].order_id == better.order_id
    assert worse.filled_size == 0


def test_book_decrease_does_not_consume_queue():
    engine = MatchingEngine("#8050")
    engine.process_book(book(bid_size="25"))
    resting = order(Side.BUY, "0.49")
    engine.register_order(resting)
    engine.process_book(book(bid_size="2", at=NOW + timedelta(milliseconds=10)))
    assert resting.queue_ahead == Decimal("25")


def test_book_increase_is_conservatively_added_ahead():
    engine = MatchingEngine("#8050")
    engine.process_book(book(bid_size="5"))
    resting = order(Side.BUY, "0.49")
    engine.register_order(resting)
    engine.process_book(book(bid_size="12", at=NOW + timedelta(milliseconds=10)))
    assert resting.queue_ahead == Decimal("12")


def test_duplicate_trade_id_is_ignored():
    engine = MatchingEngine("#8050")
    engine.process_book(book(bid_size="0"))
    engine.register_order(order(Side.BUY, "0.49", "20"))
    event = trade(Side.SELL, "0.49", "10")
    assert len(engine.process_trade(event)) == 1
    assert engine.process_trade(event) == []
    assert engine.stats["duplicates_ignored"] == 1


def test_other_coin_is_ignored():
    engine = MatchingEngine("#8050")
    event = trade(Side.SELL, "0.49", "10").model_copy(update={"coin": "#9990"})
    assert engine.process_trade(event) == []


def test_cancel_and_purge():
    engine = MatchingEngine("#8050")
    engine.process_book(book(bid_size="0"))
    resting = order(Side.BUY, "0.49")
    engine.register_order(resting)
    assert engine.cancel_order(resting.order_id) is resting
    assert engine.purge_inactive() == 1
    assert engine.active_order_count == 0


def test_register_validation_and_reset():
    engine = MatchingEngine("#8050")
    engine.process_book(book())
    pending = order(Side.BUY, "0.49").model_copy(update={"status": OrderStatus.PENDING})
    with pytest.raises(ValueError):
        engine.register_order(pending)
    active = order(Side.BUY, "0.49")
    engine.register_order(active)
    with pytest.raises(ValueError):
        engine.register_order(active)
    engine.reset()
    assert engine.active_order_count == 0
