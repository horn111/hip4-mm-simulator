"""Mock Hyperliquid WebSocket for backtesting and development.

Provides two modes:
    1. **Replay mode**: Feed historical trades from a JSON/CSV file.
    2. **Generator mode**: Produce synthetic trades with configurable
       volatility for rapid strategy prototyping.

This avoids the need for a live mainnet connection during development
and enables deterministic, reproducible backtesting.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

from hl_paper_trading.types import (
    OrderBookLevel,
    OrderBookSnapshot,
    Side,
    Trade,
)
from hl_paper_trading.utils import get_logger

logger = get_logger(__name__)


class MockHyperliquidWS:
    """Simulated Hyperliquid WebSocket feed.

    Generates or replays trades and order book snapshots for paper
    trading without requiring a live connection.

    Args:
        market: Market symbol.
        initial_price: Starting price for the synthetic generator.
        tick_interval_ms: Milliseconds between synthetic ticks.
        volatility: Standard deviation of per-tick price changes.
        seed: Random seed for reproducibility.

    Example::

        ws = MockHyperliquidWS(market="BTC-50K", initial_price=Decimal("0.55"))

        async for trade in ws.stream_trades(num_trades=1000):
            oms.process_trade(trade)
    """

    def __init__(
        self,
        market: str = "OUTCOME-DEMO",
        initial_price: Decimal = Decimal("0.50"),
        tick_interval_ms: int = 100,
        volatility: float = 0.005,
        seed: Optional[int] = None,
    ) -> None:
        self._market = market
        self._current_price = initial_price
        self._tick_interval_ms = tick_interval_ms
        self._volatility = volatility
        self._rng = random.Random(seed)
        self._trade_count = 0

        logger.info(
            "mock_ws.initialized",
            market=market,
            initial_price=str(initial_price),
            volatility=volatility,
            seed=seed,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_price(self) -> Decimal:
        """Current simulated price."""
        return self._current_price

    @property
    def market(self) -> str:
        """Market symbol."""
        return self._market

    # ------------------------------------------------------------------
    # Synthetic trade generation
    # ------------------------------------------------------------------

    def _generate_trade(self, timestamp: datetime) -> Trade:
        """Generate a single synthetic trade.

        Price follows a bounded random walk in [0.01, 0.99] to stay
        within the outcome market range.

        Args:
            timestamp: Trade timestamp.

        Returns:
            A synthetic ``Trade``.
        """
        # Random walk with mean reversion toward 0.5
        mean_reversion = float(Decimal("0.5") - self._current_price) * 0.01
        delta = self._rng.gauss(mean_reversion, self._volatility)
        new_price = float(self._current_price) + delta

        # Clamp to valid outcome market range
        new_price = max(0.01, min(0.99, new_price))
        self._current_price = Decimal(str(round(new_price, 4)))

        # Random size (right-skewed distribution)
        size = Decimal(str(round(self._rng.lognormvariate(2.0, 1.0), 2)))
        size = max(Decimal("1"), min(Decimal("500"), size))

        # Random aggressor side
        side = Side.BID if self._rng.random() > 0.5 else Side.ASK

        self._trade_count += 1

        return Trade(
            market=self._market,
            price=self._current_price,
            size=size,
            side=side,
            timestamp=timestamp,
        )

    def _generate_orderbook(self, timestamp: datetime) -> OrderBookSnapshot:
        """Generate a synthetic order book centered on current price.

        Creates 5 levels on each side with decreasing liquidity.

        Args:
            timestamp: Snapshot timestamp.

        Returns:
            A synthetic ``OrderBookSnapshot``.
        """
        price = float(self._current_price)
        spread = 0.01  # 1 cent spread

        bids: list[OrderBookLevel] = []
        asks: list[OrderBookLevel] = []

        for i in range(5):
            bid_price = max(0.01, price - spread / 2 - i * 0.005)
            ask_price = min(0.99, price + spread / 2 + i * 0.005)

            bid_size = self._rng.uniform(10, 200) * (1 / (i + 1))
            ask_size = self._rng.uniform(10, 200) * (1 / (i + 1))

            bids.append(
                OrderBookLevel(
                    price=Decimal(str(round(bid_price, 4))),
                    size=Decimal(str(round(bid_size, 2))),
                    count=self._rng.randint(1, 5),
                )
            )
            asks.append(
                OrderBookLevel(
                    price=Decimal(str(round(ask_price, 4))),
                    size=Decimal(str(round(ask_size, 2))),
                    count=self._rng.randint(1, 5),
                )
            )

        return OrderBookSnapshot(
            market=self._market,
            bids=bids,
            asks=asks,
            timestamp=timestamp,
        )

    # ------------------------------------------------------------------
    # Streaming interfaces
    # ------------------------------------------------------------------

    async def stream_trades(
        self,
        num_trades: int = 1000,
        realtime: bool = False,
    ) -> AsyncIterator[Trade]:
        """Stream synthetic trades.

        Args:
            num_trades: Number of trades to generate.
            realtime: If True, sleep between ticks (for live simulation).
                      If False, generate as fast as possible (backtesting).

        Yields:
            Synthetic ``Trade`` objects.
        """
        start_time = datetime.now(timezone.utc)

        for i in range(num_trades):
            timestamp = start_time + timedelta(
                milliseconds=i * self._tick_interval_ms
            )
            trade = self._generate_trade(timestamp)
            yield trade

            if realtime:
                await asyncio.sleep(self._tick_interval_ms / 1000.0)

        logger.info(
            "mock_ws.stream_complete",
            trades_generated=num_trades,
        )

    async def stream_with_orderbook(
        self,
        num_updates: int = 1000,
        trades_per_update: int = 3,
        realtime: bool = False,
    ) -> AsyncIterator[tuple[OrderBookSnapshot, list[Trade]]]:
        """Stream paired order book snapshots and trades.

        Each iteration yields an order book update followed by the
        trades that occurred since the last update.

        Args:
            num_updates: Number of order book update cycles.
            trades_per_update: Trades generated per cycle.
            realtime: If True, sleep between cycles.

        Yields:
            Tuple of (``OrderBookSnapshot``, list of ``Trade``).
        """
        start_time = datetime.now(timezone.utc)
        tick = 0

        for i in range(num_updates):
            trades: list[Trade] = []

            for _ in range(trades_per_update):
                timestamp = start_time + timedelta(
                    milliseconds=tick * self._tick_interval_ms
                )
                trades.append(self._generate_trade(timestamp))
                tick += 1

            # Order book snapshot after trades
            ob_time = start_time + timedelta(
                milliseconds=tick * self._tick_interval_ms
            )
            snapshot = self._generate_orderbook(ob_time)

            yield snapshot, trades

            if realtime:
                await asyncio.sleep(
                    (self._tick_interval_ms * trades_per_update) / 1000.0
                )

        logger.info(
            "mock_ws.stream_with_orderbook_complete",
            updates=num_updates,
            total_trades=num_updates * trades_per_update,
        )

    # ------------------------------------------------------------------
    # Replay from file
    # ------------------------------------------------------------------

    async def replay_from_file(
        self,
        filepath: Path | str,
        realtime: bool = False,
    ) -> AsyncIterator[Trade]:
        """Replay trades from a JSON lines file.

        Expected format (one JSON object per line)::

            {"price": "0.55", "size": "10", "side": "BID", "timestamp": "2025-01-01T00:00:00Z"}

        Args:
            filepath: Path to the JSONL file.
            realtime: If True, respect inter-trade timing.

        Yields:
            ``Trade`` objects from the file.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Replay file not found: {filepath}")

        prev_timestamp: Optional[datetime] = None

        with open(filepath) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    trade = Trade(
                        market=data.get("market", self._market),
                        price=Decimal(data["price"]),
                        size=Decimal(data["size"]),
                        side=Side(data["side"]),
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                    )
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.warning(
                        "mock_ws.replay_parse_error",
                        line=line_num,
                        error=str(e),
                    )
                    continue

                if realtime and prev_timestamp is not None:
                    delay = (
                        trade.timestamp - prev_timestamp
                    ).total_seconds()
                    if delay > 0:
                        await asyncio.sleep(min(delay, 1.0))

                prev_timestamp = trade.timestamp
                self._trade_count += 1
                yield trade

        logger.info(
            "mock_ws.replay_complete",
            filepath=str(filepath),
            trades_replayed=self._trade_count,
        )
