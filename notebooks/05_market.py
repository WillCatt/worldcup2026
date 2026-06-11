# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#   kernelspec:
#     display_name: mlfootball
#     language: python
#     name: mlfootball
# ---

# %% [markdown]
# # Model vs Market — can a hobbyist model beat the closing line?
#
# Every match at the 2026 World Cup, a Monte-Carlo model's win/draw/loss probability is
# **frozen before kickoff** and scored against the bookmakers' de-vigged odds. The closing
# line is one of the most efficient forecasts in the world, so the honest, expected, and
# *publishable* result is that the model **loses** to it. The value of the piece is not the
# model — it's the measurement infrastructure: a hardened odds scraper, a write-once freeze
# protocol, two de-vig methods, and proper scoring with the match count never out of sight.
#
# This notebook is the narrative surface. The reusable logic lives in `mlfootball.market.*`
# and the live capture runs unattended from `launchd` (see `mlfootball/market/deploy.py`).
# Three decisions define the piece, narrated below:
#
# 1. **De-vigging is a method choice, not a footnote** — proportional vs Shin diverge on
#    longshots, and we say which we use and why.
# 2. **The freeze is enforced in the database** — model probabilities are written once,
#    timestamped, before kickoff, and can never be edited. No market feature can leak in.
# 3. **No number without N** — a one-match lead over the closing line is noise, and the
#    scoreboard is built to keep saying so until N is large.

# %%
import pandas as pd

from mlfootball.market import db, devig, fixtures, model_freeze, score, export

pd.set_option("display.width", 110)

# %% [markdown]
# ## 1. The fixtures and the schema
#
# The calendar is reused verbatim from the travel-burden piece (`mlfootball.travel.SCHEDULE`)
# — one source of truth for who plays whom, when. Seeding is idempotent.

# %%
con = db.init_db()
n = fixtures.seed(con)
print(f"{n} group-stage fixtures seeded.")
print(pd.read_sql_query(
    "SELECT match_id, grp, kickoff_utc FROM matches ORDER BY kickoff_utc LIMIT 4", con))

# %% [markdown]
# ## 2. De-vigging: proportional vs Shin
#
# Decimal odds imply probabilities that sum to more than one — the **overround**. To compare
# a book to the model you must strip it. **Proportional** normalisation spreads the margin
# evenly; **Shin's** method models it as protection against insider traders, concentrating it
# on longshots. At `z = 0` Shin collapses to proportional. They agree on coin-flips and
# **diverge on longshots** — so the choice matters, and we score against the Shin-de-vigged
# closing line.

# %%
for tag, odds in [("heavy favourite + longshot", [1.25, 6.0, 12.0]),
                  ("near coin-flip", [2.6, 3.3, 2.7])]:
    c = devig.compare(odds)
    print(f"\n{tag}: odds={odds}  overround={c['overround']:.1%}  Shin z={c['shin_z']:.3f}")
    for r in c["by_outcome"]:
        print(f"  {r['outcome']:<5} proportional={r['proportional']:.3f}  "
              f"shin={r['shin']:.3f}  gap={r['gap']:+.3f}")

# %% [markdown]
# The longshot (away at 12.0) is where the methods part company: Shin pulls it *down* relative
# to proportional, because it treats long-odds prices as inflated by insider protection. On the
# coin-flip the two are within a fraction of a point. This is the divergence the methods note
# shows the reader directly.

# %% [markdown]
# ## 3. The freeze protocol — enforced, not promised
#
# Model probabilities come from the resurrected Dixon-Coles engine (`mlfootball.ratings`):
# fit attack/defence strengths on international-results history, build the scoreline grid for
# the fixture, collapse it to P(home)/P(draw)/P(away). The only input is match history — the
# model **cannot see the odds**, so it cannot be circular. The probability is then written
# **once** via `db.freeze_model`, which refuses to overwrite with different numbers and refuses
# to write at all after kickoff.

# %%
out = model_freeze.freeze_upcoming(within_hours=36, con=con)
print(f"froze {out['frozen']} upcoming match(es); model inputs = {model_freeze.MODEL_INPUTS}")

