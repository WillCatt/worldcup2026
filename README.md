# World Cup 2026 — a model-led live forecast

A probabilistic forecast of the 2026 FIFA World Cup (11 Jun – 19 Jul 2026, USA/Canada/Mexico).
The site is **static**; the "live" element is the *model re-forecasting* each day as real
results land — not a scoreboard. The model is the star.

Sibling to the Blackjack Simulator in the portfolio — shares the Monte Carlo + betting-markets
through-line.

## What it does

1. **Rates teams** with a Dixon–Coles bivariate-Poisson goals model (attack/defence strengths,
   home & neutral-venue adjustment, exponential **time-decay** so recent form counts more),
   fit on ~150 years of international results. *(the time-series core)*
2. **Simulates the tournament** — the real 48-team / 12-group format (top 2 + 8 best third-placed
   → Round of 32 → … → Final), Monte Carlo ×50k. Outputs each team's odds of reaching each round
   and lifting the trophy.
3. **Backtests honestly** on the 2018 & 2022 World Cups — calibration, Brier score, log-loss vs
   two baselines: the FIFA ranking and the bookmaker's implied odds.
4. **Stays live, zero-cost** — a free daily GitHub Action pulls completed results, conditions the
   remaining bracket on what actually happened, re-simulates, and commits a fresh `output/forecast.json`.
   The portfolio page reads that JSON. If the feed ever fails, the last good snapshot stays up.

## Architecture

```
worldcup2026/
├── data/
│   ├── results.csv          # training history (auto-downloaded, gitignored)
│   └── groups.json          # the real 2026 draw + bracket structure
├── src/
│   ├── data.py              # download / load the results history
│   ├── ratings.py           # Dixon–Coles goals model + time-decay
│   ├── tournament.py        # 2026 format: groups, third-place rules, bracket
│   ├── simulate.py          # Monte Carlo the bracket → per-team round/title odds
│   ├── backtest.py          # validate on 2018 + 2022 (calibration, Brier, log-loss)
│   └── update.py            # pull live results → re-condition → re-sim → write forecast.json
├── output/forecast.json     # baked result the portfolio page reads
├── figures/                 # palette-matched plots for the write-up
└── .github/workflows/daily.yml   # free cron: run update.py, commit fresh JSON
```

## Data sources (both free)

- **Training history** — [martj42/international_results](https://github.com/martj42/international_results)
  `results.csv` (every men's international, 1872→present). No auth; raw GitHub fetch.
- **Live 2026 feed** — [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json)
  (public domain, no API key, no rate limits).

## Run

```bash
pip install -r requirements.txt
python -m src.data        # download the history
python -m src.ratings     # fit + cache team strengths
python -m src.simulate    # pre-tournament Monte Carlo → output/forecast.json
python -m src.backtest    # validation report + figures
```

## Status

Standalone build. Moves into the portfolio site (`projects/worldcup.html`, house style) once happy.
