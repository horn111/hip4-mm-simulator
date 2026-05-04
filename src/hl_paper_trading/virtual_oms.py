"""Virtual Order Management System (OMS) with latency simulation.

``VirtualOMS`` is the control plane between strategies and the matching
engine. It manages order lifecycle, enforces risk limits, and simulates
the latency between order submission and arrival at the exchange.

Latency Model:
    Real Hyperliquid API latency is typically 30–100 ms. We simulate this
    by holding orders in ``PENDING`` status for a configurable duration
    (default: 50 ms) before transitioning them to ``OPEN``. During the
    pending window, the order cannot be filled — this prevents strategies
    from "seeing" a trade and placing an order that retroactively catches it.

Risk Controls:
    - Maximum order size enforcement.
    - Maximum number of open orders.
    - Pre-trade balance check (insufficient funds → REJECTED).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Optional

from hl_paper_trading.matching_engine import MatchingEngine
from hl_paper_trading.types import (
    Fill,
    Order,
    OrderBookSnapshot,
    OrderStatus,
    OrderType,
    Side,
    Trade,
)
from hl_paper_trading.utils import Config, get_logger
from hl_paper_trading.virtual_wallet import VirtualWallet

logger = get_logger(__name__)


# Type alias for fill callbacks
FillCallback = Callable[[Fill], None]


class VirtualOMS:
    """Order Management System for paper trading.

    Manages the full order lifecycle: submission → pending (latency) →
    open → (partial) fill → filled/cancelled.

    Args:
        wallet: The virtual wallet for balance checks and fill application.
        engine: The matching engine for trade-based fill evaluation.
        config: Configuration object (latency_ms, max_order_size, etc.).

    Example::

        oms = VirtualOMS(wallet=wallet, engine=engine)
        order_id = await oms.submit_order(
            side=Side.BID,
            price=Decimal("0.45"),
            size=Decimal("100"),
        )
        await oms.cancel_order(order_id)
    """

    def __init__(
        self,
        wallet: VirtualWallet,
        engine: MatchingEngine,
        config: Optional[Config] = None,
    ) -> None:
        self._wallet = wallet
        self._engine = engine
        self._config = config or Config()

        # Configuration
        self._latency_ms: int = self._config.get_int("latency_ms", default=50)
        self._max_order_size: Decimal = self._config.get_decimal(
            "max_order_size", default=Decimal("1000")
        )
        self._max_open_orders: int = self._config.get_int(
            "max_open_orders", default=50
        )

        # All orders indexed by ID (full history)
        self._orders: dict[str, Order] = {}

        # Pending orders awaiting latency expiry
        self._pending_orders: dict[str, datetime] = {}  # order_id → activate_at

        # Fill callback
        self._on_fill: Optional[FillCallback] = None

        # Statistics
        self._total_submitted: int = 0
        self._total_rejected: int = 0
        self._total_cancelled: int = 0

        logger.info(
            "oms.initialized",
            latency_ms=self._latency_ms,
            max_order_size=str(self._max_order_size),
            max_open_orders=self._max_open_orders,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def open_orders(self) -> list[Order]:
        """All orders with status OPEN or PARTIALLY_FILLED."""
        return [o for o in self._orders.values() if o.is_active]

    @property
    def pending_orders(self) -> list[Order]:
        """Orders still in the latency window."""
        return [
            self._orders[oid]
            for oid in self._pending_orders
            if oid in self._orders
        ]

    @property
    def all_orders(self) -> list[Order]:
        """Full order history."""
        return list(self._orders.values())

    @property
    def stats(self) -> dict[str, int]:
        """OMS statistics."""
        return {
            "total_submitted": self._total_submitted,
            "total_rejected": self._total_rejected,
            "total_cancelled": self._total_cancelled,
            "open_orders": len(self.open_orders),
            "pending_orders": len(self._pending_orders),
        }

    # ------------------------------------------------------------------
    # Fill callback
    # ------------------------------------------------------------------

    def set_fill_callback(self, callback: FillCallback) -> None:
        """Register a callback invoked on each fill.

        Args:
            callback: Function accepting a ``Fill`` object.
        """
        self._on_fill = callback

    # ------------------------------------------------------------------
    # Order submission
    # ------------------------------------------------------------------

    async def submit_order(
        self,
        side: Side,
        price: Decimal,
        size: Decimal,
        market: Optional[str] = None,
    ) -> Optional[str]:
        """Submit a new limit order with simulated latency.

        The order transitions through:
            PENDING → (wait latency_ms) → OPEN → eligible for fills.

        Pre-trade checks:
            1. Size ≤ max_order_size.
            2. Open order count < max_open_orders.
            3. Sufficient USDC balance for BID orders.

        Args:
            side: BID or ASK.
            price: Limit price in [0.0, 1.0].
            size: Number of contracts.
            market: Market symbol (defaults to engine's market).

        Returns:
            Order ID on success, None if rejected.
        """
        market = market or self._engine.market
        self._total_submitted += 1

        # --- Risk checks ---
        rejection_reason = self._pre_trade_check(side, price, size)
        if rejection_reason:
            self._total_rejected += 1
            logger.warning(
                "oms.order_rejected",
                reason=rejection_reason,
                side=side.value,
                price=str(price),
                size=str(size),
            )
            return None

        # --- Create order ---
        order = Order(
            market=market,
            side=side,
            price=price,
            size=size,
            status=OrderStatus.PENDING,
        )
        self._orders[order.order_id] = order

        # --- Schedule activation after latency ---
        activate_at = datetime.now(timezone.utc) + timedelta(
            milliseconds=self._latency_ms
        )
        self._pending_orders[order.order_id] = activate_at

        logger.info(
            "oms.order_submitted",
            order_id=order.order_id,
            side=side.value,
            price=str(price),
            size=str(size),
            activate_at=activate_at.isoformat(),
        )

        # Simulate latency
        await asyncio.sleep(self._latency_ms / 1000.0)
        self._activate_order(order.order_id)

        return order.order_id

    def submit_order_sync(
        self,
        side: Side,
        price: Decimal,
        size: Decimal,
        market: Optional[str] = None,
        current_time: Optional[datetime] = None,
    ) -> Optional[str]:
        """Synchronous order submission (for backtesting without asyncio).

        The order is placed in PENDING status. Call ``activate_pending()``
        with the current simulation time to transition orders to OPEN.

        Args:
            side: BID or ASK.
            price: Limit price in [0.0, 1.0].
            size: Number of contracts.
            market: Market symbol (defaults to engine's market).
            current_time: Current simulation time.

        Returns:
            Order ID on success, None if rejected.
        """
        market = market or self._engine.market
        now = current_time or datetime.now(timezone.utc)
        self._total_submitted += 1

        rejection_reason = self._pre_trade_check(side, price, size)
        if rejection_reason:
            self._total_rejected += 1
            logger.warning(
                "oms.order_rejected",
                reason=rejection_reason,
                side=side.value,
                price=str(price),
                size=str(size),
            )
            return None

        order = Order(
            market=market,
            side=side,
            price=price,
            size=size,
            status=OrderStatus.PENDING,
            created_at=now,
        )
        self._orders[order.order_id] = order

        activate_at = now + timedelta(milliseconds=self._latency_ms)
        self._pending_orders[order.order_id] = activate_at

        logger.info(
            "oms.order_submitted_sync",
            order_id=order.order_id,
            side=side.value,
            price=str(price),
            size=str(size),
        )
        return order.order_id

    # ------------------------------------------------------------------
    # Order activation
    # ------------------------------------------------------------------

    def activate_pending(self, current_time: Optional[datetime] = None) -> int:
        """Activate pending orders whose latency window has expired.

        Call this periodically in backtesting mode to transition orders
        from PENDING to OPEN at the correct simulated time.

        Args:
            current_time: The current simulation time. If None, uses
                          wall-clock time.

        Returns:
            Number of orders activated.
        """
        now = current_time or datetime.now(timezone.utc)
        activated = 0

        expired = [
            oid for oid, at in self._pending_orders.items() if now >= at
        ]

        for oid in expired:
            self._activate_order(oid)
            activated += 1

        return activated

    def _activate_order(self, order_id: str) -> None:
        """Transition an order from PENDING to OPEN.

        Registers the order with the matching engine.

        Args:
            order_id: The order to activate.
        """
        if order_id not in self._orders:
            return

        order = self._orders[order_id]
        if order.status != OrderStatus.PENDING:
            return

        order.status = OrderStatus.OPEN
        order.activated_at = datetime.now(timezone.utc)

        # Remove from pending tracking
        self._pending_orders.pop(order_id, None)

        # Register with matching engine
        self._engine.register_order(order)

        logger.debug(
            "oms.order_activated",
            order_id=order_id,
            side=order.side.value,
            price=str(order.price),
        )

    # ------------------------------------------------------------------
    # Order cancellation
    # ------------------------------------------------------------------

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order (with simulated latency).

        Args:
            order_id: The order to cancel.

        Returns:
            True if cancelled, False if not found or already terminal.
        """
        # Simulate cancel latency
        await asyncio.sleep(self._latency_ms / 1000.0)
        return self.cancel_order_sync(order_id)

    def cancel_order_sync(self, order_id: str) -> bool:
        """Cancel an order synchronously.

        Args:
            order_id: The order to cancel.

        Returns:
            True if cancelled, False if not found or already terminal.
        """
        order = self._orders.get(order_id)
        if order is None:
            return False

        if order.status in (OrderStatus.PENDING,):
            order.status = OrderStatus.CANCELLED
            self._pending_orders.pop(order_id, None)
            self._total_cancelled += 1
            logger.info("oms.order_cancelled", order_id=order_id, was="PENDING")
            return True

        if order.is_active:
            self._engine.cancel_order(order_id)
            self._total_cancelled += 1
            logger.info("oms.order_cancelled", order_id=order_id)
            return True

        return False

    def cancel_all(self) -> int:
        """Cancel all active and pending orders.

        Returns:
            Number of orders cancelled.
        """
        count = 0
        for order in list(self._orders.values()):
            if order.status == OrderStatus.PENDING or order.is_active:
                if self.cancel_order_sync(order.order_id):
                    count += 1
        return count

    # ------------------------------------------------------------------
    # Trade processing (delegate to engine, apply fills)
    # ------------------------------------------------------------------

    def process_trade(self, trade: Trade) -> list[Fill]:
        """Process a mainnet trade: check for fills and apply them.

        This is typically called by the event loop for every incoming
        trade from the WebSocket feed. The flow:
            1. Activate any pending orders whose latency has expired.
            2. Delegate to the matching engine.
            3. Apply fills to the wallet.
            4. Invoke fill callbacks.

        Args:
            trade: Real trade from the Hyperliquid feed.

        Returns:
            List of fills generated.
        """
        # Activate pending orders based on trade timestamp
        self.activate_pending(current_time=trade.timestamp)

        # Process through matching engine
        fills = self._engine.process_trade(trade)

        # Apply each fill to the wallet
        for fill in fills:
            self._wallet.apply_fill(fill)
            if self._on_fill:
                self._on_fill(fill)

        return fills

    # ------------------------------------------------------------------
    # Pre-trade risk checks
    # ------------------------------------------------------------------

    def _pre_trade_check(
        self, side: Side, price: Decimal, size: Decimal
    ) -> Optional[str]:
        """Run pre-trade risk checks.

        Args:
            side: Order side.
            price: Order price.
            size: Order size.

        Returns:
            Rejection reason string, or None if all checks pass.
        """
        # Max order size
        if size > self._max_order_size:
            return f"Size {size} exceeds max {self._max_order_size}"

        # Max open orders
        active_count = len(self.open_orders) + len(self._pending_orders)
        if active_count >= self._max_open_orders:
            return f"Open order limit reached ({self._max_open_orders})"

        # Balance check for BID orders
        if side == Side.BID:
            cost = price * size
            if not self._wallet.has_sufficient_balance(cost):
                return (
                    f"Insufficient balance: need {cost}, "
                    f"have {self._wallet.usdc_balance}"
                )

        return None

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_order(self, order_id: str) -> Optional[Order]:
        """Look up an order by ID.

        Args:
            order_id: The order identifier.

        Returns:
            The ``Order`` object, or None if not found.
        """
        return self._orders.get(order_id)

    def get_open_orders_by_side(self, side: Side) -> list[Order]:
        """Get all active orders on a given side.

        Args:
            side: BID or ASK.

        Returns:
            List of matching active orders.
        """
        return [o for o in self.open_orders if o.side == side]
