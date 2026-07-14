"""Deterministic baseline replay and validation reporting."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from hl_paper_trading.matching_engine import MatchingEngine
from hl_paper_trading.recording import RecordedEvent
from hl_paper_trading.types import OrderBookSnapshot, Side, Trade
from hl_paper_trading.utils import Config
from hl_paper_trading.virtual_oms import VirtualOMS
from hl_paper_trading.virtual_wallet import VirtualWallet


class ReplayReport(BaseModel):
    schema_version: str = "1"
    source_sha256: str
    coin: str
    quote_token: str
    start: datetime
    end: datetime
    metadata_events: int
    book_events: int
    trade_events: int
    feed_gaps_over_5s: int
    orders_submitted: int
    orders_rejected: int
    fills: int
    filled_volume: Decimal
    queue_volume_consumed: Decimal
    duplicate_trades_ignored: int
    final_nav: Decimal
    pnl: Decimal
    invariants: dict[str, bool]
    limitations: tuple[str, ...] = (
        "L2 decreases without trades are treated as cancellations.",
        "Receive-time gaps include periods of legitimate market inactivity.",
        "Split, merge, negate, settlement, and fees are outside v0.2.",
        "The included strategy is a validation baseline, not a profitability claim.",
    )


def _events(path: Path) -> Iterator[RecordedEvent]:
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                yield RecordedEvent.model_validate_json(line)


def replay_file(
    path: str | Path,
    *,
    quote_token: str = "USDC",
    initial_quote: Decimal = Decimal("10000"),
    initial_tokens: Decimal = Decimal("1000"),
    order_size: Decimal = Decimal("10"),
    latency_ms: int = 50,
) -> ReplayReport:
    source = Path(path)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    first_book: OrderBookSnapshot | None = None
    first_event: RecordedEvent | None = None
    for event in _events(source):
        first_event = first_event or event
        market_event = event.to_market_event()
        if isinstance(market_event, OrderBookSnapshot):
            first_book = market_event
            break
    if first_event is None or first_book is None or first_book.mid_price is None:
        raise ValueError("recording must contain at least one two-sided book")

    coin = first_book.coin
    initial_mark = first_book.mid_price
    wallet = VirtualWallet(
        quote_balances={quote_token: initial_quote},
        token_balances={coin: initial_tokens},
        token_quotes={coin: quote_token},
        initial_mark_prices={coin: initial_mark},
    )
    engine = MatchingEngine(coin, quote_token)
    oms = VirtualOMS(
        wallet,
        engine,
        Config(latency_ms=str(latency_ms), max_order_size="1000000"),
    )

    counts = {"metadata": 0, "book": 0, "trade": 0}
    start: datetime | None = None
    end: datetime | None = None
    previous_received: datetime | None = None
    gaps = 0
    last_mark = initial_mark
    filled_volume = Decimal("0")
    fills_per_trade: dict[str, Decimal] = {}
    trade_sizes: dict[str, Decimal] = {}

    for event in _events(source):
        counts[event.event_type] += 1
        start = start or event.exchange_timestamp
        end = event.exchange_timestamp
        if (
            previous_received is not None
            and (event.received_timestamp - previous_received).total_seconds() > 5
        ):
            gaps += 1
        previous_received = event.received_timestamp
        market_event = event.to_market_event()
        if isinstance(market_event, OrderBookSnapshot):
            oms.process_book(market_event)
            oms.activate_pending(market_event.timestamp)
            if market_event.mid_price is not None:
                last_mark = market_event.mid_price
            _maintain_baseline_quotes(oms, market_event, order_size)
        elif isinstance(market_event, Trade):
            if market_event.trade_id:
                trade_sizes.setdefault(market_event.trade_id, market_event.size)
            fills = oms.process_trade(market_event)
            for fill in fills:
                filled_volume += fill.fill_size
                if fill.aggressor_trade_id:
                    fills_per_trade[fill.aggressor_trade_id] = (
                        fills_per_trade.get(fill.aggressor_trade_id, Decimal("0"))
                        + fill.fill_size
                    )

    oms.cancel_all()
    assert start is not None and end is not None
    snapshot = wallet.snapshot(
        {coin: last_mark}, quote_token=quote_token, timestamp=end
    )
    balances_non_negative = all(
        value >= 0
        for value in list(snapshot.available_balances.values())
        + list(snapshot.reserved_balances.values())
    )
    volume_conserved = all(
        fill_size <= trade_sizes.get(trade_id, Decimal("0"))
        for trade_id, fill_size in fills_per_trade.items()
    )
    reservations_released = all(
        value == 0 for value in snapshot.reserved_balances.values()
    )
    return ReplayReport(
        source_sha256=source_hash,
        coin=coin,
        quote_token=quote_token,
        start=start,
        end=end,
        metadata_events=counts["metadata"],
        book_events=counts["book"],
        trade_events=counts["trade"],
        feed_gaps_over_5s=gaps,
        orders_submitted=oms.stats["total_submitted"],
        orders_rejected=oms.stats["total_rejected"],
        fills=len(wallet.fills),
        filled_volume=filled_volume,
        queue_volume_consumed=Decimal(str(engine.stats["queue_volume_consumed"])),
        duplicate_trades_ignored=int(engine.stats["duplicates_ignored"]),
        final_nav=snapshot.nav,
        pnl=snapshot.pnl,
        invariants={
            "balances_non_negative": balances_non_negative,
            "trade_volume_conserved": volume_conserved,
            "reservations_released": reservations_released,
        },
    )


def _maintain_baseline_quotes(
    oms: VirtualOMS, book: OrderBookSnapshot, order_size: Decimal
) -> None:
    if book.best_bid is None or book.best_ask is None:
        return
    desired = {(Side.BUY, book.best_bid), (Side.SELL, book.best_ask)}
    existing = {
        (order.side, order.price) for order in oms.open_orders + oms.pending_orders
    }
    if desired == existing:
        return
    oms.cancel_all()
    oms.submit_order_sync(
        Side.BUY, book.best_bid, order_size, current_time=book.timestamp
    )
    oms.submit_order_sync(
        Side.SELL, book.best_ask, order_size, current_time=book.timestamp
    )


def write_report(report: ReplayReport, output: str | Path) -> None:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.suffix.lower() == ".json":
        destination.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return
    data: dict[str, Any] = report.model_dump(mode="json")
    invariant_lines = "\n".join(
        f"- {'PASS' if passed else 'FAIL'}: `{name}`"
        for name, passed in report.invariants.items()
    )
    limitation_lines = "\n".join(f"- {item}" for item in report.limitations)
    destination.write_text(
        "# HIP-4 replay validation report\n\n"
        f"- Source SHA-256: `{data['source_sha256']}`\n"
        f"- Coin / quote: `{report.coin}` / `{report.quote_token}`\n"
        f"- Window: `{data['start']}` to `{data['end']}`\n"
        f"- Events: {report.book_events} books, {report.trade_events} trades\n"
        f"- Feed gaps over 5s: {report.feed_gaps_over_5s}\n"
        f"- Orders / rejected / fills: {report.orders_submitted} / "
        f"{report.orders_rejected} / {report.fills}\n"
        f"- Filled volume: {report.filled_volume}\n"
        f"- Queue volume consumed: {report.queue_volume_consumed}\n"
        f"- Duplicate trades ignored: {report.duplicate_trades_ignored}\n"
        f"- Final NAV / PnL: {report.final_nav} / {report.pnl}\n\n"
        "## Invariants\n\n"
        f"{invariant_lines}\n\n"
        "## Limitations\n\n"
        f"{limitation_lines}\n",
        encoding="utf-8",
    )
