# HIP-4 replay validation report

- Source SHA-256: `8d155b56c98daaf186eaa12150d2560f71fa2388a7b73776c9b2520ae2249dfc`
- Coin / quote: `#8220` / `USDC`
- Window: `2026-07-13T19:21:27.943783Z` to `2026-07-14T19:21:26.107000Z`
- Events: 16087 books, 562 trades
- Feed gaps over 5s: 15755
- Orders / rejected / fills: 550 / 0 / 38
- Filled volume: 364.0
- Queue volume consumed: 12875.0
- Duplicate trades ignored: 240
- Final NAV / PnL: 10544.669730 / -4.060270

## Invariants

- PASS: `balances_non_negative`
- PASS: `trade_volume_conserved`
- PASS: `reservations_released`

## Limitations

- L2 decreases without trades are treated as cancellations.
- Receive-time gaps include periods of legitimate market inactivity.
- Split, merge, negate, settlement, and fees are outside v0.2.
- The included strategy is a validation baseline, not a profitability claim.
