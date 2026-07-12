# Migrating from v0.1 to v0.2

v0.2 intentionally breaks the proof-of-concept API to make execution and
accounting assumptions explicit.

| v0.1 | v0.2 |
|---|---|
| `Side.BID`, `Side.ASK` | `Side.BUY`, `Side.SELL` |
| `market` | explicit `coin` plus `quote_token` |
| `MatchingEngine(market=...)` | `MatchingEngine(coin, quote_token)` |
| trade-only matching | call `process_book` before order activation |
| `VirtualWallet(initial_balance=...)` | quote/token balance mappings |
| negative YES inventory | spot token balance; naked sells rejected |
| `snapshot(mark_price=...)` | `snapshot({coin: mark}, quote_token=...)` |
| `HyperliquidWS(outcome_id=1)` | `HyperliquidWS(token=...)` or explicit coin |

Orders submitted before a fresh L2 book become `REJECTED/BOOK_STALE`. BUY
orders reserve quote balance at their limit; SELL orders reserve token balance.
Cancellation releases only the unfilled reservation.

The distribution name changes, but imports do not:

```bash
pip install "hip4-mm-simulator[live]==0.2.0"
```

```python
from hl_paper_trading import HyperliquidInfo, MatchingEngine
```
