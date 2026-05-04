"""Tests for VirtualWallet — portfolio accounting correctness."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from hl_paper_trading.types import Fill, Side
from hl_paper_trading.virtual_wallet import VirtualWallet


@pytest.fixture
def wallet() -> VirtualWallet:
    """Create a wallet with 10k USDC."""
    return VirtualWallet(initial_balance=Decimal("10000"))


def make_fill(
    side: Side,
    price: str,
    size: str,
    order_id: str = "test-order",
) -> Fill:
    """Helper to create a Fill."""
    return Fill(
        order_id=order_id,
        fill_price=Decimal(price),
        fill_size=Decimal(size),
        side=side,
        timestamp=datetime.now(timezone.utc),
    )


class TestBuySide:
    """Tests for BID (buy YES) fills."""

    def test_buy_reduces_usdc(self, wallet: VirtualWallet) -> None:
        """Buying YES reduces USDC by price * size."""
        wallet.apply_fill(make_fill(Side.BID, "0.50", "100"))
        assert wallet.usdc_balance == Decimal("9950")

    def test_buy_increases_inventory(self, wallet: VirtualWallet) -> None:
        """Buying YES increases YES inventory."""
        wallet.apply_fill(make_fill(Side.BID, "0.50", "100"))
        assert wallet.yes_inventory == Decimal("100")

    def test_buy_sets_avg_entry(self, wallet: VirtualWallet) -> None:
        """Average entry is set correctly on first buy."""
        wallet.apply_fill(make_fill(Side.BID, "0.45", "100"))
        assert wallet.avg_entry_price_yes == Decimal("0.45")

    def test_multiple_buys_vwap(self, wallet: VirtualWallet) -> None:
        """Multiple buys compute correct VWAP."""
        wallet.apply_fill(make_fill(Side.BID, "0.40", "100"))
        wallet.apply_fill(make_fill(Side.BID, "0.60", "100"))
        # VWAP = (0.40 * 100 + 0.60 * 100) / 200 = 0.50
        assert wallet.avg_entry_price_yes == Decimal("0.50")


class TestSellSide:
    """Tests for ASK (sell YES) fills."""

    def test_sell_increases_usdc(self, wallet: VirtualWallet) -> None:
        """Selling YES credits USDC."""
        wallet.apply_fill(make_fill(Side.BID, "0.40", "100"))
        wallet.apply_fill(make_fill(Side.ASK, "0.50", "100"))
        # Bought at 0.40*100=40, sold at 0.50*100=50
        assert wallet.usdc_balance == Decimal("10010")

    def test_sell_reduces_inventory(self, wallet: VirtualWallet) -> None:
        """Selling YES reduces inventory to zero."""
        wallet.apply_fill(make_fill(Side.BID, "0.50", "100"))
        wallet.apply_fill(make_fill(Side.ASK, "0.50", "100"))
        assert wallet.yes_inventory == Decimal("0")


class TestPnL:
    """PnL accounting correctness."""

    def test_realized_pnl_on_close(self, wallet: VirtualWallet) -> None:
        """Closing a long position realises PnL."""
        wallet.apply_fill(make_fill(Side.BID, "0.40", "100"))
        wallet.apply_fill(make_fill(Side.ASK, "0.55", "100"))
        # PnL = 100 * (0.55 - 0.40) = 15
        assert wallet.realized_pnl == Decimal("15")

    def test_unrealized_pnl(self, wallet: VirtualWallet) -> None:
        """Unrealized PnL is calculated correctly."""
        wallet.apply_fill(make_fill(Side.BID, "0.40", "100"))
        u_pnl = wallet.unrealized_pnl(mark_price=Decimal("0.60"))
        # 100 * (0.60 - 0.40) = 20
        assert u_pnl == Decimal("20")

    def test_total_pnl(self, wallet: VirtualWallet) -> None:
        """Total PnL = realized + unrealized."""
        wallet.apply_fill(make_fill(Side.BID, "0.40", "200"))
        wallet.apply_fill(make_fill(Side.ASK, "0.50", "100"))
        # Realized: 100 * (0.50 - 0.40) = 10
        # Unrealized at 0.55: 100 * (0.55 - 0.40) = 15
        total = wallet.total_pnl(mark_price=Decimal("0.55"))
        assert total == Decimal("25")

    def test_losing_trade_pnl(self, wallet: VirtualWallet) -> None:
        """PnL is negative for losing trades."""
        wallet.apply_fill(make_fill(Side.BID, "0.60", "100"))
        wallet.apply_fill(make_fill(Side.ASK, "0.45", "100"))
        # PnL = 100 * (0.45 - 0.60) = -15
        assert wallet.realized_pnl == Decimal("-15")


class TestSnapshot:
    """Portfolio snapshot generation."""

    def test_snapshot_fields(self, wallet: VirtualWallet) -> None:
        """Snapshot contains all expected fields."""
        wallet.apply_fill(make_fill(Side.BID, "0.50", "100"))
        snap = wallet.snapshot(mark_price=Decimal("0.55"))

        assert snap.usdc_balance == Decimal("9950.0000")
        assert snap.yes_inventory == Decimal("100")
        assert snap.avg_entry_price_yes == Decimal("0.5000")
        assert snap.unrealized_pnl == Decimal("5.0000")

    def test_snapshot_is_frozen(self, wallet: VirtualWallet) -> None:
        """Snapshots are immutable."""
        snap = wallet.snapshot()
        with pytest.raises(Exception):
            snap.usdc_balance = Decimal("999999")  # type: ignore


class TestReset:
    """Wallet reset."""

    def test_reset_restores_initial_state(self, wallet: VirtualWallet) -> None:
        """Reset brings everything back to initial values."""
        wallet.apply_fill(make_fill(Side.BID, "0.50", "100"))
        wallet.reset()

        assert wallet.usdc_balance == Decimal("10000")
        assert wallet.yes_inventory == Decimal("0")
        assert wallet.realized_pnl == Decimal("0")
        assert len(wallet.fills) == 0
