"""Base strategy interface (Bring-Your-Own-Logic).

``BaseStrategy`` defines the contract that all user strategies must
implement. It follows the classic event-driven trading pattern:

    - ``on_orderbook_update(snapshot)`` — called on every L2 update.
    - ``on_trade(trade)`` — called on every mainnet trade.
    - ``on_fill(fill)`` — called when one of your virtual orders fills.
    - ``on_start()`` / ``on_stop()`` — lifecycle hooks.

Strategies receive a reference to the ``VirtualOMS`` so they can
submit and cancel orders. They also have read access to the
``VirtualWallet`` for portfolio queries.

Design Notes:
    - Strategies should be *stateless between sessions* — all state
      should be derivable from the wallet/OMS or stored in explicit
      strategy fields.
    - Avoid blocking calls in event handlers — use async where needed.
    - Log with ``self.log`` (a bound structlog logger) for consistent
      structured output.
"""

from __future__ import annotations

from decimal import Decimal

from hl_paper_trading.types import Fill, OrderBookSnapshot, Trade
from hl_paper_trading.utils import get_logger
from hl_paper_trading.virtual_oms import VirtualOMS
from hl_paper_trading.virtual_wallet import VirtualWallet


class BaseStrategy:
    """Abstract base class for paper trading strategies.

    Subclass this to implement your own market-making or directional
    strategy. Override the event handlers you need.

    Args:
        oms: The virtual order management system.
        wallet: The virtual wallet (read access for portfolio queries).
        name: Human-readable strategy name for logging.

    Example::

        class MyMM(BaseStrategy):
            def on_orderbook_update(self, snapshot):
                mid = snapshot.mid_price
                if mid:
                    self.oms.submit_order_sync(Side.BUY, mid - 0.01, 10)
                    self.oms.submit_order_sync(Side.SELL, mid + 0.01, 10)
    """

    def __init__(
        self,
        oms: VirtualOMS,
        wallet: VirtualWallet,
        name: str = "BaseStrategy",
    ) -> None:
        self._oms = oms
        self._wallet = wallet
        self._name = name
        self.log = get_logger(f"strategy.{name}")

        # Register fill callback
        self._oms.set_fill_callback(self._internal_on_fill)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def oms(self) -> VirtualOMS:
        """The virtual Order Management System."""
        return self._oms

    @property
    def wallet(self) -> VirtualWallet:
        """The virtual wallet (read-only access recommended)."""
        return self._wallet

    @property
    def name(self) -> str:
        """Strategy name."""
        return self._name

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        """Called when the simulation starts.

        Override to perform initialization (e.g., set initial quotes).
        Default implementation does nothing.
        """
        self.log.info("strategy.started", name=self._name)

    def on_stop(self) -> None:
        """Called when the simulation ends.

        Override to perform cleanup, log final statistics, etc.
        Default implementation cancels all open orders.
        """
        cancelled = self._oms.cancel_all()
        self.log.info(
            "strategy.stopped",
            name=self._name,
            cancelled_orders=cancelled,
        )

    # ------------------------------------------------------------------
    # Event handlers — override these
    # ------------------------------------------------------------------

    def on_orderbook_update(self, snapshot: OrderBookSnapshot) -> None:
        """Called on every order book L2 update.

        Args:
            snapshot: Current top-of-book snapshot.
        """
        pass

    def on_trade(self, trade: Trade) -> None:
        """Called on every mainnet trade.

        This is invoked *after* the trade has been processed by the
        matching engine (so any fills from this trade are already applied).

        Args:
            trade: The observed mainnet trade.
        """
        pass

    def on_fill(self, fill: Fill) -> None:
        """Called when one of your virtual orders is filled.

        Args:
            fill: The fill record.
        """
        pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _internal_on_fill(self, fill: Fill) -> None:
        """Internal fill handler — logs and delegates to user override."""
        self.log.info(
            "strategy.fill",
            order_id=fill.order_id,
            side=fill.side.value,
            price=str(fill.fill_price),
            size=str(fill.fill_size),
        )
        self.on_fill(fill)

    # ------------------------------------------------------------------
    # Convenience methods for subclasses
    # ------------------------------------------------------------------

    def get_position(self) -> Decimal:
        """Current total spot-token inventory for the engine coin."""
        return self._wallet.total_balance(self._oms.coin)

    def get_mid_price(self, snapshot: OrderBookSnapshot) -> Decimal | None:
        """Extract mid price from an order book snapshot.

        Args:
            snapshot: Order book snapshot.

        Returns:
            Mid price or None if no two-sided market.
        """
        return snapshot.mid_price

    def cancel_all_orders(self) -> int:
        """Cancel all outstanding virtual orders.

        Returns:
            Number of orders cancelled.
        """
        return self._oms.cancel_all()
