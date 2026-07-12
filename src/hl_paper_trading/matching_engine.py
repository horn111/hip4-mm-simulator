"""Volume-conserving, L2-seeded matching for HIP-4 paper orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from hl_paper_trading.types import (
    Fill,
    Order,
    OrderBookSnapshot,
    OrderStatus,
    Side,
    Trade,
)


class BookUnavailableError(RuntimeError):
    """Raised when an order cannot join a fresh observed L2 book."""


@dataclass
class _QueueLevel:
    external_ahead: Decimal
    order_ids: list[str] = field(default_factory=list)


class MatchingEngine:
    """Simulate passive fills using observed L2 and aggressor trades.

    The model is deliberately conservative: book-size decreases never consume
    queue. Only observed trades reduce queue-ahead, and each trade's size is
    shared across all eligible virtual orders.
    """

    def __init__(
        self,
        coin: str,
        quote_token: str = "USDC",
        *,
        book_stale_after_ms: int = 5_000,
    ) -> None:
        self.coin = coin
        self.quote_token = quote_token
        self.book_stale_after = timedelta(milliseconds=book_stale_after_ms)
        self._book: OrderBookSnapshot | None = None
        self._orders: dict[str, Order] = {}
        self._levels: dict[tuple[Side, Decimal], _QueueLevel] = {}
        self._seen_trade_ids: set[str] = set()
        self._total_trades_processed = 0
        self._total_fills_generated = 0
        self._duplicates_ignored = 0
        self._queue_volume_consumed = Decimal("0")

    @property
    def market(self) -> str:
        """Compatibility-shaped name for the engine's single coin."""
        return self.coin

    @property
    def active_orders(self) -> list[Order]:
        return [order for order in self._orders.values() if order.is_active]

    @property
    def active_order_count(self) -> int:
        return len(self.active_orders)

    @property
    def stats(self) -> dict[str, int | str]:
        return {
            "total_trades_processed": self._total_trades_processed,
            "total_fills_generated": self._total_fills_generated,
            "duplicates_ignored": self._duplicates_ignored,
            "active_orders": self.active_order_count,
            "queue_volume_consumed": str(self._queue_volume_consumed),
        }

    def process_book(self, snapshot: OrderBookSnapshot) -> None:
        """Store the latest L2 state without treating decreases as fills."""
        if snapshot.coin != self.coin:
            return
        if self._book is not None and snapshot.timestamp < self._book.timestamp:
            return
        self._book = snapshot

        # New visible volume may be ahead of us. Decreases are ignored because
        # they may be cancellations rather than executions.
        for (side, price), level in self._levels.items():
            if self._active_ids(level):
                level.external_ahead = max(
                    level.external_ahead, snapshot.size_at(side, price)
                )
                self._refresh_queue_positions(side, price)

    def register_order(self, order: Order) -> None:
        if order.status is not OrderStatus.OPEN:
            raise ValueError("only OPEN orders can be registered")
        if order.order_id in self._orders:
            raise ValueError(f"order {order.order_id} is already registered")
        if order.coin != self.coin:
            raise ValueError(f"order coin {order.coin} does not match {self.coin}")
        if self._book is None or order.activated_at is None:
            raise BookUnavailableError("no L2 snapshot is available")
        if order.activated_at - self._book.timestamp > self.book_stale_after:
            raise BookUnavailableError("latest L2 snapshot is stale")

        key = (order.side, order.price)
        level = self._levels.get(key)
        if level is None or not self._active_ids(level):
            level = _QueueLevel(self._book.size_at(order.side, order.price))
            self._levels[key] = level
        level.order_ids.append(order.order_id)
        self._orders[order.order_id] = order
        self._refresh_queue_positions(*key)

    def cancel_order(self, order_id: str) -> Order | None:
        order = self._orders.get(order_id)
        if order is None or not order.is_active:
            return None
        order.status = OrderStatus.CANCELLED
        self._refresh_queue_positions(order.side, order.price)
        return order

    def process_trade(self, trade: Trade) -> list[Fill]:
        if trade.coin != self.coin:
            return []
        if trade.trade_id and trade.trade_id in self._seen_trade_ids:
            self._duplicates_ignored += 1
            return []
        if trade.trade_id:
            self._seen_trade_ids.add(trade.trade_id)

        self._total_trades_processed += 1
        passive_side = Side.SELL if trade.side is Side.BUY else Side.BUY
        prices = self._eligible_prices(passive_side, trade.price)
        remaining_volume = trade.size
        fills: list[Fill] = []

        for price in prices:
            if remaining_volume <= 0:
                break
            key = (passive_side, price)
            level = self._levels[key]
            active_ids = self._active_ids(level)
            if not active_ids:
                continue

            is_trade_through = (passive_side is Side.BUY and price > trade.price) or (
                passive_side is Side.SELL and price < trade.price
            )
            if is_trade_through:
                level.external_ahead = Decimal("0")
            else:
                queue_consumed = min(level.external_ahead, remaining_volume)
                level.external_ahead -= queue_consumed
                remaining_volume -= queue_consumed
                self._queue_volume_consumed += queue_consumed

            for order_id in active_ids:
                if remaining_volume <= 0:
                    break
                order = self._orders[order_id]
                fill_size = min(order.remaining, remaining_volume)
                if fill_size <= 0:
                    continue
                order.filled_size += fill_size
                order.status = (
                    OrderStatus.FILLED
                    if order.remaining == 0
                    else OrderStatus.PARTIALLY_FILLED
                )
                fills.append(
                    Fill(
                        order_id=order.order_id,
                        coin=order.coin,
                        quote_token=order.quote_token,
                        fill_price=order.price,
                        order_price=order.price,
                        fill_size=fill_size,
                        side=order.side,
                        timestamp=trade.timestamp,
                        aggressor_trade_id=trade.trade_id,
                    )
                )
                remaining_volume -= fill_size

            self._refresh_queue_positions(*key)

        self._total_fills_generated += len(fills)
        return fills

    def purge_inactive(self) -> int:
        inactive = [oid for oid, order in self._orders.items() if not order.is_active]
        for order_id in inactive:
            order = self._orders.pop(order_id)
            self._refresh_queue_positions(order.side, order.price)
        return len(inactive)

    def reset(self) -> None:
        self._book = None
        self._orders.clear()
        self._levels.clear()
        self._seen_trade_ids.clear()
        self._total_trades_processed = 0
        self._total_fills_generated = 0
        self._duplicates_ignored = 0
        self._queue_volume_consumed = Decimal("0")

    def _eligible_prices(self, side: Side, trade_price: Decimal) -> list[Decimal]:
        prices = {
            price
            for (level_side, price), level in self._levels.items()
            if level_side is side
            and self._active_ids(level)
            and (
                (side is Side.BUY and price >= trade_price)
                or (side is Side.SELL and price <= trade_price)
            )
        }
        return sorted(prices, reverse=side is Side.BUY)

    def _active_ids(self, level: _QueueLevel) -> list[str]:
        return [
            order_id
            for order_id in level.order_ids
            if order_id in self._orders and self._orders[order_id].is_active
        ]

    def _refresh_queue_positions(self, side: Side, price: Decimal) -> None:
        level = self._levels.get((side, price))
        if level is None:
            return
        ahead = level.external_ahead
        for order_id in self._active_ids(level):
            order = self._orders[order_id]
            order.queue_ahead = ahead
            ahead += order.remaining
