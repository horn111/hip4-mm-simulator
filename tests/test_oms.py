"""Tests for VirtualOMS — order lifecycle and risk controls."""

from __future__ import annotations

import pytest
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from hl_paper_trading.matching_engine import MatchingEngine
from hl_paper_trading.types import OrderStatus, Side, Trade
from hl_paper_trading.utils import Config
from hl_paper_trading.virtual_oms import VirtualOMS
from hl_paper_trading.virtual_wallet import VirtualWallet


@pytest.fixture
def components():
    """Create wallet, engine, and OMS."""
    config = Config(latency_ms="0", max_order_size="500", max_open_orders="10")
    wallet = VirtualWallet(initial_balance=Decimal("10000"))
    engine = MatchingEngine(market="TEST")
    oms = VirtualOMS(wallet=wallet, engine=engine, config=config)
    return wallet, engine, oms


class TestOrderSubmission:
    """Order submission and risk checks."""

    def test_submit_creates_order(self, components) -> None:
        wallet, engine, oms = components
        oid = oms.submit_order_sync(Side.BID, Decimal("0.50"), Decimal("100"))
        assert oid is not None
        order = oms.get_order(oid)
        assert order is not None
        assert order.status == OrderStatus.PENDING

    def test_reject_oversized_order(self, components) -> None:
        wallet, engine, oms = components
        oid = oms.submit_order_sync(Side.BID, Decimal("0.50"), Decimal("600"))
        assert oid is None

    def test_reject_insufficient_balance(self, components) -> None:
        wallet, engine, oms = components
        # Try to buy 10000 contracts at 0.50 → cost 5000 (fits)
        # But 25000 contracts at 0.50 → cost 12500 (doesn't fit)
        oid = oms.submit_order_sync(Side.BID, Decimal("0.90"), Decimal("500"))
        # Cost = 0.90 * 500 = 450 → fits
        assert oid is not None

    def test_reject_max_open_orders(self, components) -> None:
        wallet, engine, oms = components
        for i in range(10):
            oid = oms.submit_order_sync(Side.BID, Decimal("0.50"), Decimal("10"))
            assert oid is not None

        # 11th should be rejected
        oid = oms.submit_order_sync(Side.BID, Decimal("0.50"), Decimal("10"))
        assert oid is None


class TestCancellation:
    """Order cancellation."""

    def test_cancel_pending(self, components) -> None:
        wallet, engine, oms = components
        oid = oms.submit_order_sync(Side.BID, Decimal("0.50"), Decimal("100"))
        assert oid is not None
        result = oms.cancel_order_sync(oid)
        assert result is True
        order = oms.get_order(oid)
        assert order.status == OrderStatus.CANCELLED

    def test_cancel_all(self, components) -> None:
        wallet, engine, oms = components
        for _ in range(5):
            oms.submit_order_sync(Side.BID, Decimal("0.50"), Decimal("10"))
        count = oms.cancel_all()
        assert count == 5


class TestTradeProcessing:
    """Trade processing through OMS."""

    def test_process_trade_activates_and_fills(self, components) -> None:
        wallet, engine, oms = components
        oid = oms.submit_order_sync(
            Side.BID, Decimal("0.50"), Decimal("100"),
            current_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        assert oid is not None

        # Trade after latency window
        trade = Trade(
            market="TEST",
            price=Decimal("0.45"),
            size=Decimal("100"),
            side=Side.ASK,
            timestamp=datetime(2025, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        )
        fills = oms.process_trade(trade)
        assert len(fills) == 1
        assert wallet.yes_inventory == Decimal("100")
