#!/usr/bin/env python3
"""Connect to Hyperliquid mainnet and paper-trade a live outcome market.

This example demonstrates the full pipeline:
1. Subscribe to real mainnet WebSocket trades for a HIP-4 outcome
2. Feed trades through the pessimistic matching engine
3. Track PnL in real-time via VirtualWallet

Usage::

    # Paper-trade BTC daily outcome (YES side)
    python examples/live_paper_trade.py --outcome-id 1 --side 0

    # With testnet
    python examples/live_paper_trade.py --outcome-id 1 --testnet

Requirements:
    pip install websockets>=12.0
"""

from __future__ import annotations

import argparse
import asyncio
import signal
from decimal import Decimal

from hl_paper_trading import (
    BaseStrategy,
    Fill,
    HyperliquidWS,
    MatchingEngine,
    OrderBookSnapshot,
    Side,
    Trade,
    VirtualOMS,
    VirtualWallet,
    outcome_coin_name,
)
from hl_paper_trading.utils import setup_logging, get_logger

logger = get_logger(__name__)


class LiveInventorySkewMM(BaseStrategy):
    """Simple market-maker that runs on live outcome data.

    Places symmetric quotes around the mid price with an inventory
    skew to manage directional risk.
    """

    def __init__(
        self,
        oms: VirtualOMS,
        wallet: VirtualWallet,
        half_spread: Decimal = Decimal("0.015"),
        order_size: Decimal = Decimal("25"),
        skew_factor: Decimal = Decimal("0.0002"),
    ) -> None:
        super().__init__(oms=oms, wallet=wallet)
        self.half_spread = half_spread
        self.order_size = order_size
        self.skew_factor = skew_factor

    def on_orderbook_update(self, snapshot: OrderBookSnapshot) -> None:
        mid = self.get_mid_price(snapshot)
        if mid is None:
            return

        self.cancel_all_orders()

        position = self.get_position()
        skew = position * self.skew_factor

        bid = mid - self.half_spread - skew
        ask = mid + self.half_spread - skew

        # Clamp to [0.01, 0.99]
        bid = max(bid, Decimal("0.01"))
        ask = min(ask, Decimal("0.99"))

        self.oms.submit_order_sync(Side.BID, bid, self.order_size)
        self.oms.submit_order_sync(Side.ASK, ask, self.order_size)

    def on_fill(self, fill: Fill) -> None:
        snap = self.wallet.snapshot(mark_price=fill.fill_price)
        logger.info(
            "live_fill",
            side=fill.side.value,
            price=str(fill.fill_price),
            size=str(fill.fill_size),
            total_pnl=str(snap.total_pnl),
            yes_inv=str(snap.yes_inventory),
        )


async def run_live(
    outcome_id: int,
    side: int,
    testnet: bool,
    balance: Decimal,
    log_level: str,
) -> None:
    """Main async loop for live paper trading."""
    setup_logging(json_output=False, level=log_level)

    coin = outcome_coin_name(outcome_id, side)
    logger.info(
        "starting_live_paper_trading",
        outcome_id=outcome_id,
        coin=coin,
        testnet=testnet,
    )

    wallet = VirtualWallet(initial_balance=balance)
    engine = MatchingEngine(market=coin)
    oms = VirtualOMS(
        wallet=wallet,
        engine=engine,
        market=coin,
        latency_ms=50,
    )
    strategy = LiveInventorySkewMM(oms=oms, wallet=wallet)

    ws = HyperliquidWS(
        outcome_id=outcome_id,
        side=side,
        testnet=testnet,
        subscribe_trades=True,
        subscribe_l2=True,
    )

    trade_count = 0

    print(f"\n{'='*60}")
    print(f"  Live Paper Trading — {coin}")
    print(f"  Endpoint: {'testnet' if testnet else 'mainnet'}")
    print(f"  Balance:  {balance} USDC")
    print(f"  Press Ctrl+C to stop")
    print(f"{'='*60}\n")

    try:
        async for event in ws.stream():
            if isinstance(event, Trade):
                trade_count += 1
                fills = oms.process_trade(event)
                strategy.on_trade(event)
                for fill in fills:
                    strategy.on_fill(fill)

                if trade_count % 100 == 0:
                    snap = wallet.snapshot(mark_price=event.price)
                    print(
                        f"  [{trade_count:>6} trades] "
                        f"Price={event.price:.4f}  "
                        f"PnL={snap.total_pnl:+.4f}  "
                        f"YES={snap.yes_inventory}"
                    )

            elif isinstance(event, OrderBookSnapshot):
                strategy.on_orderbook_update(event)

    except KeyboardInterrupt:
        await ws.close()

    # Final summary
    snap = wallet.snapshot(mark_price=Decimal("0.50"))
    print(f"\n{'='*60}")
    print(f"  SESSION SUMMARY")
    print(f"{'='*60}")
    print(f"  Trades Received:   {trade_count}")
    print(f"  Fills Generated:   {engine.stats['total_fills_generated']}")
    print(f"  USDC Balance:      {snap.usdc_balance:.4f}")
    print(f"  YES Inventory:     {snap.yes_inventory}")
    print(f"  Total PnL:         {snap.total_pnl:+.4f}")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Live paper trading on Hyperliquid outcome markets"
    )
    parser.add_argument(
        "--outcome-id", type=int, default=1,
        help="HIP-4 outcome ID (default: 1 = BTC daily)",
    )
    parser.add_argument(
        "--side", type=int, default=0, choices=[0, 1],
        help="0 = YES, 1 = NO (default: 0)",
    )
    parser.add_argument("--testnet", action="store_true", help="Use testnet")
    parser.add_argument(
        "--balance", type=Decimal, default=Decimal("10000"),
        help="Initial USDC balance",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    asyncio.run(run_live(
        outcome_id=args.outcome_id,
        side=args.side,
        testnet=args.testnet,
        balance=args.balance,
        log_level=args.log_level,
    ))


if __name__ == "__main__":
    main()