# attempt a retroactive edit — the database refuses it
row = pd.read_sql_query("SELECT match_id, p_home, p_draw, p_away FROM frozen_model LIMIT 1", con)
if len(row):
    mid = row.match_id.iloc[0]
    try:
        db.freeze_model(con, match_id=mid, model_version=model_freeze.MODEL_VERSION,
                        p_home=0.99, p_draw=0.005, p_away=0.005)
        print("ERROR: overwrite was allowed")
    except db.FrozenModelError as e:
        print("retroactive edit refused ✓:", str(e)[:70], "…")

# %% [markdown]
# ## 4. Scoring — on identical match sets, always with N
#
# Four series are scored on the *same* settled matches: the frozen **model**, the de-vigged
# **closing** line (the benchmark), the de-vigged **opening** line (earlier, worse — the
# market learning), and a **uniform** 1/3 dummy (the floor). Two proper scoring rules:
# multiclass **Brier** and **log-loss**, reported cumulatively and rolling.
#
# Live early in the tournament there may be few or no settled matches, so for a populated
# illustration we score the synthetic preview database the page is built against
# (`mlfootball.market.demo_seed`); the live pipeline scores `odds.sqlite` the same way.

# %%
from mlfootball.market import demo_seed  # noqa: E402
_, payload = demo_seed.seed()
sb = payload["scoreboard"]["series"]
print(f"N = {payload['meta']['n_settled']} settled matches\n")
print(f"{'series':<10}{'N':>4}{'Brier':>9}{'log-loss':>10}")
for s in ("model", "closing", "opening", "uniform"):
    d = sb[s]
    print(f"{s:<10}{d['n']:>4}{d['mean_brier']:>9.4f}{d['mean_logloss']:>10.4f}")

nn = payload["scoreboard"]["n_needed"]
print(f"\nModel's Brier edge over closing: {nn['mean_edge']:+.4f} (per-match sd {nn['sd']}).")
print(f"That gap wouldn't clear two standard errors until N ≈ {nn['n_for_signif']} matches —")
print("so any early model lead is variance, and the page says exactly that.")

# %% [markdown]
# The ordering is the thesis in miniature: **closing < model < opening < uniform** on Brier.
# The closing line is sharpest; the model sits between opening and closing; the uniform dummy
# is the floor every real forecaster must clear. And the model's apparent edge or deficit is
# not yet significant — which is the whole point of pairing every number with its N.

# %% [markdown]
# ## 5. Calibration and steam
#
# Calibration pools every (predicted-probability, outcome) pair into reliability bins, each
# carrying its count so thin early bins read as the weak evidence they are. `detect_steam`
# flags sharp implied-probability moves within a short window — the market repricing on news.

# %%
demo = db.connect(demo_seed.DEMO_DB)
cal = score.calibration(demo, series="model", method="shin", n_bins=5)
print("model reliability bins (predicted → observed, with count):")
for b in cal:
    if b["n"]:
        print(f"  [{b['lo']:.1f},{b['hi']:.1f})  pred={b['pred']:.2f}  obs={b['obs']:.2f}  n={b['n']}")

mid = pd.read_sql_query(
    "SELECT match_id FROM results JOIN matches USING(match_id) LIMIT 1", demo).match_id.iloc[0]
steam = score.detect_steam(demo, mid, threshold=0.04, window_min=720)
print(f"\nsteam moves on {mid}: {len(steam)}")
for s in steam[:3]:
    print(f"  {s['outcome']} {s['delta']:+.3f}  ({s['from_ts']} → {s['to_ts']})")
demo.close()

# %% [markdown]
# ## 6. Export
#
# Everything the page needs is baked into one static `site/data/market.json`: per-match
# de-vigged implied-probability time-series per book, the frozen model line, steam markers,
# results, the scoreboard, calibration bins, editorial cards, the de-vig comparison and a
# freshness block. No ML or database at runtime — the page is static. (The synthetic preview
# above already wrote it; the live pipeline overwrites with captured data.)

# %%
print("market.json written for the page →", (export.SITE_DATA / "market.json"))
con.close()
