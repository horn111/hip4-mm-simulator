# HIP-4 MM Simulator

[![Tests](https://github.com/horn111/hip4-mm-simulator/actions/workflows/tests.yml/badge.svg)](https://github.com/horn111/hip4-mm-simulator/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Experimental, volume-conserving execution simulation for Hyperliquid HIP-4
market makers.

> Existing HIP-4 SDKs solve market access, while general trading engines solve
> broad backtesting. HIP-4 MM Simulator focuses on transparent, empirically
> validated execution simulation for market makers.

This is an **alpha research tool**, not a production trading system and not a
claim that the included baseline strategy is profitable.

**[Open the 60-second execution demo](https://hip4-mm-simulator.vercel.app/)**
to see an observed L2 queue, aggressor trade, queue consumption, and partial
fill replayed through the Python engine.

## What v0.2 validates

- Dynamic `outcomeMeta` discovery, including custom side labels, multi-outcome
  questions, and per-outcome quote tokens.
- An explicit HIP-4 coin: there is no stale default outcome ID.
- Queue-ahead seeded from the latest L2 snapshot.
- Aggressor-aware matching: buys consume asks and sells consume bids.
- Price-time priority with a shared trade-volume budget.
- Partial fills and `sum(fill_size) <= observed_trade.size`.
- Duplicate exchange trade IDs ignored.
- Spot-safe quote/token balances, reservations, and no naked sells.
- Versioned JSONL recording and deterministic replay reports.

Book-size decreases without a trade are conservatively treated as possible
cancellations. They do not move a virtual order forward in queue.

## Product boundary

| Tool category | Primary job | HIP-4 MM Simulator's relationship |
|---|---|---|
| Hyperliquid/HIP-4 SDKs | Discovery, signing, orders, settlement operations | Complementary: consumes market data but does not replace an SDK |
| NautilusTrader and general engines | Broad live/backtest infrastructure | Narrower: focuses on inspectable HIP-4 execution assumptions |
| Historical data services | Store and serve exchange data | Recorder is self-contained; external data can be converted to JSONL |
| This project | Paper execution, queue assumptions, replay invariants | Not a live execution stack or profitability oracle |

## Install

```bash
pip install "hip4-mm-simulator[live]==0.2.0"
```

For repository development:

```bash
git clone https://github.com/horn111/hip4-mm-simulator.git
cd hip4-mm-simulator
pip install -e ".[live]"
pip install pytest pytest-cov ruff mypy
```

## CLI workflow

Discover current markets rather than copying an old outcome ID:

```bash
hip4-sim markets
hip4-sim markets --testnet --json
```

Record one explicit token:

```bash
hip4-sim record --coin "#8050" --duration 24h --output data/mainnet-8050.jsonl
```

Replay it through the included validation baseline:

```bash
hip4-sim replay data/mainnet-8050.jsonl --output validation-report.md
```

The command exits non-zero when a balance, reservation, or trade-volume
invariant fails. A small deterministic fixture is included:

```bash
hip4-sim replay tests/fixtures/sample_recording.jsonl --output sample-report.md
```

## Python API

```python
from decimal import Decimal

from hl_paper_trading import MatchingEngine, Side, VirtualOMS, VirtualWallet

coin = "#8050"  # obtain from HyperliquidInfo or `hip4-sim markets`
wallet = VirtualWallet(
    quote_balances={"USDC": Decimal("10000")},
    token_balances={coin: Decimal("1000")},
    token_quotes={coin: "USDC"},
    initial_mark_prices={coin: Decimal("0.50")},
)
engine = MatchingEngine(coin=coin, quote_token="USDC")
oms = VirtualOMS(wallet=wallet, engine=engine)

# Feed each book before strategy decisions.
oms.process_book(snapshot)
order_id = oms.submit_order_sync(
    Side.BUY,
    Decimal("0.49"),
    Decimal("10"),
    current_time=snapshot.timestamp,
)

# Observed trades activate latency-expired orders and generate spot-safe fills.
fills = oms.process_trade(trade)
```

An order is rejected with `BOOK_STALE` if no L2 snapshot exists or if the
latest book is more than five seconds older than activation. Its reservation is
released automatically.

## Recording schema

Each JSONL row contains:

```json
{
  "schema_version": "1",
  "event_type": "metadata | book | trade",
  "exchange_timestamp": "ISO-8601",
  "received_timestamp": "ISO-8601",
  "coin": "#8050",
  "payload": {}
}
```

The report records the source SHA-256, exact time window, event/gap counts,
orders, rejections, fills, queue volume, duplicate trades, final NAV, PnL,
invariants, and model limitations.

## Development checks

```bash
ruff check .
mypy src
pytest
python -m build
```

CI runs the same checks on Python 3.11 and 3.12. Test coverage must remain at
or above 85%.

## Explicitly outside v0.2

- Split, merge, negate, and settlement transitions.
- Fee and builder-code accounting.
- Calibration against private order-level ground truth.
- Multi-market portfolio simulation, dashboards, and live order submission.

Those are candidates for v0.3 after the execution assumptions receive external
review. See [the validation protocol](docs/VALIDATION.md) and
[the v0.1 migration guide](MIGRATION.md). Publication status is tracked in the
[v0.2 release checklist](docs/RELEASE_CHECKLIST.md).

## License

MIT. Contributions that challenge a fill assumption with a reproducible trace
are especially welcome.
