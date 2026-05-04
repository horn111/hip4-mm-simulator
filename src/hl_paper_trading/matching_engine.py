"""Pessimistic matching engine for paper trade simulation.

This is the **most critical** component of the framework. It determines
whether virtual orders would have been filled given the real trade flow
observed on Hyperliquid mainnet.

Design Philosophy — **Pessimistic Execution**:
    Real market-making is adversarial. A paper trading engine that fills
    every time the market touches your price will dramatically overstate
    performance. We therefore use conservative fill rules:

    1. **BID (buy) fills** only when ``trade_price < order_price``
       (strictly below your bid — you only get filled when the market
       trades *through* your level).

    2. **ASK (sell) fills** only when ``trade_price > order_price``
       (strictly above your ask).

    3. **At-price trades** (``trade_price == order_price``) fill only
       after the cumulative volume at that price exceeds the order's
       queue position + size. This simulates queue priority: you sit
       behind everyone who was there before you.

This approach is standard practice at prop trading firms (Jane Street,
Jump Trading, Citadel Securities) for backtesting market-making strategies.

Volume Tracking:
    For each (market, price) pair, we track cumulative volume traded.
    When a virtual order is placed, it records the current volume as its
    ``queue_priority``. At-price fills only occur when:
        ``cumulative_volume >= queue_priority + order_size``
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from hl_paper_trading.types import Fill, Order, OrderStatus, Side, Trade
from hl_paper_trading.utils import get_logger

logger = get_logger(__name__)


class MatchingEngine:
    """Pessimistic fill simulator for virtual orders against real trades.

    The engine maintains a registry of active virtual orders and evaluates
    each incoming trade for potential fills. Fill logic is intentionally
    conservative to avoid over-fitting strategies to unrealistic execution.

    Args:
        market: The market symbol this engine instance handles.

    Example::

        engine = MatchingEngine(market="BTC-50K-2025")
        engine.register_order(order)
        fills = engine.process_trade(trade)
    """

    def __init__(self, market: str) -> None:
        self._market = market

        # Active orders indexed by order_id for O(1) lookup
        self._orders: dict[str, Order] = {}

        # Cumulative volume at each price level for queue simulation
        # Key: Decimal price → Value: cumulative volume
        self._volume_at_price: dict[Decimal, Decimal] = defaultdict(
            lambda: Decimal("0")
        )

        # Statistics
        self._total_trades_processed: int = 0
        self._total_fills_generated: int = 0

        logger.info("matching_engine.initialized", market=market)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def market(self) -> str:
        """Market symbol this engine handles."""
        return self._market

    @property
    def active_orders(self) -> list[Order]:
        """All orders currently eligible for fills."""
        return [o for o in self._orders.values() if o.is_active]

    @property
    def active_order_count(self) -> int:
        """Number of orders currently eligible for fills."""
        return sum(1 for o in self._orders.values() if o.is_active)

    @property
    def stats(self) -> dict[str, int]:
        """Engine statistics."""
        return {
            "total_trades_processed": self._total_trades_processed,
            "total_fills_generated": self._total_fills_generated,
            "active_orders": self.active_order_count,
        }

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def register_order(self, order: Order) -> None:
        """Register a new order for fill evaluation.

        The order's ``queue_priority`` is set to the current cumulative
        volume at its price level, simulating arriving at the back of
        the queue.

        Args:
            order: The order to register. Must have status OPEN.

        Raises:
            ValueError: If the order is not OPEN or already registered.
        """
        if order.status != OrderStatus.OPEN:
            raise ValueError(
                f"Cannot register order {order.order_id} with status "
                f"{order.status}; expected OPEN"
            )
        if order.order_id in self._orders:
            raise ValueError(f"Order {order.order_id} is already registered")

        # Record queue position = current volume at this price
        order.queue_priority = self._volume_at_price[order.price]

        self._orders[order.order_id] = order
        logger.debug(
            "matching_engine.order_registered",
            order_id=order.order_id,
            side=order.side.value,
            price=str(order.price),
            size=str(order.size),
            queue_priority=str(order.queue_priority),
        )

    def cancel_order(self, order_id: str) -> Optional[Order]:
        """Cancel a registered order.

        Args:
            order_id: The order to cancel.

        Returns:
            The cancelled order, or None if not found.
        """
        order = self._orders.get(order_id)
        if order is None:
            logger.warning(
                "matching_engine.cancel_not_found", order_id=order_id
            )
            return None

        order.status = OrderStatus.CANCELLED
        logger.info(
            "matching_engine.order_cancelled",
            order_id=order_id,
            filled_size=str(order.filled_size),
        )
        return order

    # ------------------------------------------------------------------
    # Trade processing — the core pessimistic logic
    # ------------------------------------------------------------------

    def process_trade(self, trade: Trade) -> list[Fill]:
        """Evaluate a mainnet trade against all active virtual orders.

        This is the hot path. For each active order, we check:

        - **BID orders**: fill if ``trade.price < order.price``
          (strict improvement) OR if ``trade.price == order.price``
          AND sufficient queue volume has been consumed.

        - **ASK orders**: fill if ``trade.price > order.price``
          (strict improvement) OR if ``trade.price == order.price``
          AND sufficient queue volume has been consumed.

        Args:
            trade: A real trade from the Hyperliquid mainnet feed.

        Returns:
            List of generated ``Fill`` objects (may be empty).
        """
        if trade.market != self._market:
            return []

        self._total_trades_processed += 1

        # Update cumulative volume at this price level
        self._volume_at_price[trade.price] += trade.size

        fills: list[Fill] = []

        for order in list(self._orders.values()):
            if not order.is_active:
                continue

            fill = self._try_fill(order, trade)
            if fill is not None:
                fills.append(fill)

        if fills:
            self._total_fills_generated += len(fills)
            logger.info(
                "matching_engine.fills_generated",
                trade_price=str(trade.price),
                trade_size=str(trade.size),
                fill_count=len(fills),
            )

        return fills

    def _try_fill(self, order: Order, trade: Trade) -> Optional[Fill]:
        """Attempt to fill a single order against a trade.

        Implements the three-rule pessimistic model:
            1. Strict price improvement → immediate full/partial fill.
            2. At-price → fill only after queue is consumed.
            3. Worse price → no fill.

        Args:
            order: The virtual order to evaluate.
            trade: The incoming mainnet trade.

        Returns:
            A ``Fill`` if execution conditions are met, else None.
        """
        should_fill = False
        is_at_price = trade.price == order.price

        if order.side == Side.BID:
            # BID fills when market trades BELOW our bid
            if trade.price < order.price:
                should_fill = True
            elif is_at_price:
                should_fill = self._check_queue_fill(order, trade)

        elif order.side == Side.ASK:
            # ASK fills when market trades ABOVE our ask
            if trade.price > order.price:
                should_fill = True
            elif is_at_price:
                should_fill = self._check_queue_fill(order, trade)

        if not should_fill:
            return None

        return self._execute_fill(order, trade)

    def _check_queue_fill(self, order: Order, trade: Trade) -> bool:
        """Check if an at-price trade has consumed enough queue volume.

        The order fills when the cumulative volume traded at this price
        exceeds the order's queue position plus its remaining size.
        This means everyone ahead in the queue must be filled first.

        Args:
            order: The order being evaluated.
            trade: The current trade (at the order's price).

        Returns:
            True if sufficient volume has been consumed.
        """
        cumulative = self._volume_at_price[order.price]
        threshold = order.queue_priority + order.remaining
        return cumulative >= threshold

    def _execute_fill(self, order: Order, trade: Trade) -> Fill:
        """Execute a fill: update order state and return Fill record.

        The fill quantity is the minimum of the order's remaining size
        and the trade's size (partial fills are supported).

        Args:
            order: The order being filled.
            trade: The trade that triggered the fill.

        Returns:
            A ``Fill`` record.
        """
        fill_size = min(order.remaining, trade.size)

        order.filled_size += fill_size
        if order.filled_size >= order.size:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIALLY_FILLED

        fill = Fill(
            order_id=order.order_id,
            fill_price=order.price,  # Fill at the limit price, not trade price
            fill_size=fill_size,
            side=order.side,
            timestamp=trade.timestamp,
        )

        logger.debug(
            "matching_engine.fill_executed",
            order_id=order.order_id,
            fill_price=str(fill.fill_price),
            fill_size=str(fill.fill_size),
            order_status=order.status.value,
            remaining=str(order.remaining),
        )

        return fill

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------

    def purge_inactive(self) -> int:
        """Remove filled and cancelled orders from the registry.

        Returns:
            Number of orders purged.
        """
        inactive_ids = [
            oid for oid, o in self._orders.items() if not o.is_active
        ]
        for oid in inactive_ids:
            del self._orders[oid]

        if inactive_ids:
            logger.debug(
                "matching_engine.purged", count=len(inactive_ids)
            )
        return len(inactive_ids)

    def get_volume_at_price(self, price: Decimal) -> Decimal:
        """Return cumulative volume traded at a specific price level.

        Args:
            price: The price level to query.

        Returns:
            Cumulative volume.
        """
        return self._volume_at_price.get(price, Decimal("0"))

    def reset(self) -> None:
        """Reset the engine to a clean state."""
        self._orders.clear()
        self._volume_at_price.clear()
        self._total_trades_processed = 0
        self._total_fills_generated = 0
        logger.info("matching_engine.reset", market=self._market)
