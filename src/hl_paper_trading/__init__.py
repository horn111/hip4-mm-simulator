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
    hyperliquid_ws – Real-time mainnet WebSocket connector.
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
    ContractType,
    Order,
    Trade,
    Fill,
    OrderBookLevel,
    OrderBookSnapshot,
    PortfolioSnapshot,
    # HIP-4 encoding
    OutcomeMarket,
    OUTCOME_ASSET_BASE,
    outcome_encoding,
    outcome_asset_id,
    outcome_coin_name,
    outcome_token_name,
)
from hl_paper_trading.virtual_wallet import VirtualWallet
from hl_paper_trading.virtual_oms import VirtualOMS
from hl_paper_trading.matching_engine import MatchingEngine
from hl_paper_trading.strategy import BaseStrategy
from hl_paper_trading.hyperliquid_ws import HyperliquidWS

__all__ = [
    "__version__",
    # Types
    "Side",
    "OrderStatus",
    "OrderType",
    "ContractType",
    "Order",
    "Trade",
    "Fill",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "PortfolioSnapshot",
    # HIP-4
    "OutcomeMarket",
    "OUTCOME_ASSET_BASE",
    "outcome_encoding",
    "outcome_asset_id",
    "outcome_coin_name",
    "outcome_token_name",
    # Core
    "VirtualWallet",
    "VirtualOMS",
    "MatchingEngine",
    "BaseStrategy",
    "HyperliquidWS",
]
