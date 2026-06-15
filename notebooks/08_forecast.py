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
# # Every match, predicted — then marked
#
# The Dixon-Coles goals model (`ratings.py`) turns 150 years of international results into a
# probability for every scoreline of every match. This notebook holds it to account: it
# **freezes the model the day before kickoff**, predicts all 72 group fixtures, and then
# grades those frozen predictions against the actual results as they land.
#
# Why freezing matters: if the ratings absorbed in-tournament results, the "forecast" would
# be cheating. Fitting strictly on matches before `ASOF` makes every call genuinely
# out-of-sample. This is the sibling of the Model-vs-Market piece — but the yardstick here is
# **reality**, not the bookmaker's closing line.

# %%
import pandas as pd

from mlfootball import forecast, ratings, data

pd.set_option("display.width", 110)
print("model frozen at:", forecast.ASOF.date())

# %% [markdown]
# ## 1. Fit the frozen model and predict a match
#
# `outcome_probs` gives 1X2; `score_matrix` gives the full scoreline grid (the most likely
# scores come straight off it). Host nations get a venue edge only when playing at home.

# %%
s = ratings.fit(data.load(), asof=forecast.ASOF)
fx = forecast.fixtures()
demo = next(f for f in fx if f["home"] == "Brazil")
pred = forecast.predict(s, demo)
print(f"{pred['home']} vs {pred['away']} @ {pred['venue']}")
print(f"  1X2: {pred['p_home']:.0%} / {pred['p_draw']:.0%} / {pred['p_away']:.0%}"
      f"  | xG {pred['exp_home']}–{pred['exp_away']}")
print("  most likely:", [f"{t['h']}-{t['a']} ({t['p']:.0%})" for t in pred["top_scores"]])

# %% [markdown]
# ## 2. Pull the actual results
#
# openfootball's public-domain feed marks played matches with a full-time score. We key by
# the unordered team pair, so home/away orientation in the feed never matters.

# %%
results = forecast.fetch_results()
print(f"{len(results)} matches played so far")

# %% [markdown]
# ## 3. Mark the homework
#
# For every played match: did the model call the right result, how many exact scorelines did
# it nail, and does it beat a 33/33/33 coin-flip on Brier and log-loss? Early on this is
# noise — an opening round of upsets will sink any model — so the metrics travel with their N.

# %%
preds = [forecast.predict(s, f) for f in fx]
sc = forecast.score(preds, results)
print(f"results called right : {sc['n_correct']}/{sc['n_played']} ({sc['pct_correct']:.0%})")
print(f"exact scorelines     : {sc['n_exact']}")
print(f"Brier   model {sc['brier_model']}  vs coin-flip {sc['brier_uniform']}")
print(f"log-loss model {sc['logloss_model']} vs coin-flip {sc['logloss_uniform']}")

# %%
pd.DataFrame(sc["log"])[["date", "home", "away", "pred", "actual", "correct"]].head(14)

# %% [markdown]
# ## 4. Emit the bundle
#
# One static `site/data/forecast.json`: per-fixture predictions (1X2, xG, top scores, a 0–5
# score grid), the running scorecard, the reliability bins and the prediction log. The page
# re-runs this through the tournament; no compute in the browser.

# %%
out = forecast.export()
m, scd = out["meta"], out["scorecard"]
print(f"written site/data/forecast.json: {m['n_fixtures']} fixtures (frozen {m['asof']}), "
      f"{scd['n_played']} graded")
