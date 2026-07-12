"""Domain models for HIP-4 market-data and execution simulation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

OUTCOME_ASSET_BASE = 100_000_000


class Side(StrEnum):
    """Order side or aggressor direction."""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderType(StrEnum):
    LIMIT = "LIMIT"


class RejectionReason(StrEnum):
    BOOK_STALE = "BOOK_STALE"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    MAX_ORDER_SIZE = "MAX_ORDER_SIZE"
    MAX_OPEN_ORDERS = "MAX_OPEN_ORDERS"


def outcome_encoding(outcome_id: int, side_index: int) -> int:
    """Return the HIP-4 encoding ``10 * outcome + side``."""
    if side_index < 0:
        raise ValueError("side_index must be non-negative")
    return 10 * outcome_id + side_index


def outcome_asset_id(outcome_id: int, side_index: int) -> int:
    return OUTCOME_ASSET_BASE + outcome_encoding(outcome_id, side_index)


def outcome_coin_name(outcome_id: int, side_index: int) -> str:
    return f"#{outcome_encoding(outcome_id, side_index)}"


def outcome_token_name(outcome_id: int, side_index: int) -> str:
    return f"+{outcome_encoding(outcome_id, side_index)}"


class OutcomeToken(BaseModel):
    """One tradeable side-token belonging to a HIP-4 outcome."""

    outcome_id: int
    side_index: int
    label: str
    quote_token: str
    coin: str = ""
    token: str = ""
    asset_id: int = 0

    model_config = {"frozen": True, "extra": "ignore"}

    def model_post_init(self, __context: object) -> None:
        object.__setattr__(
            self,
            "coin",
            self.coin or outcome_coin_name(self.outcome_id, self.side_index),
        )
        object.__setattr__(
            self,
            "token",
            self.token or outcome_token_name(self.outcome_id, self.side_index),
        )
        object.__setattr__(
            self,
            "asset_id",
            self.asset_id or outcome_asset_id(self.outcome_id, self.side_index),
        )


class OutcomeMarket(BaseModel):
    """An outcome and its arbitrary set of tradeable side-tokens."""

    outcome_id: int
    name: str
    description: str = ""
    quote_token: str
    tokens: tuple[OutcomeToken, ...]
    question_ids: tuple[int, ...] = ()
    raw_metadata: dict[str, Any] = Field(default_factory=dict, exclude=True)

    model_config = {"frozen": True, "extra": "ignore"}


class OutcomeQuestion(BaseModel):
    """A multi-outcome HIP-4 question from ``outcomeMeta``."""

    question_id: int
    name: str
    description: str = ""
    fallback_outcome: int | None = None
    named_outcomes: tuple[int, ...] = ()
    settled_named_outcomes: tuple[int, ...] = ()

    model_config = {"frozen": True, "extra": "ignore"}


class Order(BaseModel):
    order_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    coin: str
    quote_token: str
    side: Side
    price: Decimal
    size: Decimal
    filled_size: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.PENDING
    order_type: OrderType = OrderType.LIMIT
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    activated_at: datetime | None = None
    queue_ahead: Decimal = Decimal("0")
    rejection_reason: RejectionReason | None = None

    @field_validator("price")
    @classmethod
    def _price_in_range(cls, value: Decimal) -> Decimal:
        if not Decimal("0") <= value <= Decimal("1"):
            raise ValueError("price must be in [0, 1]")
        return value

    @field_validator("size")
    @classmethod
    def _size_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("size must be positive")
        return value

    @property
    def remaining(self) -> Decimal:
        return self.size - self.filled_size

    @property
    def is_active(self) -> bool:
        return self.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}


class Trade(BaseModel):
    coin: str
    price: Decimal
    size: Decimal
    side: Side
    timestamp: datetime
    trade_id: str | None = None

    model_config = {"frozen": True}


class Fill(BaseModel):
    fill_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    order_id: str
    coin: str
    quote_token: str
    fill_price: Decimal
    order_price: Decimal
    fill_size: Decimal
    side: Side
    timestamp: datetime
    aggressor_trade_id: str | None = None

    model_config = {"frozen": True}


class OrderBookLevel(BaseModel):
    price: Decimal
    size: Decimal
    count: int = 1

    model_config = {"frozen": True}


class OrderBookSnapshot(BaseModel):
    coin: str
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    timestamp: datetime

    model_config = {"frozen": True}

    @property
    def best_bid(self) -> Decimal | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Decimal | None:
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> Decimal | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread(self) -> Decimal | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    def size_at(self, side: Side, price: Decimal) -> Decimal:
        levels = self.bids if side is Side.BUY else self.asks
        return next(
            (level.size for level in levels if level.price == price), Decimal("0")
        )


class PortfolioSnapshot(BaseModel):
    quote_token: str
    available_balances: dict[str, Decimal]
    reserved_balances: dict[str, Decimal]
    nav: Decimal
    initial_nav: Decimal
    pnl: Decimal
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"frozen": True}
