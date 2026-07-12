"""Virtual order management with latency and spot reservations."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hl_paper_trading.matching_engine import BookUnavailableError, MatchingEngine
from hl_paper_trading.types import (
    Fill,
    Order,
    OrderBookSnapshot,
    OrderStatus,
    RejectionReason,
    Side,
    Trade,
)
from hl_paper_trading.utils import Config
from hl_paper_trading.virtual_wallet import InsufficientBalanceError, VirtualWallet

FillCallback = Callable[[Fill], None]


class VirtualOMS:
    def __init__(
        self,
        wallet: VirtualWallet,
        engine: MatchingEngine,
        config: Config | None = None,
    ) -> None:
        self._wallet = wallet
        self._engine = engine
        self._config = config or Config()
        self._latency_ms = self._config.get_int("latency_ms", default=50)
        self._max_order_size = self._config.get_decimal(
            "max_order_size", default=Decimal("1000")
        )
        self._max_open_orders = self._config.get_int("max_open_orders", default=50)
        self._orders: dict[str, Order] = {}
        self._pending_orders: dict[str, datetime] = {}
        self._on_fill: FillCallback | None = None
        self._total_submitted = 0
        self._total_rejected = 0
        self._total_cancelled = 0

    @property
    def open_orders(self) -> list[Order]:
        return [order for order in self._orders.values() if order.is_active]

    @property
    def coin(self) -> str:
        return self._engine.coin

    @property
    def pending_orders(self) -> list[Order]:
        return [self._orders[oid] for oid in self._pending_orders]

    @property
    def all_orders(self) -> list[Order]:
        return list(self._orders.values())

    @property
    def stats(self) -> dict[str, int]:
        return {
            "total_submitted": self._total_submitted,
            "total_rejected": self._total_rejected,
            "total_cancelled": self._total_cancelled,
            "open_orders": len(self.open_orders),
            "pending_orders": len(self.pending_orders),
        }

    def set_fill_callback(self, callback: FillCallback) -> None:
        self._on_fill = callback

    async def submit_order(
        self,
        side: Side,
        price: Decimal,
        size: Decimal,
        *,
        coin: str | None = None,
        quote_token: str | None = None,
    ) -> str | None:
        order_id = self.submit_order_sync(
            side,
            price,
            size,
            coin=coin,
            quote_token=quote_token,
        )
        if order_id is None:
            return None
        await asyncio.sleep(self._latency_ms / 1000)
        self._activate_order(order_id, datetime.now(UTC))
        return order_id

    def submit_order_sync(
        self,
        side: Side,
        price: Decimal,
        size: Decimal,
        *,
        coin: str | None = None,
        quote_token: str | None = None,
        current_time: datetime | None = None,
    ) -> str | None:
        now = current_time or datetime.now(UTC)
        order = Order(
            coin=coin or self._engine.coin,
            quote_token=quote_token or self._engine.quote_token,
            side=side,
            price=price,
            size=size,
            created_at=now,
        )
        self._total_submitted += 1
        reason = self._risk_rejection(order)
        if reason is not None:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = reason
            self._orders[order.order_id] = order
            self._total_rejected += 1
            return None
        try:
            self._wallet.reserve_order(order)
        except InsufficientBalanceError:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = RejectionReason.INSUFFICIENT_BALANCE
            self._orders[order.order_id] = order
            self._total_rejected += 1
            return None

        self._orders[order.order_id] = order
        self._pending_orders[order.order_id] = now + timedelta(
            milliseconds=self._latency_ms
        )
        return order.order_id

    def activate_pending(self, current_time: datetime | None = None) -> int:
        now = current_time or datetime.now(UTC)
        expired = [oid for oid, at in self._pending_orders.items() if now >= at]
        for order_id in expired:
            self._activate_order(order_id, now)
        return len(expired)

    def _activate_order(self, order_id: str, activated_at: datetime) -> None:
        order = self._orders.get(order_id)
        if order is None or order.status is not OrderStatus.PENDING:
            return
        order.status = OrderStatus.OPEN
        order.activated_at = activated_at
        self._pending_orders.pop(order_id, None)
        try:
            self._engine.register_order(order)
        except BookUnavailableError:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = RejectionReason.BOOK_STALE
            self._wallet.release_order(order)
            self._total_rejected += 1

    async def cancel_order(self, order_id: str) -> bool:
        await asyncio.sleep(self._latency_ms / 1000)
        return self.cancel_order_sync(order_id)

    def cancel_order_sync(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order is None:
            return False
        if order.status is OrderStatus.PENDING:
            order.status = OrderStatus.CANCELLED
            self._pending_orders.pop(order_id, None)
        elif order.is_active:
            self._engine.cancel_order(order_id)
        else:
            return False
        self._wallet.release_order(order)
        self._total_cancelled += 1
        return True

    def cancel_all(self) -> int:
        return sum(
            self.cancel_order_sync(order.order_id)
            for order in list(self._orders.values())
            if order.status is OrderStatus.PENDING or order.is_active
        )

    def process_book(self, snapshot: OrderBookSnapshot) -> None:
        self._engine.process_book(snapshot)

    def process_trade(self, trade: Trade) -> list[Fill]:
        self.activate_pending(trade.timestamp)
        fills = self._engine.process_trade(trade)
        for fill in fills:
            self._wallet.apply_fill(fill)
            if self._on_fill is not None:
                self._on_fill(fill)
        return fills

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def get_open_orders_by_side(self, side: Side) -> list[Order]:
        return [order for order in self.open_orders if order.side is side]

    def _risk_rejection(self, order: Order) -> RejectionReason | None:
        if order.size > self._max_order_size:
            return RejectionReason.MAX_ORDER_SIZE
        if len(self.open_orders) + len(self.pending_orders) >= self._max_open_orders:
            return RejectionReason.MAX_OPEN_ORDERS
        if not self._wallet.can_reserve(order):
            return RejectionReason.INSUFFICIENT_BALANCE
        return None
