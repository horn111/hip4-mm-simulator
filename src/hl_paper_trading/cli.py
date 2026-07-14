"""Command-line interface for discovery, recording, and deterministic replay."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from hl_paper_trading.hyperliquid_ws import HyperliquidInfo, HyperliquidWS
from hl_paper_trading.recording import record_stream
from hl_paper_trading.replay import replay_file, write_report


def parse_duration(value: str) -> timedelta:
    units = {"s": 1, "m": 60, "h": 3600}
    if len(value) < 2 or value[-1] not in units:
        raise argparse.ArgumentTypeError("duration must look like 30s, 15m, or 24h")
    try:
        amount = Decimal(value[:-1])
    except Exception as exc:
        raise argparse.ArgumentTypeError("invalid duration") from exc
    if amount <= 0:
        raise argparse.ArgumentTypeError("duration must be positive")
    return timedelta(seconds=float(amount) * units[value[-1]])


async def _markets(args: argparse.Namespace) -> int:
    markets = await HyperliquidInfo(testnet=args.testnet).discover_outcomes()
    if args.json:
        print(
            json.dumps([market.model_dump(mode="json") for market in markets], indent=2)
        )
    else:
        for market in markets:
            tokens = ", ".join(f"{token.label}={token.coin}" for token in market.tokens)
            print(
                f"{market.outcome_id:>5}  {market.quote_token:<6}  "
                f"{market.name}  [{tokens}]"
            )
    return 0


async def _record(args: argparse.Namespace) -> int:
    info = HyperliquidInfo(testnet=args.testnet)
    markets = await info.discover_outcomes()
    selected = next(
        (
            token
            for market in markets
            for token in market.tokens
            if token.coin == args.coin
        ),
        None,
    )
    quote_token = selected.quote_token if selected is not None else args.quote_token
    stream = HyperliquidWS(
        selected,
        coin=None if selected is not None else args.coin,
        quote_token=quote_token,
        testnet=args.testnet,
    )
    metadata = (
        selected.model_dump(mode="json")
        if selected is not None
        else {"coin": args.coin, "quote_token": quote_token}
    )
    try:
        count = await record_stream(
            stream.stream(),
            args.output,
            duration=args.duration,
            metadata=metadata,
            coin=args.coin,
        )
    finally:
        await stream.close()
    print(f"recorded {count} market events to {args.output}")
    return 0


def _replay(args: argparse.Namespace) -> int:
    report = replay_file(
        args.input,
        quote_token=args.quote_token,
        initial_quote=args.initial_quote,
        initial_tokens=args.initial_tokens,
        order_size=args.order_size,
        latency_ms=args.latency_ms,
    )
    write_report(report, args.output)
    print(f"wrote deterministic report to {args.output}")
    if not all(report.invariants.values()):
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hip4-sim")
    parser.add_argument("--version", action="version", version="%(prog)s 0.2.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    markets = subparsers.add_parser("markets", help="list current HIP-4 markets")
    markets.add_argument("--testnet", action="store_true")
    markets.add_argument("--json", action="store_true")

    record = subparsers.add_parser("record", help="record L2 and trades to JSONL")
    record.add_argument("--coin", required=True, help="explicit HIP-4 coin, e.g. #8050")
    record.add_argument("--quote-token", default="USDC")
    record.add_argument("--duration", type=parse_duration, default=parse_duration("1h"))
    record.add_argument("--output", type=Path, required=True)
    record.add_argument("--testnet", action="store_true")

    replay = subparsers.add_parser(
        "replay", help="replay JSONL and validate invariants"
    )
    replay.add_argument("input", type=Path)
    replay.add_argument("--output", type=Path, default=Path("validation-report.md"))
    replay.add_argument("--quote-token", default="USDC")
    replay.add_argument("--initial-quote", type=Decimal, default=Decimal("10000"))
    replay.add_argument("--initial-tokens", type=Decimal, default=Decimal("1000"))
    replay.add_argument("--order-size", type=Decimal, default=Decimal("10"))
    replay.add_argument("--latency-ms", type=int, default=50)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "markets":
        return asyncio.run(_markets(args))
    if args.command == "record":
        return asyncio.run(_record(args))
    if args.command == "replay":
        return _replay(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
