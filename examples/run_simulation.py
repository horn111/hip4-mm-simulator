"""Example: Run a complete paper trading simulation.

This script demonstrates the full end-to-end workflow:

    1. Initialize the framework (wallet, engine, OMS).
    2. Create a MockHyperliquidWS for synthetic data.
    3. Instantiate the InventorySkewMM strategy.
    4. Run the simulation loop.
    5. Print final portfolio report.

Usage::

    python examples/run_simulation.py
    python examples/run_simulation.py --trades 5000 --balance 25000
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

# Add parent directory to path for development
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hl_paper_trading.matching_engine import MatchingEngine
from hl_paper_trading.mock_ws import MockHyperliquidWS
from hl_paper_trading.utils import Config, setup_logging, get_logger
from hl_paper_trading.virtual_oms import VirtualOMS
from hl_paper_trading.virtual_wallet import VirtualWallet

from basic_strategy import InventorySkewMM

logger = get_logger(__name__)


async def run_simulation(
    num_trades: int = 2000,
    initial_balance: Decimal = Decimal("10000"),
    initial_price: Decimal = Decimal("0.50"),
    seed: int = 42,
) -> None:
    """Run a complete paper trading simulation.

    Args:
        num_trades: Number of synthetic trades to process.
        initial_balance: Starting USDC balance.
        initial_price: Starting price for the synthetic market.
        seed: Random seed for reproducibility.
    """
    market = "OUTCOME-DEMO"

    # --- Infrastructure setup ---
    config = Config(
        initial_balance=str(initial_balance),
        latency_ms="50",
        market=market,
    )

    wallet = VirtualWallet(initial_balance=initial_balance)
    engine = MatchingEngine(market=market)
    oms = VirtualOMS(wallet=wallet, engine=engine, config=config)

    # --- Mock WebSocket ---
    ws = MockHyperliquidWS(
        market=market,
        initial_price=initial_price,
        tick_interval_ms=50,
        volatility=0.008,
        seed=seed,
    )

    # --- Strategy ---
    strategy = InventorySkewMM(
        oms=oms,
        wallet=wallet,
        half_spread=Decimal("0.008"),
        order_size=Decimal("25"),
        max_inventory=Decimal("300"),
        skew_factor=Decimal("0.00005"),
    )

    # --- Simulation loop ---
    print("=" * 70)
    print("  Hyperliquid Outcomes Paper Trading — Simulation")
    print("=" * 70)
    print(f"  Market:          {market}")
    print(f"  Initial Balance: {initial_balance} USDC")
    print(f"  Initial Price:   {initial_price}")
    print(f"  Num Trades:      {num_trades}")
    print(f"  Strategy:        {strategy.name}")
    print(f"  Latency:         {config.get_int('latency_ms')}ms")
    print(f"  Random Seed:     {seed}")
    print("=" * 70)
    print()

    strategy.on_start()

    trade_count = 0
    fill_count = 0

    async for snapshot, trades in ws.stream_with_orderbook(
        num_updates=num_trades // 3,
        trades_per_update=3,
        realtime=False,
    ):
        # Process each trade through OMS (which delegates to engine)
        for trade in trades:
            fills = oms.process_trade(trade)
            fill_count += len(fills)
            strategy.on_trade(trade)
            trade_count += 1

        # Strategy receives the order book update
        strategy.on_orderbook_update(snapshot)

    strategy.on_stop()

    # --- Final Report ---
    mark_price = ws.current_price
    snap = wallet.snapshot(mark_price=mark_price)

    print()
    print("=" * 70)
    print("  SIMULATION RESULTS")
    print("=" * 70)
    print(f"  Trades Processed:    {trade_count}")
    print(f"  Fills Generated:     {fill_count}")
    print(f"  Final Mark Price:    {mark_price}")
    print(f"  ---")
    print(f"  USDC Balance:        {snap.usdc_balance}")
    print(f"  YES Inventory:       {snap.yes_inventory}")
    print(f"  Avg Entry (YES):     {snap.avg_entry_price_yes}")
    print(f"  ---")
    print(f"  Realized PnL:        {snap.realized_pnl}")
    print(f"  Unrealized PnL:      {snap.unrealized_pnl}")
    print(f"  Total PnL:           {snap.total_pnl}")
    print("=" * 70)

    # Engine stats
    eng_stats = engine.stats
    oms_stats = oms.stats
    print(f"\n  Engine: {eng_stats}")
    print(f"  OMS:    {oms_stats}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Hyperliquid Outcomes Paper Trading Simulation"
    )
    parser.add_argument(
        "--trades", type=int, default=2000, help="Number of trades (default: 2000)"
    )
    parser.add_argument(
        "--balance", type=float, default=10000, help="Initial USDC balance"
    )
    parser.add_argument(
        "--price", type=float, default=0.50, help="Initial market price"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed"
    )
    parser.add_argument(
        "--log-level", default="INFO", help="Log level (DEBUG/INFO/WARNING)"
    )

    args = parser.parse_args()

    setup_logging(json_output=False, level=args.log_level)

    asyncio.run(
        run_simulation(
            num_trades=args.trades,
            initial_balance=Decimal(str(args.balance)),
            initial_price=Decimal(str(args.price)),
            seed=args.seed,
        )
    )


if __name__ == "__main__":
    main()
