"""HIP-4 metadata discovery and read-only WebSocket market data."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from hl_paper_trading.types import (
    OrderBookLevel,
    OrderBookSnapshot,
    OutcomeMarket,
    OutcomeQuestion,
    OutcomeToken,
    Side,
    Trade,
)

MAINNET_API = "https://api.hyperliquid.xyz"
TESTNET_API = "https://api.hyperliquid-testnet.xyz"
MAINNET_WS = "wss://api.hyperliquid.xyz/ws"
TESTNET_WS = "wss://api.hyperliquid-testnet.xyz/ws"


class HyperliquidInfo:
    """Read and parse the official ``outcomeMeta`` response."""

    def __init__(self, *, testnet: bool = False) -> None:
        self.base_url = TESTNET_API if testnet else MAINNET_API

    async def discover_outcomes(self) -> list[OutcomeMarket]:
        try:
            import aiohttp
        except ImportError as exc:  # pragma: no cover - exercised in smoke usage
            raise ImportError("install hip4-mm-simulator[live] for discovery") from exc
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                f"{self.base_url}/info", json={"type": "outcomeMeta"}
            ) as response,
        ):
            response.raise_for_status()
            payload = await response.json()
        markets, _ = self.parse_outcome_meta(payload)
        return markets

    @staticmethod
    def parse_outcome_meta(
        payload: dict[str, Any],
    ) -> tuple[list[OutcomeMarket], list[OutcomeQuestion]]:
        raw_questions = payload.get("questions", [])
        questions = [
            OutcomeQuestion(
                question_id=int(item["question"]),
                name=str(item.get("name", "")),
                description=str(item.get("description", "")),
                fallback_outcome=(
                    int(item["fallbackOutcome"])
                    if item.get("fallbackOutcome") is not None
                    else None
                ),
                named_outcomes=tuple(
                    int(value) for value in item.get("namedOutcomes", [])
                ),
                settled_named_outcomes=tuple(
                    int(value) for value in item.get("settledNamedOutcomes", [])
                ),
            )
            for item in raw_questions
            if isinstance(item, dict) and item.get("question") is not None
        ]

        market_questions: dict[int, list[int]] = {}
        for question in questions:
            outcome_ids = list(question.named_outcomes) + list(
                question.settled_named_outcomes
            )
            if question.fallback_outcome is not None:
                outcome_ids.append(question.fallback_outcome)
            for outcome_id in outcome_ids:
                market_questions.setdefault(outcome_id, []).append(question.question_id)

        markets: list[OutcomeMarket] = []
        for item in payload.get("outcomes", []):
            if not isinstance(item, dict) or item.get("outcome") is None:
                continue
            outcome_id = int(item["outcome"])
            quote_token = str(item.get("quoteToken", "USDC"))
            side_specs = item.get("sideSpecs", [])
            tokens = tuple(
                OutcomeToken(
                    outcome_id=outcome_id,
                    side_index=index,
                    label=str(spec.get("name", f"Side {index}")),
                    quote_token=quote_token,
                )
                for index, spec in enumerate(side_specs)
                if isinstance(spec, dict)
            )
            markets.append(
                OutcomeMarket(
                    outcome_id=outcome_id,
                    name=str(item.get("name", f"Outcome {outcome_id}")),
                    description=str(item.get("description", "")),
                    quote_token=quote_token,
                    tokens=tokens,
                    question_ids=tuple(market_questions.get(outcome_id, [])),
                    raw_metadata=dict(item),
                )
            )
        return markets, questions


class HyperliquidWS:
    """Stream trades and L2 snapshots for one explicit HIP-4 token."""

    def __init__(
        self,
        token: OutcomeToken | None = None,
        *,
        coin: str | None = None,
        quote_token: str = "USDC",
        testnet: bool = False,
        subscribe_trades: bool = True,
        subscribe_l2: bool = True,
    ) -> None:
        if token is None and coin is None:
            raise ValueError(
                "token or coin is required; there is no default HIP-4 market"
            )
        if token is not None and coin is not None and token.coin != coin:
            raise ValueError("token.coin and coin disagree")
        self.token = token
        self.coin = token.coin if token is not None else str(coin)
        self.quote_token = token.quote_token if token is not None else quote_token
        self.url = TESTNET_WS if testnet else MAINNET_WS
        self.subscribe_trades = subscribe_trades
        self.subscribe_l2 = subscribe_l2
        self._ws: Any = None
        self._running = False

    def _build_subscriptions(self) -> list[dict[str, Any]]:
        subscriptions: list[dict[str, Any]] = []
        if self.subscribe_trades:
            subscriptions.append(
                {
                    "method": "subscribe",
                    "subscription": {"type": "trades", "coin": self.coin},
                }
            )
        if self.subscribe_l2:
            subscriptions.append(
                {
                    "method": "subscribe",
                    "subscription": {"type": "l2Book", "coin": self.coin},
                }
            )
        return subscriptions

    @staticmethod
    def _parse_trade(raw: Any, fallback_coin: str) -> list[Trade]:
        rows: list[Any]
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict) and isinstance(raw.get("data"), list):
            rows = raw["data"]
        elif isinstance(raw, dict):
            rows = [raw]
        else:
            return []
        trades: list[Trade] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            try:
                timestamp_ms = int(item.get("time", 0))
                trade_id = item.get("tid") or item.get("hash")
                trades.append(
                    Trade(
                        coin=str(item.get("coin", fallback_coin)),
                        price=Decimal(str(item["px"])),
                        size=Decimal(str(item["sz"])),
                        side=Side.BUY if item.get("side") == "B" else Side.SELL,
                        timestamp=(
                            datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
                            if timestamp_ms
                            else datetime.now(UTC)
                        ),
                        trade_id=str(trade_id) if trade_id is not None else None,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return trades

    @staticmethod
    def _parse_l2_book(raw: Any, fallback_coin: str) -> OrderBookSnapshot | None:
        if not isinstance(raw, dict):
            return None
        data = raw.get("data", raw)
        if not isinstance(data, dict):
            return None
        levels = data.get("levels")
        if not isinstance(levels, list) or len(levels) < 2:
            return None
        try:
            timestamp_ms = int(data.get("time", 0))
            return OrderBookSnapshot(
                coin=str(data.get("coin", fallback_coin)),
                bids=tuple(
                    OrderBookLevel(
                        price=Decimal(str(level["px"])),
                        size=Decimal(str(level["sz"])),
                        count=int(level.get("n", 1)),
                    )
                    for level in levels[0]
                ),
                asks=tuple(
                    OrderBookLevel(
                        price=Decimal(str(level["px"])),
                        size=Decimal(str(level["sz"])),
                        count=int(level.get("n", 1)),
                    )
                    for level in levels[1]
                ),
                timestamp=(
                    datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
                    if timestamp_ms
                    else datetime.now(UTC)
                ),
            )
        except (KeyError, TypeError, ValueError):
            return None

    async def stream(self) -> AsyncIterator[Trade | OrderBookSnapshot]:
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover
            raise ImportError("install hip4-mm-simulator[live] for streaming") from exc
        self._running = True
        attempt = 0
        while self._running and attempt < 10:
            try:
                async with websockets.connect(self.url) as websocket:
                    self._ws = websocket
                    attempt = 0
                    for subscription in self._build_subscriptions():
                        await websocket.send(json.dumps(subscription))
                    async for message in websocket:
                        payload = json.loads(message)
                        channel = payload.get("channel")
                        data = payload.get("data")
                        if channel == "trades":
                            for trade in self._parse_trade(data, self.coin):
                                yield trade
                        elif channel == "l2Book":
                            snapshot = self._parse_l2_book(data, self.coin)
                            if snapshot is not None:
                                yield snapshot
            except asyncio.CancelledError:
                raise
            except Exception:
                attempt += 1
                await asyncio.sleep(min(2 ** (attempt - 1), 60))
            finally:
                self._ws = None

    async def close(self) -> None:
        self._running = False
        if self._ws is not None:
            await self._ws.close()
