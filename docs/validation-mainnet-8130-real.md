# HIP-4 replay validation report

- Source SHA-256: `00f2b2629e118f69fa0269694898108f98c752c6eea8d2f5fa01c0688438d3e1`
- Coin / quote: `#8130` / `USDC`
- Window: `2026-07-12T12:46:41.455959Z` to `2026-07-13T01:37:02.799000Z`
- Events: 6756 books, 614 trades
- Feed gaps over 5s: 6450
- Orders / rejected / fills: 390 / 2 / 40
- Filled volume: 364.0
- Queue volume consumed: 207196.0
- Duplicate trades ignored: 90
- Final NAV / PnL: 10594.373620 / -9.396380

## Invariants

- PASS: `balances_non_negative`
- PASS: `trade_volume_conserved`
- PASS: `reservations_released`

## Limitations

- L2 decreases without trades are treated as cancellations.
- Receive-time gaps include periods of legitimate market inactivity.
- Split, merge, negate, settlement, and fees are outside v0.2.
- The included strategy is a validation baseline, not a profitability claim.
