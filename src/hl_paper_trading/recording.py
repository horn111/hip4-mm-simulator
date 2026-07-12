"""Versioned JSONL recording for HIP-4 metadata and market-data events."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, TextIO

from pydantic import BaseModel

from hl_paper_trading.types import OrderBookSnapshot, Trade

EventType = Literal["metadata", "book", "trade"]


class RecordedEvent(BaseModel):
    schema_version: Literal["1"] = "1"
    event_type: EventType
    exchange_timestamp: datetime
    received_timestamp: datetime
    coin: str
    payload: dict[str, Any]

    model_config = {"frozen": True}

    @classmethod
    def from_market_event(
        cls,
        event: Trade | OrderBookSnapshot,
        *,
        received_timestamp: datetime | None = None,
    ) -> RecordedEvent:
        return cls(
            event_type="trade" if isinstance(event, Trade) else "book",
            exchange_timestamp=event.timestamp,
            received_timestamp=received_timestamp or datetime.now(UTC),
            coin=event.coin,
            payload=event.model_dump(mode="json"),
        )

    def to_market_event(self) -> Trade | OrderBookSnapshot | None:
        if self.event_type == "trade":
            return Trade.model_validate(self.payload)
        if self.event_type == "book":
            return OrderBookSnapshot.model_validate(self.payload)
        return None


class EventRecorder:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._file: TextIO | None = None

    def __enter__(self) -> EventRecorder:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding="utf-8", newline="\n")
        return self

    def __exit__(self, *_: object) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def write(self, event: RecordedEvent) -> None:
        if self._file is None:
            raise RuntimeError("EventRecorder must be used as a context manager")
        self._file.write(event.model_dump_json() + "\n")
        self._file.flush()

    def write_metadata(
        self,
        *,
        coin: str,
        payload: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> None:
        now = timestamp or datetime.now(UTC)
        self.write(
            RecordedEvent(
                event_type="metadata",
                exchange_timestamp=now,
                received_timestamp=now,
                coin=coin,
                payload=payload,
            )
        )


async def record_stream(
    stream: AsyncIterator[Trade | OrderBookSnapshot],
    path: str | Path,
    *,
    duration: timedelta,
    metadata: dict[str, Any] | None = None,
    coin: str,
) -> int:
    """Record a stream for a wall-clock duration and return event count."""
    count = 0
    with EventRecorder(path) as recorder:
        if metadata is not None:
            recorder.write_metadata(coin=coin, payload=metadata)
        try:
            async with asyncio.timeout(duration.total_seconds()):
                async for event in stream:
                    recorder.write(RecordedEvent.from_market_event(event))
                    count += 1
        except TimeoutError:
            pass
    return count


def iter_recording(path: str | Path) -> AsyncIterator[RecordedEvent]:
    async def _iterator() -> AsyncIterator[RecordedEvent]:
        with Path(path).open(encoding="utf-8") as source:
            for line in source:
                if line.strip():
                    yield RecordedEvent.model_validate_json(line)

    return _iterator()
