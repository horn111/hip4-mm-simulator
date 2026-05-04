"""Virtual portfolio and wallet accounting for paper trading.

``VirtualWallet`` tracks USDC balance, YES/NO contract inventory,
average entry prices (VWAP), and both realised and unrealised PnL.

All arithmetic uses ``Decimal`` to avoid floating-point drift — a
critical requirement for any trading system, even a simulator.

HIP-4 Outcome Market Accounting:
    - Buying YES at price *p* costs *p* USDC per contract.
    - Selling YES at price *p* returns *p* USDC per contract.
    - At settlement: winning contracts pay 1.0 USDC, losers pay 0.0.
    - YES + NO = 1.0 USDC always (complementary pair).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from hl_paper_trading.types import Fill, PortfolioSnapshot, Side
from hl_paper_trading.utils import decimal_round, get_logger

logger = get_logger(__name__)


class VirtualWallet:
    """Simulated portfolio for HIP-4 outcome market paper trading.

    Manages USDC cash balance, YES/NO contract inventories, and tracks
    average entry prices and PnL in real time.

    Args:
        initial_balance: Starting USDC balance. Defaults to 10 000.

    Example::

        wallet = VirtualWallet(initial_balance=Decimal("5000"))
        wallet.apply_fill(fill)
        snapshot = wallet.snapshot(mark_price=Decimal("0.65"))
    """

    def __init__(self, initial_balance: Decimal = Decimal("10000")) -> None:
        self._initial_balance = initial_balance
        self._usdc_balance = initial_balance

        # Contract inventories (positive = long, negative = short)
        self._yes_inventory: Decimal = Decimal("0")
        self._no_inventory: Decimal = Decimal("0")

        # Volume-weighted average entry prices
        self._avg_entry_yes: Decimal = Decimal("0")
        self._avg_entry_no: Decimal = Decimal("0")

        # Cumulative cost basis for VWAP tracking
        self._total_cost_yes: Decimal = Decimal("0")
        self._total_cost_no: Decimal = Decimal("0")

        # PnL tracking
        self._realized_pnl: Decimal = Decimal("0")

        # Fill history
        self._fills: list[Fill] = []

        logger.info(
            "wallet.initialized",
            initial_balance=str(initial_balance),
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def usdc_balance(self) -> Decimal:
        """Current USDC cash balance."""
        return self._usdc_balance

    @property
    def yes_inventory(self) -> Decimal:
        """Net YES contract position (positive = long)."""
        return self._yes_inventory

    @property
    def no_inventory(self) -> Decimal:
        """Net NO contract position (positive = long)."""
        return self._no_inventory

    @property
    def avg_entry_price_yes(self) -> Decimal:
        """Volume-weighted average entry price for YES position."""
        return self._avg_entry_yes

    @property
    def avg_entry_price_no(self) -> Decimal:
        """Volume-weighted average entry price for NO position."""
        return self._avg_entry_no

    @property
    def realized_pnl(self) -> Decimal:
        """Cumulative realised PnL in USDC."""
        return self._realized_pnl

    @property
    def fills(self) -> list[Fill]:
        """Complete fill history."""
        return list(self._fills)

    # ------------------------------------------------------------------
    # Fill application
    # ------------------------------------------------------------------

    def apply_fill(self, fill: Fill) -> None:
        """Apply a simulated fill to the portfolio.

        Updates inventory, average entry price, USDC balance, and
        realised PnL according to the fill's side and price.

        For BID fills (buying YES):
            - Debit USDC by ``fill_price × fill_size``.
            - Increase YES inventory.

        For ASK fills (selling YES):
            - Credit USDC by ``fill_price × fill_size``.
            - Decrease YES inventory.
            - Realise PnL on the closed portion.

        Args:
            fill: The ``Fill`` to apply.
        """
        cost = fill.fill_price * fill.fill_size

        if fill.side == Side.BID:
            self._apply_buy(fill, cost)
        else:
            self._apply_sell(fill, cost)

        self._fills.append(fill)

        logger.info(
            "wallet.fill_applied",
            side=fill.side.value,
            price=str(fill.fill_price),
            size=str(fill.fill_size),
            usdc_balance=str(decimal_round(self._usdc_balance)),
            yes_inventory=str(self._yes_inventory),
            realized_pnl=str(decimal_round(self._realized_pnl)),
        )

    def _apply_buy(self, fill: Fill, cost: Decimal) -> None:
        """Handle a BID fill (buying YES contracts).

        If we have existing short YES inventory, this is a cover
        (realises PnL). Otherwise it increases the long position.
        """
        self._usdc_balance -= cost

        if self._yes_inventory < 0:
            # Covering a short: realise PnL
            cover_qty = min(fill.fill_size, abs(self._yes_inventory))
            pnl = cover_qty * (self._avg_entry_yes - fill.fill_price)
            self._realized_pnl += pnl
            self._yes_inventory += fill.fill_size

            # Reset avg entry if flipped to long
            if self._yes_inventory > 0:
                self._avg_entry_yes = fill.fill_price
                self._total_cost_yes = fill.fill_price * self._yes_inventory
            elif self._yes_inventory == 0:
                self._avg_entry_yes = Decimal("0")
                self._total_cost_yes = Decimal("0")
        else:
            # Adding to long or opening new long
            self._total_cost_yes += cost
            self._yes_inventory += fill.fill_size
            if self._yes_inventory > 0:
                self._avg_entry_yes = self._total_cost_yes / self._yes_inventory

    def _apply_sell(self, fill: Fill, cost: Decimal) -> None:
        """Handle an ASK fill (selling YES contracts).

        If we have existing long YES inventory, this closes the
        position and realises PnL. Otherwise opens/increases a short.
        """
        self._usdc_balance += cost

        if self._yes_inventory > 0:
            # Closing a long: realise PnL
            close_qty = min(fill.fill_size, self._yes_inventory)
            pnl = close_qty * (fill.fill_price - self._avg_entry_yes)
            self._realized_pnl += pnl
            self._yes_inventory -= fill.fill_size

            # Reset avg entry if flipped to short
            if self._yes_inventory < 0:
                self._avg_entry_yes = fill.fill_price
                self._total_cost_yes = fill.fill_price * abs(self._yes_inventory)
            elif self._yes_inventory == 0:
                self._avg_entry_yes = Decimal("0")
                self._total_cost_yes = Decimal("0")
            else:
                self._total_cost_yes = self._avg_entry_yes * self._yes_inventory
        else:
            # Opening or adding to short
            self._total_cost_yes += cost
            self._yes_inventory -= fill.fill_size
            if self._yes_inventory < 0:
                self._avg_entry_yes = self._total_cost_yes / abs(self._yes_inventory)

    # ------------------------------------------------------------------
    # Unrealised PnL
    # ------------------------------------------------------------------

    def unrealized_pnl(self, mark_price: Decimal) -> Decimal:
        """Calculate unrealised PnL at the given mark price.

        Args:
            mark_price: Current mid or last-trade price for YES.

        Returns:
            Unrealised PnL in USDC.
        """
        if self._yes_inventory > 0:
            return self._yes_inventory * (mark_price - self._avg_entry_yes)
        elif self._yes_inventory < 0:
            return abs(self._yes_inventory) * (self._avg_entry_yes - mark_price)
        return Decimal("0")

    def total_pnl(self, mark_price: Decimal) -> Decimal:
        """Realised + unrealised PnL.

        Args:
            mark_price: Current mark price for YES.

        Returns:
            Total PnL in USDC.
        """
        return self._realized_pnl + self.unrealized_pnl(mark_price)

    # ------------------------------------------------------------------
    # Snapshots & validation
    # ------------------------------------------------------------------

    def snapshot(self, mark_price: Optional[Decimal] = None) -> PortfolioSnapshot:
        """Generate a point-in-time portfolio snapshot.

        Args:
            mark_price: Current mark price for unrealised PnL.
                        If None, unrealised PnL is reported as 0.

        Returns:
            Frozen ``PortfolioSnapshot``.
        """
        u_pnl = self.unrealized_pnl(mark_price) if mark_price else Decimal("0")
        return PortfolioSnapshot(
            usdc_balance=decimal_round(self._usdc_balance),
            yes_inventory=self._yes_inventory,
            no_inventory=self._no_inventory,
            avg_entry_price_yes=decimal_round(self._avg_entry_yes),
            avg_entry_price_no=decimal_round(self._avg_entry_no),
            realized_pnl=decimal_round(self._realized_pnl),
            unrealized_pnl=decimal_round(u_pnl),
            total_pnl=decimal_round(self._realized_pnl + u_pnl),
        )

    def has_sufficient_balance(self, cost: Decimal) -> bool:
        """Check if the wallet can afford a given cost.

        Args:
            cost: USDC amount to check against.

        Returns:
            True if ``usdc_balance >= cost``.
        """
        return self._usdc_balance >= cost

    def reset(self) -> None:
        """Reset the wallet to its initial state."""
        self.__init__(initial_balance=self._initial_balance)  # type: ignore[misc]
        logger.info("wallet.reset", initial_balance=str(self._initial_balance))
