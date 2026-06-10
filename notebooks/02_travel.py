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
# # The 2026 Travel Burden Index
#
# Three host countries, sixteen venues, a continent's worth of distance. This
# notebook builds a defensible, from-scratch **burden index** for every team in
# the 2026 World Cup group stage — total kilometres flown, time-zones crossed,
# altitude breathed, and rest denied — then asks the only honest follow-up:
# *does the ranking survive if you reweight the ingredients?*
#
# Data is static (the final-draw schedule + venue coordinates), so there's no
# scraping and nothing to go stale. All logic lives in `mlfootball/travel.py`;
# this notebook narrates it and writes `site/data/travel.json` for the web app.

# %%
import json
from pathlib import Path

from mlfootball import travel as T

print(f"{len(T.VENUES)} venues · {len(T.SCHEDULE)} group-stage matches · "
      f"{sum(len(v) for v in T.GROUPS.values())} teams")

# %% [markdown]
# ## 1 · One team's journey
#
# Start concrete. Czechia drew the cruellest itinerary in the field: a Mexican
# opener at altitude in Guadalajara, a transcontinental hop to Atlanta, then back
# up to 2,200 m in Mexico City.

# %%
cze = T.team_travel("Czechia", "A")
for leg in cze.legs:
    tag = f"  ✈ {leg['leg_km']} km" if leg["leg_km"] else ""
    alt = f"  ({leg['alt']} m)" if leg["alt"] >= T.ALT_THRESHOLD else ""
    print(f"{leg['date']}  {leg['city']:14}{alt:10} vs {leg['opponent']}{tag}")
print(f"\nTotal {cze.total_km} km · {cze.tz_changes} tz-changes · "
      f"{cze.alt_matches} altitude matches · shortest rest {cze.min_rest} d")

# %% [markdown]
# ## 2 · The index
#
# Four sub-burdens, each **z-scored across the 48 teams** so they're comparable,
# then combined as a weighted sum. Recovery enters negatively (less rest = more
# burden). Default weights: distance .35, timezone .25, altitude .25, recovery .15.

# %%
table = T.burden_table()
print(f"{'#':>2}  {'Team':14} {'Grp':3} {'km':>5} {'tz':>2} {'alt':>5} {'rest':>4}  burden")
for r in table[:10]:
    print(f"{r['rank']:>2}  {r['team']:14} {r['group']:3} {r['total_km']:>5} "
          f"{r['tz_changes']:>2} {int(r['altitude_load']):>5} {r['min_rest']:>4}  {r['burden']:+.3f}")
print("...")
for r in table[-3:]:
    print(f"{r['rank']:>2}  {r['team']:14} {r['group']:3} {r['total_km']:>5} "
          f"{r['tz_changes']:>2} {int(r['altitude_load']):>5} {r['min_rest']:>4}  {r['burden']:+.3f}")

# %% [markdown]
# ## 3 · Who got screwed by the draw?
#
# Average the burden over each group's four teams.

# %%
for r in T.group_burden():
    bar = "█" * int(max(0, r["mean_burden"]) * 20)
    print(f"Group {r['group']}  {r['mean_burden']:+.2f}  {bar}")

# %% [markdown]
# ## 4 · Sensitivity — is the ranking real or an artefact of the weights?
#
# Re-run the index under five very different weightings and measure Kendall's τ
# against the default ordering. High τ = the ranking is a property of the
# schedule, not of our weight choices.

# %%
sens = T.sensitivity()
print(f"mean τ vs default: {sens['mean_tau']}\n")
for sc in sens["scenarios"]:
    print(f"  {sc['scenario']:16} τ = {sc['tau']:+.3f}")
print("\nMost weight-robust teams (smallest rank spread across scenarios):")
for s in sorted(sens["stability"], key=lambda x: x["spread"])[:5]:
    print(f"  {s['team']:14} rank {s['best']}–{s['worst']}")

# %% [markdown]
# The index is robust to reweighting **distance, altitude and timezone** (τ ≈ 0.8–0.9)
# but wobbles under *recovery_heavy* — group-stage rest days barely vary, so leaning
# on them adds noise. That's a finding, not a flaw: the burden ranking is driven by
# geography, and rest is a weak signal until the knockouts compress the calendar.

# %% [markdown]
# ## 5 · Does travel actually hurt? A historical reality check
#
# The index *measures* travel; it doesn't prove travel *matters*. So we test the
# thesis on three past World Cups with real travel variance — South Africa 2010,
# Brazil 2014, Russia 2018 — regressing each team's group-stage points on its
# pre-tournament **Elo** (strength, built from the full match history) and its
# within-tournament-standardized travel. Logic in `mlfootball/historical.py`.

# %%
from mlfootball import historical as H

reg = H.regression()
print(f"N = {reg['n']} team-campaigns · pooled R² = {reg['r2']}")
print(f"raw travel↔points correlation (uncontrolled): {reg['raw_travel_points_corr']}\n")
for name, c in reg["coef"].items():
    print(f"  {name:10} β={c['beta']:+.3f}  t={c['t']:+.2f}  p={c['p']:.3f}")

# %% [markdown]
# **The verdict.** Strength (Elo) is overwhelmingly the story — but *holding strength
# constant*, a standard deviation of extra group-stage travel costs about a third of
# a point (β ≈ −0.36, p ≈ 0.10). Directionally real, modest, and noisy: travel is a
# genuine headwind, not a death sentence. That honest "small but present" is exactly
# how much weight the 2026 burden ranking deserves.

# %% [markdown]
# ## 6 · Export for the web app

# %%
hist = {
    "n": reg["n"], "tournaments": reg["tournaments"], "r2": reg["r2"],
    "raw_corr": reg["raw_travel_points_corr"],
    "travel": reg["coef"]["travel_z"], "elo": reg["coef"]["elo_z"],
    "extremes": sorted(reg["panel"], key=lambda x: -x["travel_km"])[:5],
}
out = {
    "generated_note": "2026 WC group-stage travel burden. Static schedule + venue data.",
    "weights": T.DEFAULT_WEIGHTS,
    "alt_threshold": T.ALT_THRESHOLD,
    "venues": T.VENUES,
    "groups": T.GROUPS,
    "teams": table,
    "group_burden": T.group_burden(),
    "sensitivity": sens,
    "history": hist,
}
dest = Path("site/data/travel.json")
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(out, ensure_ascii=False))
print(f"wrote {dest} ({dest.stat().st_size/1024:.1f} KB)")
