# Hyperliquid Outcomes Paper Trading Framework

![Tests](https://github.com/horn111/hip4-mm-simulator/actions/workflows/tests.yml/badge.svg)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

<p align="center">
  <strong>🏗️ Production-ready paper trading engine for HIP-4 outcome markets (0.0–1.0)</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#usage">Usage</a> •
  <a href="#roadmap">Roadmap</a> •
  <a href="#contributing">Contributing</a>
</p>

---

## 🎯 Problem

Hyperliquid's new **HIP-4 outcome markets** (binary contracts priced 0.0–1.0) create opportunities for market-makers, but **there is no safe way to test MM strategies** without risking real capital. Existing paper trading tools are built for perpetual futures and don't handle the unique mechanics of outcome markets.

## 💡 Solution

A **framework-level** paper trading engine that lets market-makers:

- **Test strategies on real mainnet WebSocket data** without placing real orders
- **Simulate pessimistic execution** (how prop trading firms actually backtest)
- **Track portfolio P&L** with proper VWAP, inventory accounting, and outcome market settlement logic
- **Bring their own logic** via a clean strategy interface

## 🤔 Why Not Just Use Hyperliquid Testnet?

While the testnet is useful for basic integration checks, it is **not suitable** for serious market-making strategy development on HIP-4 markets. Here's why professional quant teams choose a realistic paper trading engine instead:

| Aspect                      | Hyperliquid Testnet                          | This Framework (Mainnet Paper Trading)              |
|-----------------------------|----------------------------------------------|-----------------------------------------------------|
| **Data quality**            | Artificial, low-volume order flow            | **Real mainnet WebSocket trades**                   |
| **Execution realism**       | Optimistic / "as-if" fills                   | **Strict pessimistic model** (real queue position)  |
| **Latency & queue**         | No realistic latency or priority simulation  | 50ms latency + cumulative volume queue              |
| **Adverse selection**       | Almost non-existent                          | Fully simulated (the #1 MM risk)                    |
| **PnL accuracy**            | Not representative                           | Precise realized + unrealized PnL with VWAP         |
| **Speed of iteration**      | Slow (need to wait for real fills)           | Instant replay + synthetic data                     |
| **Purpose**                 | Smoke-testing connectivity                   | **Production-like backtesting & validation**        |

Testnet data differs significantly from mainnet, especially on newly launched primitives like HIP-4.
**Real market makers** (prop firms, HFT teams) always validate strategies on **production feed** before deploying capital. This framework gives you exactly that — without risking a single dollar.

## ✨ Features

| Component | Description |
|---|---|
| **VirtualWallet** | USDC balance + YES/NO inventory tracking, VWAP avg entry, realized + unrealized PnL |
| **VirtualOMS** | Limit order lifecycle with configurable latency simulation (default: 50ms), pre-trade risk checks |
| **MatchingEngine** | **Pessimistic fill model** — the core innovation (see below) |
| **BaseStrategy** | Event-driven BYOL interface (`on_orderbook_update`, `on_trade`, `on_fill`) |
| **MockHyperliquidWS** | Synthetic data generator + historical replay for offline development |

### 🔬 Pessimistic Execution Model

The matching engine uses a **three-rule fill model** standard at prop trading firms:

| Condition | Rule | Rationale |
|---|---|---|
| `trade_price < bid_price` | ✅ **Fill** | Market traded through your level |
| `trade_price > ask_price` | ✅ **Fill** | Market traded through your level |
| `trade_price == order_price` | ⏳ **Queue** | Fill only after cumulative volume at this price exceeds your queue position + order size |
| `trade_price` worse than order | ❌ **No fill** | You wouldn't have been filled |

This prevents the #1 backtesting pitfall: **overstating fill rates on passive limit orders**.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Your Strategy                      │
│         (extends BaseStrategy — BYOL)                │
├──────────────┬──────────────┬────────────────────────┤
│ on_orderbook │   on_trade   │       on_fill          │
├──────────────┴──────────────┴────────────────────────┤
│                  VirtualOMS                          │
│        (order lifecycle + latency sim)               │
├──────────────────────────────────────────────────────┤
│               MatchingEngine                         │
│     (pessimistic fill against real trades)           │
├──────────────────────────────────────────────────────┤
│               VirtualWallet                          │
│    (USDC + YES/NO inventory + PnL tracking)         │
├──────────────────────────────────────────────────────┤
│         Hyperliquid Mainnet WebSocket                │
│     (or MockHyperliquidWS for development)           │
└──────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/) (recommended) or pip

### Installation

```bash
# Clone the repository
git clone https://github.com/horn111/hip4-mm-simulator.git
cd hip4-mm-simulator

# Install with Poetry
poetry install

# Or with pip
pip install -e ".[dev]"
```

### Run the Demo

```bash
# Run a simulation with synthetic data
python main.py

# With custom parameters
python main.py --trades 5000 --balance 25000 --log-level DEBUG

# Run from examples
python examples/run_simulation.py --trades 3000 --seed 123
```

### Demo Output

```
======================================================================
  Hyperliquid Outcomes Paper Trading — Simulation
======================================================================
  Market:          OUTCOME-DEMO
  Initial Balance: 10000 USDC
  Initial Price:   0.5
  Num Trades:      2000
  Strategy:        InventorySkewMM
  Latency:         50ms
  Random Seed:     42
======================================================================

======================================================================
  SIMULATION RESULTS
======================================================================
  Trades Processed:    1998
  Fills Generated:     47
  Final Mark Price:    0.5271
  ---
  USDC Balance:        9987.4200
  YES Inventory:       23
  Avg Entry (YES):     0.4892
  ---
  Realized PnL:        1.2350
  Unrealized PnL:      0.8723
  Total PnL:           2.1073
======================================================================

  Engine: {'total_trades_processed': 1998, 'total_fills_generated': 47}
  OMS:    {'total_submitted': 1332, 'total_rejected': 0, 'total_cancelled': 1286}
```

### Run Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=hl_paper_trading --cov-report=term-missing

# Specific test file
pytest tests/test_matching.py -v
```

## 📖 Usage

### Writing Your Own Strategy

```python
from decimal import Decimal
from hl_paper_trading import BaseStrategy, Side, OrderBookSnapshot, Trade, Fill

class MyStrategy(BaseStrategy):
    """Your custom market-making strategy."""

    def on_orderbook_update(self, snapshot: OrderBookSnapshot) -> None:
        mid = self.get_mid_price(snapshot)
        if mid is None:
            return

        # Cancel stale orders
        self.cancel_all_orders()

        position = self.get_position()

        # Simple symmetric quotes with inventory skew
        skew = position * Decimal("0.0001")
        bid = mid - Decimal("0.02") - skew
        ask = mid + Decimal("0.02") - skew

        self.oms.submit_order_sync(Side.BID, bid, Decimal("50"))
        self.oms.submit_order_sync(Side.ASK, ask, Decimal("50"))

    def on_fill(self, fill: Fill) -> None:
        snap = self.wallet.snapshot(mark_price=fill.fill_price)
        self.log.info("filled", pnl=str(snap.total_pnl))
```

### Replaying Historical Data

```python
from hl_paper_trading.mock_ws import MockHyperliquidWS

ws = MockHyperliquidWS(market="BTC-50K-2025")

# Replay from JSONL file
async for trade in ws.replay_from_file("data/historical_trades.jsonl"):
    fills = oms.process_trade(trade)
    strategy.on_trade(trade)
```

### Configuration

Configuration follows a hierarchical resolution:

1. **Constructor kwargs** (highest priority)
2. **Environment variables** (`HL_PAPER_<KEY>`)
3. **Built-in defaults**

```bash
# Environment variable configuration
export HL_PAPER_LATENCY_MS=100
export HL_PAPER_INITIAL_BALANCE=50000
export HL_PAPER_LOG_LEVEL=DEBUG
```

## 📁 Project Structure

```
hyperliquid-outcomes-paper-trading/
├── README.md                          # This file
├── pyproject.toml                     # Poetry project config
├── main.py                            # CLI entry point
├── src/
│   └── hl_paper_trading/
│       ├── __init__.py                # Public API exports
│       ├── types.py                   # Domain types (Pydantic models)
│       ├── virtual_wallet.py          # Portfolio accounting
│       ├── virtual_oms.py             # Order Management System
│       ├── matching_engine.py         # Pessimistic fill engine ⭐
│       ├── strategy.py                # BaseStrategy (BYOL interface)
│       ├── mock_ws.py                 # Mock WebSocket (synthetic + replay)
│       └── utils.py                   # Logging, config, helpers
├── examples/
│   ├── basic_strategy.py              # InventorySkewMM example
│   └── run_simulation.py              # Full simulation runner
├── tests/
│   ├── test_matching.py               # Matching engine tests (23 cases)
│   ├── test_wallet.py                 # Wallet accounting tests
│   └── test_oms.py                    # OMS lifecycle tests
└── .gitignore
```

## 🗺️ Roadmap

### Phase 1 — Core Framework ✅ (Current)
- [x] Pessimistic matching engine with queue simulation
- [x] Virtual wallet with VWAP and PnL tracking
- [x] Order management with latency simulation
- [x] BYOL strategy interface
- [x] Mock WebSocket (synthetic + file replay)
- [x] Example strategy (inventory skew MM)
- [x] Comprehensive test suite

### Phase 2 — Live Feed Integration (Next)
- [ ] Real-time Hyperliquid mainnet WebSocket connector
- [ ] L2 order book reconstruction
- [ ] Multi-market support
- [ ] Performance metrics dashboard (Streamlit/Grafana)
- [ ] Trade history export (CSV / Parquet)

### Phase 3 — Advanced Features
- [ ] Monte Carlo simulation mode
- [ ] Slippage and fee modeling
- [ ] Multi-strategy portfolio simulation
- [ ] Outcome market settlement simulation
- [ ] REST API for remote strategy control

### Phase 4 — Production Deployment
- [ ] Docker containerization
- [ ] Kubernetes deployment manifests
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Real-time monitoring and alerting
- [ ] Strategy parameter optimization framework

## 🔧 Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| Async Runtime | asyncio |
| Data Models | Pydantic v2 |
| Logging | structlog (JSON + console) |
| Testing | pytest + pytest-asyncio |
| Linting | ruff |
| Type Checking | mypy (strict) |
| Package Manager | Poetry |

## 🤝 Contributing

We welcome contributions! Here's how to get started:

1. **Fork** the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Write tests for your changes
4. Ensure all tests pass: `pytest`
5. Lint your code: `ruff check . && mypy src/`
6. Submit a **Pull Request**

### Contribution Ideas
- Additional strategy examples (volatility-based spread, TWAP, etc.)
- Performance benchmarks
- Visualization tools
- Documentation improvements
- Integration with Hyperliquid SDK

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

## 🔗 Links

- [Hyperliquid Documentation](https://hyperliquid.gitbook.io/)
- [HIP-4 Specification](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-4-outcome-markets)
- [Hyperliquid Builders Program Application](https://docs.google.com/forms/d/e/1FAIpQLScJ8ZueDUSQtQaiQ1-8-sgEiAoaAt-iqKAvN1o2kX5sbwlGvA/viewform)

### 🏆 Grant Application

This project was submitted to the Hyperliquid Builders Program (May 2026).
Form: [Hyperliquid Builders Program](https://docs.google.com/forms/d/e/1FAIpQLScJ8ZueDUSQtQaiQ1-8-sgEiAoaAt-iqKAvN1o2kX5sbwlGvA/viewform)

---

<p align="center">
  Built for the <strong>Hyperliquid Builders Program</strong> 🚀
</p>
