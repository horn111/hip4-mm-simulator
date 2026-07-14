"""A small spot-safe inventory-skew example strategy."""

from __future__ import annotations

from decimal import Decimal

from hl_paper_trading import BaseStrategy, Fill, OrderBookSnapshot, Side, Trade
from hl_paper_trading.virtual_oms import VirtualOMS
from hl_paper_trading.virtual_wallet import VirtualWallet


class InventorySkewMM(BaseStrategy):
    """Teaching baseline; it is not a profitability claim."""

    def __init__(
        self,
        oms: VirtualOMS,
        wallet: VirtualWallet,
        *,
        order_size: Decimal = Decimal("10"),
        target_inventory: Decimal = Decimal("1000"),
        skew_factor: Decimal = Decimal("0.00001"),
    ) -> None:
        super().__init__(oms, wallet, name="InventorySkewMM")
        self.order_size = order_size
        self.target_inventory = target_inventory
        self.skew_factor = skew_factor

    def on_orderbook_update(self, snapshot: OrderBookSnapshot) -> None:
        if snapshot.best_bid is None or snapshot.best_ask is None:
            return
        inventory_delta = self.get_position() - self.target_inventory
        skew = inventory_delta * self.skew_factor
        bid = max(Decimal("0.001"), min(Decimal("0.999"), snapshot.best_bid - skew))
        ask = max(Decimal("0.001"), min(Decimal("0.999"), snapshot.best_ask - skew))
        desired = {(Side.BUY, bid), (Side.SELL, ask)}
        existing = {
            (order.side, order.price)
            for order in self.oms.open_orders + self.oms.pending_orders
        }
        if desired == existing:
            return
        self.cancel_all_orders()
        self.oms.submit_order_sync(
            Side.BUY, bid, self.order_size, current_time=snapshot.timestamp
        )
        self.oms.submit_order_sync(
            Side.SELL, ask, self.order_size, current_time=snapshot.timestamp
        )

    def on_trade(self, trade: Trade) -> None:
        return

    def on_fill(self, fill: Fill) -> None:
        self.log.info(
            "baseline.fill",
            side=fill.side.value,
            price=str(fill.fill_price),
            size=str(fill.fill_size),
        )
