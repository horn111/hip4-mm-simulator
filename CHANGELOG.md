# Changelog

## 0.2.0 - 2026-07-15

### Added

- Dynamic HIP-4 `outcomeMeta` discovery with arbitrary side labels, questions,
  and quote tokens.
- L2-seeded, aggressor-aware, price-time matching with trade-volume
  conservation and duplicate-ID protection.
- Spot quote/token ledger with order reservations and NAV-based PnL.
- Versioned JSONL recorder, deterministic replay, invariant report, and
  `hip4-sim` CLI.
- Captured metadata fixtures and a small reproducible replay fixture.

### Changed

- Package distribution renamed to `hip4-mm-simulator`; Python import remains
  `hl_paper_trading`.
- `Side.BID/ASK` replaced by `Side.BUY/SELL`.
- Orders, trades, fills, and books now identify explicit HIP-4 coins.
- WebSocket connections no longer default to obsolete outcome ID 1.
- Project status is documented as experimental alpha.

### Removed

- Synthetic naked-short accounting and hard-coded YES/NO portfolio fields.
- Claims of production readiness and unimplemented settlement support.

## 0.1.0 - 2026-05-05

- Initial proof-of-concept matching engine, wallet, OMS, synthetic source, and
  read-only WebSocket connector.
