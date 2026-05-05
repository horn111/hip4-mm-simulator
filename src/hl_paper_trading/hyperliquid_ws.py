"""Real-time Hyperliquid mainnet WebSocket connector for outcome markets.

This module provides a read-only WebSocket client that subscribes to
real trades and order book updates from Hyperliquid's mainnet API.
It converts raw exchange messages into framework-native ``Trade`` and
``OrderBookSnapshot`` objects for consumption by the paper trading engine.

Usage::

    from hl_paper_trading.hyperliquid_ws import HyperliquidWS

    ws = HyperliquidWS(outcome_id=1)  # BTC daily outcome

    async for event in ws.stream():
        if isinstance(event, Trade):
            fills = engine.process_trade(event)
        elif isinstance(event, OrderBookSnapshot):
            strategy.on_orderbook_update(event)

WebSocket endpoint:
    - Mainnet: ``wss://api.hyperliquid.xyz/ws``
    - Testnet: ``wss://api.hyperliquid-testnet.xyz/ws``

HIP-4 Asset Encoding:
    Outcome trades use ``#<encoding>`` coin format where
    ``encoding = 10 * outcome_id + side`` (side 0 = YES, side 1 = NO).

See: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncIterator, Optional, Union

import structlog

from hl_paper_trading.types import (
    OrderBookLevel,
    OrderBookSnapshot,
    Side,
    Trade,
    outcome_coin_name,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAINNET_WS = "wss://api.hyperliquid.xyz/ws"
TESTNET_WS = "wss://api.hyperliquid-testnet.xyz/ws"

# Reconnection parameters
MAX_RECONNECT_ATTEMPTS = 10
RECONNECT_BASE_DELAY_S = 1.0
RECONNECT_MAX_DELAY_S = 60.0


# ---------------------------------------------------------------------------
# HyperliquidWS
# ---------------------------------------------------------------------------

class HyperliquidWS:
    """Read-only WebSocket client for Hyperliquid outcome market data.

    Subscribes to trades and L2 book updates for a specific HIP-4 outcome
    market and yields framework-native ``Trade`` / ``OrderBookSnapshot``
    objects.

    Args:
        outcome_id: The HIP-4 outcome identifier (e.g. 1 for BTC daily).
        side: Which side to subscribe (0 = YES, 1 = NO, None = both).
        testnet: If True, connect to testnet instead of mainnet.
        subscribe_trades: Subscribe to trade feed.
        subscribe_l2: Subscribe to L2 order book snapshots.

    Example::

        ws = HyperliquidWS(outcome_id=1, side=0)  # YES side of BTC daily

        async for event in ws.stream():
            print(event)
    """

    def __init__(
        self,
        outcome_id: int = 1,
        side: Optional[int] = 0,
        *,
        testnet: bool = False,
        subscribe_trades: bool = True,
        subscribe_l2: bool = True,
    ) -> None:
        self.outcome_id = outcome_id
        self.sides = [side] if side is not None else [0, 1]
        self.url = TESTNET_WS if testnet else MAINNET_WS
        self.subscribe_trades = subscribe_trades
        self.subscribe_l2 = subscribe_l2

        # Derive coin names from HIP-4 encoding
        self.coins = [
            outcome_coin_name(outcome_id, s) for s in self.sides
        ]

        self._ws = None
        self._running = False

        logger.info(
            "hyperliquid_ws.init",
            outcome_id=outcome_id,
            coins=self.coins,
            url=self.url,
        )

    # -- Subscription messages -----------------------------------------------

    def _build_subscriptions(self) -> list[dict]:
        """Build WebSocket subscription messages per Hyperliquid API spec."""
        subs: list[dict] = []

        for coin in self.coins:
            if self.subscribe_trades:
                subs.append({
                    "method": "subscribe",
                    "subscription": {
                        "type": "trades",
                        "coin": coin,
                    },
                })

            if self.subscribe_l2:
                subs.append({
                    "method": "subscribe",
                    "subscription": {
                        "type": "l2Book",
                        "coin": coin,
                    },
                })

        return subs

    # -- Message parsing -----------------------------------------------------

    @staticmethod
    def _parse_trade(raw: dict, coin: str) -> list[Trade]:
        """Parse a trades channel message into framework Trade objects."""
        trades: list[Trade] = []

        for t in raw.get("data", []):
            try:
                trade = Trade(
                    market=coin,
                    price=Decimal(str(t["px"])),
                    size=Decimal(str(t["sz"])),
                    side=Side.BID if t.get("side", "B") == "B" else Side.ASK,
                    timestamp=datetime.fromtimestamp(
                        t.get("time", 0) / 1000, tz=timezone.utc
                    ) if "time" in t else datetime.now(timezone.utc),
                )
                trades.append(trade)
            except (KeyError, ValueError) as exc:
                logger.warning("trade_parse_error", error=str(exc), raw=t)

        return trades

    @staticmethod
    def _parse_l2_book(raw: dict, coin: str) -> Optional[OrderBookSnapshot]:
        """Parse an l2Book channel message into an OrderBookSnapshot."""
        try:
            book = raw.get("data", {}).get("levels", [[], []])
            bids = [
                OrderBookLevel(
                    price=Decimal(str(lvl["px"])),
                    size=Decimal(str(lvl["sz"])),
                    count=int(lvl.get("n", 1)),
                )
                for lvl in book[0]
            ]
            asks = [
                OrderBookLevel(
                    price=Decimal(str(lvl["px"])),
                    size=Decimal(str(lvl["sz"])),
                    count=int(lvl.get("n", 1)),
                )
                for lvl in book[1]
            ]
            return OrderBookSnapshot(
                market=coin,
                bids=bids,
                asks=asks,
                timestamp=datetime.now(timezone.utc),
            )
        except (KeyError, ValueError, IndexError) as exc:
            logger.warning("l2_parse_error", error=str(exc))
            return None

    # -- Streaming -----------------------------------------------------------

    async def stream(self) -> AsyncIterator[Union[Trade, OrderBookSnapshot]]:
        """Connect to Hyperliquid WebSocket and yield parsed events.

        Automatically reconnects on disconnection with exponential backoff.

        Yields:
            Trade or OrderBookSnapshot objects as they arrive.

        Raises:
            ImportError: If ``websockets`` is not installed.
        """
        try:
            import websockets  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError(
                "The 'websockets' package is required for live data. "
                "Install it with: pip install websockets>=12.0\n"
                "Or install the live extras: pip install hl-paper-trading[live]"
            )

        self._running = True
        attempt = 0

        while self._running and attempt < MAX_RECONNECT_ATTEMPTS:
            try:
                logger.info(
                    "ws.connecting",
                    url=self.url,
                    attempt=attempt + 1,
                    coins=self.coins,
                )

                async with websockets.connect(self.url) as ws:
                    self._ws = ws
                    attempt = 0  # reset on successful connection

                    # Send subscriptions
                    for sub in self._build_subscriptions():
                        await ws.send(json.dumps(sub))
                        logger.debug("ws.subscribed", subscription=sub)

                    # Process messages
                    async for raw_msg in ws:
                        try:
                            msg = json.loads(raw_msg)
                        except json.JSONDecodeError:
                            continue

                        channel = msg.get("channel", "")
                        data = msg.get("data", {})

                        if channel == "trades":
                            coin = data.get("coin", self.coins[0]) if isinstance(data, dict) else self.coins[0]
                            # Trades data may be at top level or nested
                            trade_data = data if isinstance(data, dict) else {"data": data}
                            for trade in self._parse_trade(trade_data, coin):
                                yield trade

                        elif channel == "l2Book":
                            coin = data.get("coin", self.coins[0]) if isinstance(data, dict) else self.coins[0]
                            snapshot = self._parse_l2_book(
                                {"data": data} if isinstance(data, dict) else data,
                                coin,
                            )
                            if snapshot:
                                yield snapshot

                        elif channel == "subscriptionResponse":
                            logger.info("ws.subscription_confirmed", data=data)

            except Exception as exc:
                attempt += 1
                delay = min(
                    RECONNECT_BASE_DELAY_S * (2 ** (attempt - 1)),
                    RECONNECT_MAX_DELAY_S,
                )
                logger.warning(
                    "ws.disconnected",
                    error=str(exc),
                    reconnect_in_s=delay,
                    attempt=attempt,
                )
                await asyncio.sleep(delay)
            finally:
                self._ws = None

        if attempt >= MAX_RECONNECT_ATTEMPTS:
            logger.error("ws.max_reconnects_exceeded")

    async def close(self) -> None:
        """Gracefully close the WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
            logger.info("ws.closed")
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
