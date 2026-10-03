# RiskLens 2.0 — portfolio review workspace

Dark desk-style dashboard, independent hedge sizing, editable exposures, baseline comparisons, and a personal notebook.

## Windows quick start

Extract the ZIP, open the `risklens` folder, and double-click `START_RISKLENS.bat`. Or open PowerShell in that folder and run `python app.py`. Open http://127.0.0.1:8000 and leave the terminal running. Requires Python 3.10+; no pip packages.

Stop the previous app with Ctrl+C before running this version. Use Ctrl+F5 in the browser if the old appearance persists. Extract to a fresh folder so you retain any custom CSVs or reports in your old copy.

## New in this version

- Charcoal background, warm text, muted chart colours, compact tables and practical review notes.
- Short-equity hedge multiplier, independent of the whole-book exposure multiplier.
- Edit individual USD exposures under Overview > Edit the book; zero removes a position for the current run.
- Compare current VaR with the original CSV book at 1× and see VaR with short-equity hedges removed.
- A browser-saved Notebook for observations and interview practice.
- A reset button and Windows launcher.

Position editing does not overwrite CSVs. Apply positions to recalculate. Calculations use entered values, then the hedge multiplier for negative equity exposures, then the whole-book multiplier. A hedge multiplier of zero removes those positions. The original-book comparison always uses the CSV book, exposure 1×, and current confidence. The unhedged comparison removes all negative equity positions from the edited book, keeping the chosen overall scale. It is an illustrative sensitivity check, not an optimization recommendation.

Scenario CSV exports include position results, scale and input hash. Saved JSON/SQLite runs also include comparison results and hedge settings. Notebook text stays in browser storage and is not included in audit exports. No trading, live data, derivatives pricing or regulatory capital model is provided.

## Existing analytical features

Historical VaR/ES, normal VaR benchmark, duration-convexity bond shocks, scenario attribution, rolling backtesting, Kupiec coverage diagnostic, input validation, CSV exports and SQLite/JSON audit runs. All data is synthetic.

Run tests: `python -m unittest discover -s tests -v`.
Save a default report: `python app.py --report`.
Read `docs/METHODOLOGY.md` and `docs/INTERVIEW_GUIDE.md` for financial assumptions and interview preparation.
