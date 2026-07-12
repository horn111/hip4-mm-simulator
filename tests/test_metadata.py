import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from hl_paper_trading.hyperliquid_ws import HyperliquidInfo, HyperliquidWS
from hl_paper_trading.types import Side

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    ("fixture", "coin", "quote", "labels"),
    [
        ("outcome_meta_mainnet.json", "#7780", "USDC", ["Norway", "England"]),
        ("outcome_meta_testnet.json", "#420", "USDH", ["Alpha", "Beta", "Draw"]),
    ],
)
def test_outcome_meta_parser_supports_dynamic_sides(fixture, coin, quote, labels):
    payload = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    markets, _ = HyperliquidInfo.parse_outcome_meta(payload)
    market = markets[0]
    assert market.quote_token == quote
    assert market.tokens[0].coin == coin
    assert [token.label for token in market.tokens] == labels


def test_question_relationships_are_attached():
    payload = json.loads(
        (FIXTURES / "outcome_meta_mainnet.json").read_text(encoding="utf-8")
    )
    markets, questions = HyperliquidInfo.parse_outcome_meta(payload)
    recurring = next(market for market in markets if market.outcome_id == 805)
    assert recurring.question_ids == (141,)
    assert questions[0].fallback_outcome == 809


def test_websocket_requires_an_explicit_market():
    with pytest.raises(ValueError):
        HyperliquidWS()


def test_trade_parser_captures_aggressor_and_exchange_id():
    trades = HyperliquidWS._parse_trade(
        [{"coin": "#8050", "px": "0.49", "sz": "3", "side": "S", "time": 1, "tid": 7}],
        "#8050",
    )
    assert trades[0].side is Side.SELL
    assert trades[0].trade_id == "7"
    assert trades[0].timestamp == datetime.fromtimestamp(0.001, tz=UTC)


def test_book_parser_uses_exchange_timestamp():
    snapshot = HyperliquidWS._parse_l2_book(
        {
            "coin": "#8050",
            "time": 1000,
            "levels": [
                [{"px": "0.4", "sz": "2", "n": 1}],
                [{"px": "0.6", "sz": "3", "n": 2}],
            ],
        },
        "#8050",
    )
    assert snapshot is not None
    assert snapshot.mid_price == Decimal("0.5")
    assert snapshot.timestamp == datetime.fromtimestamp(1, tz=UTC)


def test_malformed_messages_are_ignored():
    assert HyperliquidWS._parse_trade({"bad": True}, "#8050") == []
    assert HyperliquidWS._parse_l2_book({"levels": []}, "#8050") is None
