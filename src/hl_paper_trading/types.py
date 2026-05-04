"""Domain types for the paper trading framework.

All value objects are immutable Pydantic models with strict validation.
Enumerations use ``StrEnum`` for human-readable serialisation in logs and JSON.

HIP-4 Outcome Market Conventions:
    - Prices are in the [0.0, 1.0] range (probability space).
    - Contracts are denominated in *YES* and *NO* tokens.
    - Settlement is 1.0 USDC per winning contract at expiry.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Side(str, enum.Enum):
    """Order / trade direction."""

    BID = "BID"   # Buy YES (or sell NO – equivalent in outcome markets)
    ASK = "ASK"   # Sell YES (or buy NO)


class OrderStatus(str, enum.Enum):
    """Lifecycle states of a virtual order."""

    PENDING = "PENDING"          # Awaiting simulated latency window
    OPEN = "OPEN"                # Resting in the virtual book
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderType(str, enum.Enum):
    """Supported order types."""

    LIMIT = "LIMIT"
    # Future: MARKET, IOC, FOK


class ContractType(str, enum.Enum):
    """Outcome contract leg."""

    YES = "YES"
    NO = "NO"


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------

class Order(BaseModel):
    """Immutable representation of a virtual limit order.

    Attributes:
        order_id: Unique identifier (UUID4 hex).
        market: Hyperliquid market symbol (e.g., ``"BTC-50K-2025"``).
        side: BID or ASK.
        price: Limit price in [0.0, 1.0].
        size: Quantity of contracts (positive).
        filled_size: Cumulative filled quantity so far.
        status: Current lifecycle status.
        order_type: LIMIT (only supported type for now).
        created_at: Timestamp when the order was created.
        activated_at: Timestamp when the order became OPEN (after latency).
        queue_priority: Accumulated volume at this price level before this
            order; used for queue-position simulation at equal price.
    """

    order_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    market: str
    side: Side
    price: Decimal
    size: Decimal
    filled_size: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.PENDING
    order_type: OrderType = OrderType.LIMIT
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    activated_at: Optional[datetime] = None
    queue_priority: Decimal = Decimal("0")

    model_config = {"frozen": False}  # mutable during lifecycle

    @field_validator("price")
    @classmethod
    def _price_in_range(cls, v: Decimal) -> Decimal:
        if not (Decimal("0") <= v <= Decimal("1")):
            raise ValueError(f"Price must be in [0, 1], got {v}")
        return v

    @field_validator("size")
    @classmethod
    def _size_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError(f"Size must be > 0, got {v}")
        return v

    @property
    def remaining(self) -> Decimal:
        """Unfilled quantity."""
        return self.size - self.filled_size

    @property
    def is_active(self) -> bool:
        """True if the order can still receive fills."""
        return self.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)


class Trade(BaseModel):
    """A single trade observed on the Hyperliquid mainnet feed.

    Attributes:
        market: Market symbol.
        price: Execution price in [0.0, 1.0].
        size: Quantity traded.
        side: Aggressor side (BID = buyer-initiated).
        timestamp: Exchange timestamp (UTC).
    """

    market: str
    price: Decimal
    size: Decimal
    side: Side
    timestamp: datetime

    model_config = {"frozen": True}


class Fill(BaseModel):
    """Record of a simulated fill against a virtual order.

    Attributes:
        order_id: Parent order that was filled.
        fill_price: Price at which the fill occurred.
        fill_size: Quantity filled.
        side: Inherited from the parent order.
        timestamp: Time of fill.
        aggressor_trade_id: Reference to the mainnet trade that triggered this.
    """

    order_id: str
    fill_price: Decimal
    fill_size: Decimal
    side: Side
    timestamp: datetime
    aggressor_trade_id: Optional[str] = None

    model_config = {"frozen": True}


class OrderBookLevel(BaseModel):
    """A single price level in the order book snapshot.

    Attributes:
        price: Price level.
        size: Aggregate size at this level.
        count: Number of orders at this level.
    """

    price: Decimal
    size: Decimal
    count: int = 1

    model_config = {"frozen": True}


class OrderBookSnapshot(BaseModel):
    """Point-in-time order book snapshot from the exchange.

    Attributes:
        market: Market symbol.
        bids: List of bid levels (best first, descending price).
        asks: List of ask levels (best first, ascending price).
        timestamp: Exchange timestamp (UTC).
    """

    market: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    timestamp: datetime

    model_config = {"frozen": True}

    @property
    def best_bid(self) -> Optional[Decimal]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[Decimal]:
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> Optional[Decimal]:
        if self.best_bid is not None and self.best_ask is not None:
            return (self.best_bid + self.best_ask) / 2
        return None

    @property
    def spread(self) -> Optional[Decimal]:
        if self.best_bid is not None and self.best_ask is not None:
            return self.best_ask - self.best_bid
        return None


class PortfolioSnapshot(BaseModel):
    """Snapshot of virtual portfolio state.

    Attributes:
        usdc_balance: Available USDC.
        yes_inventory: Net YES contract inventory (negative = short).
        no_inventory: Net NO contract inventory (negative = short).
        avg_entry_price_yes: Volume-weighted average entry for YES.
        avg_entry_price_no: Volume-weighted average entry for NO.
        realized_pnl: Cumulative realised PnL in USDC.
        unrealized_pnl: Mark-to-market unrealised PnL.
        total_pnl: realized_pnl + unrealized_pnl.
        timestamp: When this snapshot was taken.
    """

    usdc_balance: Decimal
    yes_inventory: Decimal = Decimal("0")
    no_inventory: Decimal = Decimal("0")
    avg_entry_price_yes: Decimal = Decimal("0")
    avg_entry_price_no: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"frozen": True}
