"""Experimental HIP-4 execution simulation toolkit."""

from hl_paper_trading.hyperliquid_ws import HyperliquidInfo, HyperliquidWS
from hl_paper_trading.matching_engine import BookUnavailableError, MatchingEngine
from hl_paper_trading.recording import EventRecorder, RecordedEvent, record_stream
from hl_paper_trading.replay import ReplayReport, replay_file, write_report
from hl_paper_trading.strategy import BaseStrategy
from hl_paper_trading.types import (
    OUTCOME_ASSET_BASE,
    Fill,
    Order,
    OrderBookLevel,
    OrderBookSnapshot,
    OrderStatus,
    OrderType,
    OutcomeMarket,
    OutcomeQuestion,
    OutcomeToken,
    PortfolioSnapshot,
    RejectionReason,
    Side,
    Trade,
    outcome_asset_id,
    outcome_coin_name,
    outcome_encoding,
    outcome_token_name,
)
from hl_paper_trading.virtual_oms import VirtualOMS
from hl_paper_trading.virtual_wallet import (
    DuplicateFillError,
    InsufficientBalanceError,
    VirtualWallet,
)

__version__ = "0.2.0"

__all__ = [
    "OUTCOME_ASSET_BASE",
    "BaseStrategy",
    "BookUnavailableError",
    "DuplicateFillError",
    "EventRecorder",
    "Fill",
    "HyperliquidInfo",
    "HyperliquidWS",
    "InsufficientBalanceError",
    "MatchingEngine",
    "Order",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "OrderStatus",
    "OrderType",
    "OutcomeMarket",
    "OutcomeQuestion",
    "OutcomeToken",
    "PortfolioSnapshot",
    "RecordedEvent",
    "RejectionReason",
    "ReplayReport",
    "Side",
    "Trade",
    "VirtualOMS",
    "VirtualWallet",
    "outcome_asset_id",
    "outcome_coin_name",
    "outcome_encoding",
    "outcome_token_name",
    "record_stream",
    "replay_file",
    "write_report",
]
