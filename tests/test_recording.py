from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from hl_paper_trading.cli import main, parse_duration
from hl_paper_trading.recording import EventRecorder, RecordedEvent
from hl_paper_trading.replay import build_demo_trace, replay_file, write_report
from hl_paper_trading.types import Side, Trade

FIXTURE = Path(__file__).parent / "fixtures" / "sample_recording.jsonl"


def test_recorded_event_roundtrip():
    event = Trade(
        coin="#8050",
        price=Decimal("0.5"),
        size=Decimal("2"),
        side=Side.BUY,
        timestamp=datetime(2026, 7, 12, tzinfo=UTC),
        trade_id="t1",
    )
    recorded = RecordedEvent.from_market_event(
        event, received_timestamp=event.timestamp
    )
    assert recorded.to_market_event() == event
    assert RecordedEvent.model_validate_json(recorded.model_dump_json()) == recorded


def test_event_recorder_writes_versioned_jsonl(tmp_path):
    destination = tmp_path / "nested" / "events.jsonl"
    now = datetime(2026, 7, 12, tzinfo=UTC)
    with EventRecorder(destination) as recorder:
        recorder.write_metadata(
            coin="#8050", payload={"quote_token": "USDC"}, timestamp=now
        )
    line = destination.read_text(encoding="utf-8")
    assert '"schema_version":"1"' in line
    assert '"event_type":"metadata"' in line


def test_replay_is_deterministic_and_invariants_pass():
    first = replay_file(FIXTURE)
    second = replay_file(FIXTURE)
    assert first == second
    assert first.book_events == 2
    assert first.trade_events == 3
    assert first.fills == 2
    assert first.duplicate_trades_ignored == 1
    assert all(first.invariants.values())


def test_demo_trace_is_deterministic_and_causal():
    first = build_demo_trace(FIXTURE)
    second = build_demo_trace(FIXTURE)

    assert first.model_dump_json() == second.model_dump_json()
    assert first.schema_version == "demo-1"
    assert first.source_sha256 == (
        "2978ac390d3472439311d30d2ed9308f261f64a220b9446e49e851d99a1a1ffd"
    )
    assert len(first.steps) == 6

    sell_trade = first.steps[3]
    assert sell_trade.trade is not None
    assert sell_trade.trade.side is Side.SELL
    assert sell_trade.queue_consumed_delta == Decimal("25")
    assert sell_trade.fills[0].side is Side.BUY
    assert sell_trade.fills[0].size == Decimal("5")
    assert sell_trade.orders[0].queue_ahead == Decimal("0")

    duplicate = first.steps[-1]
    assert duplicate.duplicate_ignored is True
    assert duplicate.trade is not None and duplicate.trade.duplicate is True
    assert all(value == 0 for value in duplicate.wallet.reserved_balances.values())
    assert first.summary.filled_volume == Decimal("10")
    assert first.summary.queue_volume_consumed == Decimal("50")
    assert first.summary.duplicate_trades_ignored == 1


def test_report_writers_and_cli(tmp_path):
    report = replay_file(FIXTURE)
    markdown = tmp_path / "report.md"
    json_path = tmp_path / "report.json"
    write_report(report, markdown)
    write_report(report, json_path)
    assert "PASS" in markdown.read_text(encoding="utf-8")
    assert '"trade_volume_conserved": true' in json_path.read_text(encoding="utf-8")
    assert main(["replay", str(FIXTURE), "--output", str(tmp_path / "cli.md")]) == 0


def test_duration_parser():
    assert parse_duration("24h") == timedelta(hours=24)
    assert parse_duration("30m") == timedelta(minutes=30)
