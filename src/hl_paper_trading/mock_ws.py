"""Deterministic synthetic market-data source for examples and tests."""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from hl_paper_trading.recording import RecordedEvent
from hl_paper_trading.types import (
    OrderBookLevel,
    OrderBookSnapshot,
    Side,
    Trade,
)


class MockHyperliquidWS:
    def __init__(
        self,
        coin: str = "#TEST0",
        *,
        initial_price: Decimal = Decimal("0.5"),
        spread: Decimal = Decimal("0.02"),
        volatility: Decimal = Decimal("0.01"),
        seed: int = 42,
    ) -> None:
        self.coin = coin
        self._price = initial_price
        self._spread = spread
        self._volatility = volatility
        self._rng = random.Random(seed)  # noqa: S311 - deterministic simulation
        self._count = 0

    @property
    def current_price(self) -> Decimal:
        return self._price

    def _next_trade(self, timestamp: datetime) -> Trade:
        change = Decimal(str(self._rng.gauss(0, float(self._volatility))))
        self._price = max(Decimal("0.01"), min(Decimal("0.99"), self._price + change))
        self._count += 1
        return Trade(
            coin=self.coin,
            price=self._price.quantize(Decimal("0.0001")),
            size=Decimal(str(round(self._rng.uniform(1, 50), 4))),
            side=Side.BUY if self._rng.random() >= 0.5 else Side.SELL,
            timestamp=timestamp,
            trade_id=f"synthetic-{self._count}",
        )

    def _book(self, timestamp: datetime) -> OrderBookSnapshot:
        half = self._spread / 2
        bid = max(Decimal("0"), self._price - half).quantize(Decimal("0.0001"))
        ask = min(Decimal("1"), self._price + half).quantize(Decimal("0.0001"))
        return OrderBookSnapshot(
            coin=self.coin,
            bids=(OrderBookLevel(price=bid, size=Decimal("25")),),
            asks=(OrderBookLevel(price=ask, size=Decimal("25")),),
            timestamp=timestamp,
        )

    async def stream_trades(
        self, num_trades: int = 1_000, *, delay_ms: int = 0
    ) -> AsyncIterator[Trade]:
        timestamp = datetime(2026, 1, 1, tzinfo=UTC)
        for index in range(num_trades):
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            yield self._next_trade(timestamp + timedelta(milliseconds=100 * index))

    async def stream_with_orderbook(
        self,
        num_trades: int = 1_000,
        *,
        book_every: int = 10,
        delay_ms: int = 0,
    ) -> AsyncIterator[Trade | OrderBookSnapshot]:
        timestamp = datetime(2026, 1, 1, tzinfo=UTC)
        for index in range(num_trades):
            now = timestamp + timedelta(milliseconds=100 * index)
            if index % book_every == 0:
                yield self._book(now)
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            yield self._next_trade(now)

    async def replay_from_file(
        self, path: str | Path
    ) -> AsyncIterator[Trade | OrderBookSnapshot]:
        with Path(path).open(encoding="utf-8") as source:
            for line in source:
                if not line.strip():
                    continue
                event = RecordedEvent.model_validate_json(line).to_market_event()
                if event is not None:
                    yield event
