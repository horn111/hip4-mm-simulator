# HIP-4 replay validation report

- Source SHA-256: `2978ac390d3472439311d30d2ed9308f261f64a220b9446e49e851d99a1a1ffd`
- Coin / quote: `#8050` / `USDC`
- Window: `2026-07-12T00:00:00Z` to `2026-07-12T00:00:00.300000Z`
- Events: 2 books, 3 trades
- Feed gaps over 5s: 0
- Orders / rejected / fills: 2 / 0 / 2
- Filled volume: 10
- Queue volume consumed: 50
- Duplicate trades ignored: 1
- Final NAV / PnL: 10500.10 / 0.10

## Invariants

- PASS: `balances_non_negative`
- PASS: `trade_volume_conserved`
- PASS: `reservations_released`

## Limitations

- L2 decreases without trades are treated as cancellations.
- Receive-time gaps include periods of legitimate market inactivity.
- Split, merge, negate, settlement, and fees are outside v0.2.
- The included strategy is a validation baseline, not a profitability claim.
