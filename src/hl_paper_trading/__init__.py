"""Hyperliquid Outcomes Paper Trading Framework.

A production-ready paper trading engine for Hyperliquid HIP-4 outcome markets
(0.0–1.0 binary contracts). Enables market-makers to backtest and forward-test
strategies on real mainnet WebSocket data without risking capital.

Modules:
    types       – Domain value objects and enumerations.
    virtual_wallet – Portfolio accounting (USDC, YES/NO inventory, PnL).
    virtual_oms    – Order Management System with latency simulation.
    matching_engine – Pessimistic fill simulator against live trades.
    strategy       – Base class for Bring-Your-Own-Logic strategies.
    utils          – Shared helpers (logging bootstrap, config loading).
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("hl-paper-trading")
except PackageNotFoundError:
    __version__ = "0.1.0"

from hl_paper_trading.types import (
    Side,
    OrderStatus,
    OrderType,
    Order,
    Trade,
    Fill,
    OrderBookLevel,
    OrderBookSnapshot,
    PortfolioSnapshot,
)
from hl_paper_trading.virtual_wallet import VirtualWallet
from hl_paper_trading.virtual_oms import VirtualOMS
from hl_paper_trading.matching_engine import MatchingEngine
from hl_paper_trading.strategy import BaseStrategy

__all__ = [
    "__version__",
    # Types
    "Side",
    "OrderStatus",
    "OrderType",
    "Order",
    "Trade",
    "Fill",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "PortfolioSnapshot",
    # Core
    "VirtualWallet",
    "VirtualOMS",
    "MatchingEngine",
    "BaseStrategy",
]
