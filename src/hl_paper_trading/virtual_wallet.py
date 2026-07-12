"""Spot-safe balance, reservation, and NAV accounting."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal

from hl_paper_trading.types import Fill, Order, PortfolioSnapshot, Side


class InsufficientBalanceError(ValueError):
    pass


class DuplicateFillError(ValueError):
    pass


class VirtualWallet:
    """A multi-asset spot ledger that never permits naked sells."""

    def __init__(
        self,
        *,
        quote_balances: Mapping[str, Decimal] | None = None,
        token_balances: Mapping[str, Decimal] | None = None,
        token_quotes: Mapping[str, str] | None = None,
        initial_mark_prices: Mapping[str, Decimal] | None = None,
    ) -> None:
        quote_balances = quote_balances or {"USDC": Decimal("10000")}
        token_balances = token_balances or {}
        all_balances = {**quote_balances, **token_balances}
        if any(value < 0 for value in all_balances.values()):
            raise ValueError("initial balances cannot be negative")
        self._available: defaultdict[str, Decimal] = defaultdict(Decimal)
        self._reserved: defaultdict[str, Decimal] = defaultdict(Decimal)
        self._available.update(all_balances)
        self._initial_balances = dict(all_balances)
        self._token_quotes = dict(token_quotes or {})
        self._initial_marks = dict(initial_mark_prices or {})
        self._applied_fills: set[str] = set()
        self._fills: list[Fill] = []

    @property
    def fills(self) -> list[Fill]:
        return list(self._fills)

    def available_balance(self, asset: str) -> Decimal:
        return self._available[asset]

    def reserved_balance(self, asset: str) -> Decimal:
        return self._reserved[asset]

    def total_balance(self, asset: str) -> Decimal:
        return self._available[asset] + self._reserved[asset]

    def reserve_order(self, order: Order) -> None:
        asset, amount = self._reservation(order, order.remaining)
        if self._available[asset] < amount:
            raise InsufficientBalanceError(
                f"insufficient {asset}: need {amount}, have {self._available[asset]}"
            )
        self._available[asset] -= amount
        self._reserved[asset] += amount
        self._token_quotes.setdefault(order.coin, order.quote_token)

    def release_order(self, order: Order) -> None:
        asset, amount = self._reservation(order, order.remaining)
        amount = min(amount, self._reserved[asset])
        self._reserved[asset] -= amount
        self._available[asset] += amount

    def can_reserve(self, order: Order) -> bool:
        asset, amount = self._reservation(order, order.remaining)
        return self._available[asset] >= amount

    def apply_fill(self, fill: Fill) -> None:
        if fill.fill_id in self._applied_fills:
            raise DuplicateFillError(f"fill {fill.fill_id} was already applied")

        if fill.side is Side.BUY:
            reserved_cost = fill.order_price * fill.fill_size
            actual_cost = fill.fill_price * fill.fill_size
            if self._reserved[fill.quote_token] < reserved_cost:
                raise InsufficientBalanceError(
                    "buy fill exceeds reserved quote balance"
                )
            self._reserved[fill.quote_token] -= reserved_cost
            self._available[fill.quote_token] += reserved_cost - actual_cost
            self._available[fill.coin] += fill.fill_size
        else:
            if self._reserved[fill.coin] < fill.fill_size:
                raise InsufficientBalanceError(
                    "sell fill exceeds reserved token balance"
                )
            self._reserved[fill.coin] -= fill.fill_size
            self._available[fill.quote_token] += fill.fill_price * fill.fill_size

        self._token_quotes.setdefault(fill.coin, fill.quote_token)
        self._applied_fills.add(fill.fill_id)
        self._fills.append(fill)

    def nav(
        self, mark_prices: Mapping[str, Decimal], quote_token: str = "USDC"
    ) -> Decimal:
        value = self.total_balance(quote_token)
        assets = set(self._available) | set(self._reserved)
        for asset in assets:
            if self._token_quotes.get(asset) == quote_token:
                value += self.total_balance(asset) * mark_prices.get(
                    asset, Decimal("0")
                )
        return value

    def initial_nav(self, quote_token: str = "USDC") -> Decimal:
        value = self._initial_balances.get(quote_token, Decimal("0"))
        for asset, balance in self._initial_balances.items():
            if self._token_quotes.get(asset) == quote_token:
                value += balance * self._initial_marks.get(asset, Decimal("0"))
        return value

    def snapshot(
        self,
        mark_prices: Mapping[str, Decimal] | None = None,
        *,
        quote_token: str = "USDC",
        timestamp: datetime | None = None,
    ) -> PortfolioSnapshot:
        marks = mark_prices or {}
        nav = self.nav(marks, quote_token)
        initial = self.initial_nav(quote_token)
        assets = sorted(set(self._available) | set(self._reserved))
        return PortfolioSnapshot(
            quote_token=quote_token,
            available_balances={asset: self._available[asset] for asset in assets},
            reserved_balances={asset: self._reserved[asset] for asset in assets},
            nav=nav,
            initial_nav=initial,
            pnl=nav - initial,
            timestamp=timestamp or datetime.now(UTC),
        )

    def reset(self) -> None:
        self._available = defaultdict(Decimal, self._initial_balances)
        self._reserved = defaultdict(Decimal)
        self._applied_fills.clear()
        self._fills.clear()

    @staticmethod
    def _reservation(order: Order, size: Decimal) -> tuple[str, Decimal]:
        if order.side is Side.BUY:
            return order.quote_token, order.price * size
        return order.coin, size
