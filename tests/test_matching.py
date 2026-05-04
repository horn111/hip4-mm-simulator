"""Tests for the pessimistic matching engine.

Covers the three core fill rules:
    1. Strict price improvement → fills.
    2. Equal price → fills only after queue volume consumed.
    3. Worse price → no fill.

Also tests partial fills, cancellation, and edge cases.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from hl_paper_trading.matching_engine import MatchingEngine
from hl_paper_trading.types import Order, OrderStatus, Side, Trade


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine() -> MatchingEngine:
    """Create a fresh matching engine."""
    return MatchingEngine(market="TEST-MARKET")


def make_order(
    side: Side,
    price: str,
    size: str,
    status: OrderStatus = OrderStatus.OPEN,
) -> Order:
    """Helper to create a test order."""
    return Order(
        market="TEST-MARKET",
        side=side,
        price=Decimal(price),
        size=Decimal(size),
        status=status,
    )


def make_trade(price: str, size: str, side: Side = Side.BID) -> Trade:
    """Helper to create a test trade."""
    return Trade(
        market="TEST-MARKET",
        price=Decimal(price),
        size=Decimal(size),
        side=side,
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Rule 1: Strict price improvement fills
# ---------------------------------------------------------------------------

class TestStrictPriceImprovement:
    """BID fills when trade_price < order_price.
    ASK fills when trade_price > order_price.
    """

    def test_bid_fills_when_trade_below_bid(self, engine: MatchingEngine) -> None:
        """A BID at 0.50 should fill when a trade occurs at 0.48."""
        order = make_order(Side.BID, "0.50", "100")
        engine.register_order(order)

        trade = make_trade("0.48", "100")
        fills = engine.process_trade(trade)

        assert len(fills) == 1
        assert fills[0].fill_price == Decimal("0.50")  # Fills at limit
        assert fills[0].fill_size == Decimal("100")
        assert order.status == OrderStatus.FILLED

    def test_ask_fills_when_trade_above_ask(self, engine: MatchingEngine) -> None:
        """An ASK at 0.50 should fill when a trade occurs at 0.52."""
        order = make_order(Side.ASK, "0.50", "100")
        engine.register_order(order)

        trade = make_trade("0.52", "100")
        fills = engine.process_trade(trade)

        assert len(fills) == 1
        assert fills[0].fill_price == Decimal("0.50")
        assert fills[0].fill_size == Decimal("100")
        assert order.status == OrderStatus.FILLED

    def test_bid_no_fill_when_trade_above_bid(self, engine: MatchingEngine) -> None:
        """A BID at 0.50 should NOT fill when trade is at 0.52."""
        order = make_order(Side.BID, "0.50", "100")
        engine.register_order(order)

        trade = make_trade("0.52", "100")
        fills = engine.process_trade(trade)

        assert len(fills) == 0
        assert order.status == OrderStatus.OPEN

    def test_ask_no_fill_when_trade_below_ask(self, engine: MatchingEngine) -> None:
        """An ASK at 0.50 should NOT fill when trade is at 0.48."""
        order = make_order(Side.ASK, "0.50", "100")
        engine.register_order(order)

        trade = make_trade("0.48", "100")
        fills = engine.process_trade(trade)

        assert len(fills) == 0
        assert order.status == OrderStatus.OPEN


# ---------------------------------------------------------------------------
# Rule 2: Equal price → queue-based fill
# ---------------------------------------------------------------------------

class TestQueueBasedFill:
    """At equal price, fill only after cumulative volume exceeds
    queue_priority + order_size.
    """

    def test_equal_price_no_fill_insufficient_volume(
        self, engine: MatchingEngine
    ) -> None:
        """At equal price, 50 contracts of volume won't fill a 100-size order
        (queue_priority=0, need >= 100 cumulative volume).
        """
        order = make_order(Side.BID, "0.50", "100")
        engine.register_order(order)

        trade = make_trade("0.50", "50")
        fills = engine.process_trade(trade)

        assert len(fills) == 0
        assert order.status == OrderStatus.OPEN

    def test_equal_price_fills_after_sufficient_volume(
        self, engine: MatchingEngine
    ) -> None:
        """After enough volume accumulates at the price, the order fills.

        Note: fill_size is min(order.remaining, trade.size), so a 50-size
        trade can only fill 50 contracts at once (partial fill). The rest
        fills on the next qualifying trade.
        """
        order = make_order(Side.BID, "0.50", "100")
        engine.register_order(order)

        # First trade: 60 contracts — not enough queue volume
        trade1 = make_trade("0.50", "60")
        fills1 = engine.process_trade(trade1)
        assert len(fills1) == 0

        # Second trade: 50 more → cumulative 110 >= 0 + 100 → fills
        # But fill_size = min(remaining=100, trade_size=50) = 50
        trade2 = make_trade("0.50", "50")
        fills2 = engine.process_trade(trade2)
        assert len(fills2) == 1
        assert fills2[0].fill_size == Decimal("50")
        assert order.status == OrderStatus.PARTIALLY_FILLED

        # Third trade completes the order
        trade3 = make_trade("0.50", "100")
        fills3 = engine.process_trade(trade3)
        assert len(fills3) == 1
        assert fills3[0].fill_size == Decimal("50")
        assert order.status == OrderStatus.FILLED

    def test_queue_priority_respected(self, engine: MatchingEngine) -> None:
        """An order placed after some volume has traded at the price
        must wait for additional volume equal to its queue position + size.
        """
        # Simulate 200 contracts already traded at 0.50
        pre_trade = make_trade("0.50", "200")
        engine.process_trade(pre_trade)

        # Now place order — queue_priority should be 200
        order = make_order(Side.BID, "0.50", "100")
        engine.register_order(order)
        assert order.queue_priority == Decimal("200")

        # Trade 50 more — cumulative = 250, need 200 + 100 = 300
        trade1 = make_trade("0.50", "50")
        fills1 = engine.process_trade(trade1)
        assert len(fills1) == 0

        # Trade 60 more — cumulative = 310 >= 300
        trade2 = make_trade("0.50", "60")
        fills2 = engine.process_trade(trade2)
        assert len(fills2) == 1


# ---------------------------------------------------------------------------
# Rule 3: Partial fills
# ---------------------------------------------------------------------------

class TestPartialFills:
    """Partial fills occur when trade size < order remaining."""

    def test_partial_fill(self, engine: MatchingEngine) -> None:
        """A 100-size order should be partially filled by a 40-size trade."""
        order = make_order(Side.BID, "0.50", "100")
        engine.register_order(order)

        trade = make_trade("0.45", "40")
        fills = engine.process_trade(trade)

        assert len(fills) == 1
        assert fills[0].fill_size == Decimal("40")
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.remaining == Decimal("60")

    def test_partial_fill_then_complete(self, engine: MatchingEngine) -> None:
        """Two trades can complete a partially filled order."""
        order = make_order(Side.BID, "0.50", "100")
        engine.register_order(order)

        # First partial
        fills1 = engine.process_trade(make_trade("0.45", "60"))
        assert fills1[0].fill_size == Decimal("60")
        assert order.status == OrderStatus.PARTIALLY_FILLED

        # Complete
        fills2 = engine.process_trade(make_trade("0.45", "50"))
        assert fills2[0].fill_size == Decimal("40")  # Only remaining
        assert order.status == OrderStatus.FILLED


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------

class TestCancellation:
    """Order cancellation behaviour."""

    def test_cancel_active_order(self, engine: MatchingEngine) -> None:
        """Cancelling an active order prevents future fills."""
        order = make_order(Side.BID, "0.50", "100")
        engine.register_order(order)

        result = engine.cancel_order(order.order_id)
        assert result is not None
        assert result.status == OrderStatus.CANCELLED

        # No fill after cancel
        fills = engine.process_trade(make_trade("0.45", "100"))
        assert len(fills) == 0

    def test_cancel_nonexistent(self, engine: MatchingEngine) -> None:
        """Cancelling a non-existent order returns None."""
        result = engine.cancel_order("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Multiple orders
# ---------------------------------------------------------------------------

class TestMultipleOrders:
    """Multiple orders processed simultaneously."""

    def test_multiple_bids_filled_by_single_trade(
        self, engine: MatchingEngine
    ) -> None:
        """A large trade can fill multiple resting orders."""
        order1 = make_order(Side.BID, "0.50", "50")
        order2 = make_order(Side.BID, "0.48", "50")
        engine.register_order(order1)
        engine.register_order(order2)

        # Trade at 0.45 — below both bids
        trade = make_trade("0.45", "200")
        fills = engine.process_trade(trade)

        assert len(fills) == 2
        assert order1.status == OrderStatus.FILLED
        assert order2.status == OrderStatus.FILLED

    def test_different_markets_ignored(self, engine: MatchingEngine) -> None:
        """Trades for other markets are ignored."""
        order = make_order(Side.BID, "0.50", "100")
        engine.register_order(order)

        trade = Trade(
            market="OTHER-MARKET",
            price=Decimal("0.40"),
            size=Decimal("100"),
            side=Side.BID,
            timestamp=datetime.now(timezone.utc),
        )
        fills = engine.process_trade(trade)
        assert len(fills) == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case handling."""

    def test_order_at_boundary_prices(self, engine: MatchingEngine) -> None:
        """Orders at extreme prices (0.01 and 0.99) work correctly."""
        bid = make_order(Side.BID, "0.01", "10")
        ask = make_order(Side.ASK, "0.99", "10")
        engine.register_order(bid)
        engine.register_order(ask)

        # Trade at 0.005 would fill the bid (if valid)
        fills_bid = engine.process_trade(make_trade("0.005", "10"))
        assert len(fills_bid) == 1

        # Trade at 0.995 would fill the ask
        fills_ask = engine.process_trade(make_trade("0.995", "10"))
        assert len(fills_ask) == 1

    def test_purge_inactive(self, engine: MatchingEngine) -> None:
        """Purging removes filled/cancelled orders."""
        order = make_order(Side.BID, "0.50", "100")
        engine.register_order(order)

        # Fill it
        engine.process_trade(make_trade("0.45", "100"))
        assert order.status == OrderStatus.FILLED

        # Purge
        purged = engine.purge_inactive()
        assert purged == 1
        assert engine.active_order_count == 0

    def test_stats(self, engine: MatchingEngine) -> None:
        """Statistics are tracked correctly."""
        order = make_order(Side.BID, "0.50", "100")
        engine.register_order(order)

        engine.process_trade(make_trade("0.45", "100"))

        stats = engine.stats
        assert stats["total_trades_processed"] == 1
        assert stats["total_fills_generated"] == 1

    def test_fill_at_limit_price_not_trade_price(
        self, engine: MatchingEngine
    ) -> None:
        """Fills execute at the order's limit price, not the trade price.
        This is standard for passive limit orders.
        """
        order = make_order(Side.BID, "0.50", "100")
        engine.register_order(order)

        trade = make_trade("0.40", "100")  # Much better than limit
        fills = engine.process_trade(trade)

        assert fills[0].fill_price == Decimal("0.50")  # Limit, not 0.40


# ---------------------------------------------------------------------------
# Registration validation
# ---------------------------------------------------------------------------

class TestRegistration:
    """Order registration validation."""

    def test_reject_non_open_order(self, engine: MatchingEngine) -> None:
        """Cannot register an order that isn't OPEN."""
        order = make_order(Side.BID, "0.50", "100", status=OrderStatus.PENDING)
        with pytest.raises(ValueError, match="expected OPEN"):
            engine.register_order(order)

    def test_reject_duplicate(self, engine: MatchingEngine) -> None:
        """Cannot register the same order twice."""
        order = make_order(Side.BID, "0.50", "100")
        engine.register_order(order)
        with pytest.raises(ValueError, match="already registered"):
            engine.register_order(order)
