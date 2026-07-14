# v0.2 validation protocol

## Reproducible sample

Run:

```bash
hip4-sim replay tests/fixtures/sample_recording.jsonl \
  --output docs/validation-sample.md
```

Expected invariants:

- available and reserved balances never become negative;
- aggregate fills caused by a trade never exceed its observed size;
- all outstanding reservations are released at the end;
- replaying the same file produces the same report fields;
- repeated exchange trade IDs do not create repeated fills.

## Mainnet 24-hour run protocol

1. Select a liquid current token using `hip4-sim markets`.
2. Record exactly one coin for at least 24 hours.
3. Preserve the raw file outside git and record its SHA-256 in the report.
4. Run replay twice and compare the generated JSON reports byte-for-byte.
5. Publish the Markdown report with the v0.2 GitHub Release.

The published report must include the exact outcome, quote token, UTC window,
commit SHA, data hash, books/trades, receive-time gaps, orders/rejections,
fills, queue volume consumed, duplicate IDs, NAV, and every invariant result.

## Interpretation

A PASS establishes internal consistency against the observed public feed. It
does not establish exact exchange queue position, counterfactual market impact,
or strategy profitability. L2 cancellations and additions cannot reveal full
order-level causality; this simulator therefore never treats an unexplained L2
decrease as executed volume.

## Mainnet interrupted run: 2026-07-12 / #8130

The first long recorder process stopped before the planned 24-hour window. This
is useful as a real-feed validation artifact, but it should not be described as
the final 24-hour release run.

- Outcome / coin: `World Cup Semifinal: France vs Spain / #8130 (France)`
- Quote token: `USDC`
- UTC window: `2026-07-12T12:46:41.455959Z` to `2026-07-13T01:37:02.799000Z`
- Duration: about 12 hours 50 minutes
- Code state: local v0.2 branch before publication; final release commit SHA
  remains part of the pending 24-hour report fields below.
- Source SHA-256:
  `00f2b2629e118f69fa0269694898108f98c752c6eea8d2f5fa01c0688438d3e1`
- Raw JSONL events: 7371 total
- Replay report: `docs/validation-mainnet-8130-real.md`
- Replay JSON: `docs/validation-mainnet-8130-real.json`
- Replay determinism: two generated JSON reports were byte-identical
- Events: 6756 books, 614 trades
- Feed gaps over 5s: 6450
- Orders / rejected / fills: 390 / 2 / 40
- Filled volume: 364.0
- Queue volume consumed: 207196.0
- Duplicate trades ignored: 90
- Final NAV / PnL: 10594.373620 / -9.396380
- Invariants: balances non-negative, trade volume conserved, reservations
  released

## Mainnet 24-hour run: 2026-07-13 / #8220

This is the release validation run. The recorder ran on a server under systemd
for a 24-hour wall-clock duration. The raw JSONL remains outside git; only the
report and source hash are published.

- Outcome / coin: `World Cup Semifinal: England vs Argentina / #8220 (England)`
- Quote token: `USDC`
- UTC window: `2026-07-13T19:21:27.943783Z` to `2026-07-14T19:21:26.107000Z`
- Duration: about 24 hours by recorder wall-clock timeout
- Code state used for recording/replay:
  `b04644acf6b9ec970b61f75d2980c3efb3e1e242`
- Source SHA-256:
  `8d155b56c98daaf186eaa12150d2560f71fa2388a7b73776c9b2520ae2249dfc`
- Raw JSONL events: 16650 total, including metadata
- Replay report: `docs/validation-mainnet-8220-24h.md`
- Replay JSON: `docs/validation-mainnet-8220-24h.json`
- Replay determinism: two generated JSON reports were byte-identical
- Events: 16087 books, 562 trades
- Feed gaps over 5s: 15755
- Orders / rejected / fills: 550 / 0 / 38
- Filled volume: 364.0
- Queue volume consumed: 12875.0
- Duplicate trades ignored: 240
- Final NAV / PnL: 10544.669730 / -4.060270
- Invariants: balances non-negative, trade volume conserved, reservations
  released
