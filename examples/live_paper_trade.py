"""Run the spot-safe baseline against one explicit live HIP-4 coin."""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from basic_strategy import InventorySkewMM

from hl_paper_trading import HyperliquidWS, MatchingEngine, OrderBookSnapshot, Trade
from hl_paper_trading.utils import Config
from hl_paper_trading.virtual_oms import VirtualOMS
from hl_paper_trading.virtual_wallet import VirtualWallet


async def run_live(
    coin: str,
    quote_token: str,
    balance: Decimal,
    tokens: Decimal,
    testnet: bool,
) -> None:
    wallet = VirtualWallet(
        quote_balances={quote_token: balance},
        token_balances={coin: tokens},
        token_quotes={coin: quote_token},
        initial_mark_prices={coin: Decimal("0.5")},
    )
    engine = MatchingEngine(coin, quote_token)
    oms = VirtualOMS(wallet, engine, Config(latency_ms="50"))
    strategy = InventorySkewMM(oms, wallet, target_inventory=tokens)
    source = HyperliquidWS(coin=coin, quote_token=quote_token, testnet=testnet)
    last_mark = Decimal("0.5")
    try:
        async for event in source.stream():
            if isinstance(event, OrderBookSnapshot):
                oms.process_book(event)
                if event.mid_price is not None:
                    last_mark = event.mid_price
                strategy.on_orderbook_update(event)
            elif isinstance(event, Trade):
                oms.process_trade(event)
                strategy.on_trade(event)
    finally:
        await source.close()
        strategy.on_stop()
        snapshot = wallet.snapshot({coin: last_mark}, quote_token=quote_token)
        print(f"fills={len(wallet.fills)} nav={snapshot.nav} pnl={snapshot.pnl}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--coin", required=True, help="explicit coin from hip4-sim markets"
    )
    parser.add_argument("--quote-token", default="USDC")
    parser.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    parser.add_argument("--tokens", type=Decimal, default=Decimal("1000"))
    parser.add_argument("--testnet", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        run_live(args.coin, args.quote_token, args.balance, args.tokens, args.testnet)
    )


if __name__ == "__main__":
    main()
