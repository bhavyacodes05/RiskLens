# RiskLens 3.0 — portfolio risk workspace

A local Python dashboard for market risk, key-rate stress testing and backtest diagnostics. Dark interface, editable exposures, independent equity hedge control, real Treasury history and traceable reports.

## Start on Windows

Extract this ZIP to a new folder. Open the inner `risklens` folder and double-click `START_RISKLENS.bat`, or run `python app.py` in that folder. Open http://127.0.0.1:8000. Keep the terminal running; Ctrl+C stops it. Stop the old app first and use Ctrl+F5 if needed.

Python 3.10+ and a modern browser; no external Python packages or API keys. Both bundled datasets work offline.

## What's new

- Independent hedge multiplier retained from v2: resize negative equity positions without changing long equities or bonds.
- Three yield factors: 2Y, 5Y and 10Y key-rate durations, with separate sliders, curve visualization, steepening and flattening scenarios.
- Official U.S. Treasury 2024–2025 observations: 499 yield-level dates producing 498 consecutive-observation changes. This dataset runs a **bond-only hypothetical book**; it does not contain historical equity or FX returns.
- Permissioned multi-asset CSV import with explicit return conventions, common-calendar checks, provenance and no silent missing-value filling.
- Exception transitions, longest exception run, Christoffersen independence and conditional-coverage tests.
- 95% Wilson and block-bootstrap exception-frequency intervals; block-bootstrap VaR and ES intervals.

## Try the new features

1. Select **U.S. Treasury 2024–2025 · bonds**. The book contains bonds only; the inactive equity/FX controls do not contribute risk.
2. Open Stress lab and click **Steepen**: 2Y −50 bp, 5Y +25 bp, 10Y +100 bp. Equity/FX settings are left at their chosen values, so use the named Curve steepening scenario for a pure curve shock in multi-asset mode.
3. Compare the two bonds' key-rate durations and P&L. The sum of each bond's KRDs equals its total modified duration.
4. Open Backtesting. Inspect transition counts and longest exception run before interpreting p-values. An all-clear sample displays an unavailable independence test, not a model-quality pass.
5. Return to Synthetic multi-asset to compare hedge sizes. Baseline uses the original CSV book at 1× with the selected confidence and dataset.

## Commands

```bash
python app.py
python app.py --report --dataset treasury
python -m unittest discover -s tests -v
```

`python -m risklens.sample` regenerates and overwrites the synthetic portfolio and factor CSVs. It does not alter the historical Treasury snapshot.

Historical multi-asset import instructions are in `docs/HISTORICAL_DATA.md`. User-imported data are excluded by `.gitignore`; check your licence before distributing them elsewhere.

## Project structure

- `app.py`: local HTTP interface and report command.
- `risklens/engine.py`: validation, position P&L, scenarios, VaR/ES and rolling backtest.
- `risklens/diagnostics.py`: transition tests, Wilson intervals and circular-block bootstrap.
- `risklens/history.py`: historical-data modes and strict CSV importer.
- `risklens/reporting.py`: SQLite/JSON audit output.
- `web/index.html`: dashboard, controls and notebook.
- `data/`: synthetic inputs and attributed Treasury snapshot/calendar/provenance.
- `tests/`: analytical invariants, boundary cases and data-quality checks.
- `docs/`: methodology, historical-data conventions, verification and interview guide.

## Scope

Historical observations do not make the sample positions real. Bond key-rate durations are illustrative, and v3 uses first-order KRD P&L, without convexity or cross-gamma. Treasury par yields proxy curve nodes; no zero-curve bootstrapping is performed. There is no live feed, derivatives pricer, credit exposure model, automated trading or regulatory capital calculation.

Saved runs retain effective positions, shocks, selected dataset, provenance, settings and diagnostic results. Notebook text stays in the browser. This is an independent educational project with no Nomura affiliation.
