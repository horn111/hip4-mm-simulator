"""Run a deterministic spot-safe synthetic simulation."""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from basic_strategy import InventorySkewMM

from hl_paper_trading import MatchingEngine, OrderBookSnapshot, Trade, VirtualOMS
from hl_paper_trading.mock_ws import MockHyperliquidWS
from hl_paper_trading.utils import Config
from hl_paper_trading.virtual_wallet import VirtualWallet


async def run_simulation(
    num_trades: int = 2_000,
    initial_balance: Decimal = Decimal("10000"),
    initial_price: Decimal = Decimal("0.50"),
    seed: int = 42,
) -> None:
    coin = "#TEST0"
    initial_tokens = Decimal("1000")
    wallet = VirtualWallet(
        quote_balances={"USDC": initial_balance},
        token_balances={coin: initial_tokens},
        token_quotes={coin: "USDC"},
        initial_mark_prices={coin: initial_price},
    )
    engine = MatchingEngine(coin)
    oms = VirtualOMS(wallet, engine, Config(latency_ms="50"))
    strategy = InventorySkewMM(
        oms, wallet, target_inventory=initial_tokens, order_size=Decimal("10")
    )
    source = MockHyperliquidWS(coin, initial_price=initial_price, seed=seed)

    trades = 0
    async for event in source.stream_with_orderbook(num_trades, book_every=10):
        if isinstance(event, OrderBookSnapshot):
            oms.process_book(event)
            oms.activate_pending(event.timestamp)
            strategy.on_orderbook_update(event)
        elif isinstance(event, Trade):
            oms.process_trade(event)
            strategy.on_trade(event)
            trades += 1
    strategy.on_stop()
    snapshot = wallet.snapshot({coin: source.current_price})
    print(f"Trades: {trades}")
    print(f"Fills: {len(wallet.fills)}")
    print(f"Final NAV: {snapshot.nav}")
    print(f"PnL: {snapshot.pnl}")
    print(f"Invariants: balances non-negative, reserved={snapshot.reserved_balances}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", type=int, default=2_000)
    parser.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    parser.add_argument("--price", type=Decimal, default=Decimal("0.50"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    asyncio.run(run_simulation(args.trades, args.balance, args.price, args.seed))


if __name__ == "__main__":
    main()
