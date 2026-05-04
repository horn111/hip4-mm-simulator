"""Example: Simple market-making strategy with inventory skew.

This demonstrates how to build a strategy on top of the paper trading
framework. The strategy:

    1. Quotes a symmetric spread around the mid price.
    2. Applies an inventory skew: if long, widen the bid and tighten
       the ask (incentivize reducing inventory). Vice-versa if short.
    3. Cancels and re-quotes on every order book update.
    4. Enforces a maximum inventory limit.

This is a *teaching example* — not a production strategy. Real MM
strategies would include features like:
    - Adverse selection detection
    - Dynamic spread based on volatility
    - Fill rate optimization
    - Multi-leg hedging

Usage::

    python -m examples.basic_strategy
"""

from __future__ import annotations

from decimal import Decimal

from hl_paper_trading.strategy import BaseStrategy
from hl_paper_trading.types import Fill, OrderBookSnapshot, Side, Trade
from hl_paper_trading.virtual_oms import VirtualOMS
from hl_paper_trading.virtual_wallet import VirtualWallet


class InventorySkewMM(BaseStrategy):
    """Market-making strategy with linear inventory skew.

    Adjusts quotes to actively reduce inventory imbalances. When long,
    the bid is lowered (less aggressive buying) and the ask is raised
    (more aggressive selling), pushing the market to flatten the position.

    Args:
        oms: Virtual order management system.
        wallet: Virtual wallet.
        half_spread: Half the base spread width (e.g., 0.02 = 2 cents).
        order_size: Size of each quote (in contracts).
        max_inventory: Maximum absolute inventory before halting quotes.
        skew_factor: How much to adjust price per unit of inventory.
    """

    def __init__(
        self,
        oms: VirtualOMS,
        wallet: VirtualWallet,
        half_spread: Decimal = Decimal("0.02"),
        order_size: Decimal = Decimal("50"),
        max_inventory: Decimal = Decimal("500"),
        skew_factor: Decimal = Decimal("0.0001"),
    ) -> None:
        super().__init__(oms=oms, wallet=wallet, name="InventorySkewMM")
        self._half_spread = half_spread
        self._order_size = order_size
        self._max_inventory = max_inventory
        self._skew_factor = skew_factor
        self._update_count = 0

    def on_start(self) -> None:
        """Log strategy parameters on start."""
        self.log.info(
            "strategy.config",
            half_spread=str(self._half_spread),
            order_size=str(self._order_size),
            max_inventory=str(self._max_inventory),
            skew_factor=str(self._skew_factor),
        )

    def on_orderbook_update(self, snapshot: OrderBookSnapshot) -> None:
        """Re-quote on every order book update.

        Steps:
            1. Cancel all existing orders.
            2. Compute skew-adjusted bid and ask prices.
            3. Submit new quotes (if within inventory limits).
        """
        self._update_count += 1

        mid = self.get_mid_price(snapshot)
        if mid is None:
            return  # No two-sided market — don't quote

        # Cancel stale orders
        self.cancel_all_orders()

        # Current inventory position
        position = self.get_position()

        # Linear skew: positive inventory → lower bid, raise ask
        skew = position * self._skew_factor

        # Compute adjusted prices
        bid_price = mid - self._half_spread - skew
        ask_price = mid + self._half_spread - skew  # Skew shifts both

        # Clamp to valid range [0.01, 0.99]
        bid_price = max(Decimal("0.01"), min(Decimal("0.99"), bid_price))
        ask_price = max(Decimal("0.01"), min(Decimal("0.99"), ask_price))

        # Round to 4 decimal places
        bid_price = bid_price.quantize(Decimal("0.0001"))
        ask_price = ask_price.quantize(Decimal("0.0001"))

        # Don't quote if inventory at limit
        abs_position = abs(position)
        can_bid = abs_position < self._max_inventory or position < 0
        can_ask = abs_position < self._max_inventory or position > 0

        if can_bid and bid_price > 0:
            self.oms.submit_order_sync(
                side=Side.BID,
                price=bid_price,
                size=self._order_size,
            )

        if can_ask and ask_price < Decimal("1"):
            self.oms.submit_order_sync(
                side=Side.ASK,
                price=ask_price,
                size=self._order_size,
            )

        # Periodic logging
        if self._update_count % 100 == 0:
            snap = self.wallet.snapshot(mark_price=mid)
            self.log.info(
                "strategy.periodic_report",
                update_count=self._update_count,
                mid=str(mid),
                position=str(position),
                skew=str(skew),
                bid=str(bid_price),
                ask=str(ask_price),
                realized_pnl=str(snap.realized_pnl),
                unrealized_pnl=str(snap.unrealized_pnl),
                total_pnl=str(snap.total_pnl),
                usdc_balance=str(snap.usdc_balance),
            )

    def on_trade(self, trade: Trade) -> None:
        """Optional: track trade flow for analytics."""
        pass

    def on_fill(self, fill: Fill) -> None:
        """Log fills with context."""
        position = self.get_position()
        self.log.info(
            "strategy.fill_received",
            side=fill.side.value,
            price=str(fill.fill_price),
            size=str(fill.fill_size),
            new_position=str(position),
        )

    def on_stop(self) -> None:
        """Print final summary."""
        super().on_stop()
        self.log.info(
            "strategy.final_summary",
            total_updates=self._update_count,
            final_position=str(self.get_position()),
            realized_pnl=str(self.wallet.realized_pnl),
        )
