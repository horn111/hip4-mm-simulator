from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from hl_paper_trading.types import Fill, Order, Side
from hl_paper_trading.virtual_wallet import (
    DuplicateFillError,
    InsufficientBalanceError,
    VirtualWallet,
)

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def wallet() -> VirtualWallet:
    return VirtualWallet(
        quote_balances={"USDC": Decimal("100")},
        token_balances={"#8050": Decimal("20")},
        token_quotes={"#8050": "USDC"},
        initial_mark_prices={"#8050": Decimal("0.5")},
    )


def order(side: Side, price: str = "0.5", size: str = "10") -> Order:
    return Order(
        coin="#8050",
        quote_token="USDC",
        side=side,
        price=Decimal(price),
        size=Decimal(size),
    )


def fill(parent: Order, size: str = "10", *, fill_id: str = "f1") -> Fill:
    return Fill(
        fill_id=fill_id,
        order_id=parent.order_id,
        coin=parent.coin,
        quote_token=parent.quote_token,
        fill_price=parent.price,
        order_price=parent.price,
        fill_size=Decimal(size),
        side=parent.side,
        timestamp=NOW,
    )


def test_buy_reserves_quote_and_fill_delivers_token():
    ledger = wallet()
    parent = order(Side.BUY)
    ledger.reserve_order(parent)
    assert ledger.available_balance("USDC") == Decimal("95")
    assert ledger.reserved_balance("USDC") == Decimal("5")
    ledger.apply_fill(fill(parent))
    assert ledger.total_balance("USDC") == Decimal("95")
    assert ledger.total_balance("#8050") == Decimal("30")


def test_sell_reserves_tokens_and_fill_delivers_quote():
    ledger = wallet()
    parent = order(Side.SELL)
    ledger.reserve_order(parent)
    assert ledger.available_balance("#8050") == Decimal("10")
    ledger.apply_fill(fill(parent))
    assert ledger.total_balance("#8050") == Decimal("10")
    assert ledger.total_balance("USDC") == Decimal("105")


def test_naked_sell_is_rejected():
    ledger = wallet()
    with pytest.raises(InsufficientBalanceError):
        ledger.reserve_order(order(Side.SELL, size="21"))


def test_release_returns_remaining_reservation():
    ledger = wallet()
    parent = order(Side.BUY)
    ledger.reserve_order(parent)
    parent.filled_size = Decimal("4")
    ledger.apply_fill(fill(parent, "4"))
    ledger.release_order(parent)
    assert ledger.reserved_balance("USDC") == 0
    assert ledger.available_balance("USDC") == Decimal("98")


def test_duplicate_fill_is_rejected():
    ledger = wallet()
    parent = order(Side.BUY)
    ledger.reserve_order(parent)
    event = fill(parent)
    ledger.apply_fill(event)
    with pytest.raises(DuplicateFillError):
        ledger.apply_fill(event)


def test_nav_and_pnl_include_available_and_reserved():
    ledger = wallet()
    ledger.reserve_order(order(Side.BUY))
    snapshot = ledger.snapshot({"#8050": Decimal("0.6")})
    assert snapshot.nav == Decimal("112")
    assert snapshot.initial_nav == Decimal("110.0")
    assert snapshot.pnl == Decimal("2.0")


def test_reset_restores_initial_balances():
    ledger = wallet()
    parent = order(Side.BUY)
    ledger.reserve_order(parent)
    ledger.apply_fill(fill(parent))
    ledger.reset()
    assert ledger.total_balance("USDC") == Decimal("100")
    assert ledger.total_balance("#8050") == Decimal("20")
    assert ledger.fills == []


def test_invalid_initial_and_order_values():
    with pytest.raises(ValueError):
        VirtualWallet(quote_balances={"USDC": Decimal("-1")})
    with pytest.raises(ValidationError):
        order(Side.BUY, price="1.1")


def test_snapshot_is_frozen():
    snapshot = wallet().snapshot({"#8050": Decimal("0.5")})
    with pytest.raises(ValidationError):
        snapshot.nav = Decimal("0")  # type: ignore[misc]
