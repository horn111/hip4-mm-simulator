# v0.2 release checklist

## Code gate

- [x] `ruff check .`
- [x] strict `mypy src`
- [x] 51 tests passing
- [x] 90% total coverage, 85% enforced minimum
- [x] deterministic sample replay passes all invariants
- [x] synthetic end-to-end example runs
- [x] build wheel and sdist
- [x] install wheel in a clean environment and run `hip4-sim --version`

## Mainnet validation

- [x] Run `hip4-sim markets` and choose a current liquid coin.
- [x] Generate JSON and Markdown reports twice for the first long real-feed run.
- [x] Confirm byte-identical deterministic reports for that run.
- [x] Fill the partial real-run fields in `docs/VALIDATION.md`.
- [x] Record at least 24 hours to storage outside git. Final run used `#8220`
  on a server-managed systemd service.
- [x] Generate JSON and Markdown reports twice for the 24-hour run.
- [x] Confirm byte-identical deterministic reports for the 24-hour run.
- [x] Fill the 24-hour real-run fields in `docs/VALIDATION.md`.
- [x] Replace every `[TBD]` in announcement and grant drafts.

## Publication

- [x] Confirm `hip4-mm-simulator` is available on PyPI; use
  `hip4-mm-sim` only if unavailable.
- [x] Change `CHANGELOG.md` from Unreleased to the actual UTC date.
- [x] Commit and push the v0.2 branch.
- [x] Merge after CI passes on Python 3.11 and 3.12.
- [x] Tag `v0.2.0` and create a GitHub Release with the validation report.
- [x] Publish the same wheel/sdist to PyPI.
- [x] Verify installation from PyPI in a new environment.

## Launch and grant

- [ ] Publish the reviewed four-post thread.
- [ ] Send the five technical-review messages.
- [ ] Fill `TRACTION_LOG.md` for 7–10 days.
- [ ] Manually review every grant answer and metric.
- [ ] Submit the updated application once.
