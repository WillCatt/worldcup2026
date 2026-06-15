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
# # Penalties as a game of mixed strategies
#
# A penalty kick is the cleanest natural experiment in football: a one-shot, two-player,
# near-simultaneous game. The shooter picks a side, the keeper picks a side, and a goal or
# a save falls out of whether they match. Game theory has used it for decades to test
# whether real professionals play mixed-strategy equilibria.
#
# The earlier version of this piece had to **apologise** for its data: StatsBomb open data
# only records which way a keeper dived when the dive ended in a save, so the keeper's choice
# was unobservable on ~3/4 of kicks. This rebuild uses a World Cup-specific corpus that
# records the keeper's dive on **every** kick — so we can finally play out the whole game.
#
# Source: every men's World Cup shootout kick 1982→2022 (`data/raw/WorldCupShootouts.csv`).
# Both the shot `Zone` (1–9 grid) and the `Keeper` dive (L/C/R) are coded from the shooter's
# view of the goal, so "did the keeper read the side" is a direct comparison.

# %%
import pandas as pd

from mlfootball import penalties as pen

pd.set_option("display.width", 110)

df = pen.load_kicks()
print(f"{len(df)} clean kicks across {df.Game_id.nunique()} shootouts; "
      f"overall conversion {df.Goal.mean():.1%}")
df.head()

# %% [markdown]
# ## 1. The keeper's coin flip
#
# Keepers commit before the ball is struck. Across these shootouts they read the correct
# side under half the time — and reading it right only turns a near-certain goal into a
# coin flip, it does not make the save automatic.

# %%
cf = pen.coin_flip(df)
print(f"keeper reads correct side : {cf['keeper_correct_rate']:.1%}")
print(f"conversion | keeper WRONG  : {cf['conv_when_wrong']:.1%}  (n={cf['n_wrong']})")
print(f"conversion | keeper RIGHT  : {cf['conv_when_right']:.1%}  (n={cf['n_right']})")
print(f"keeper dive distribution   : {cf['keeper_dive_dist']}")

# %% [markdown]
# ## 2. The payoff matrix
#
# The whole game on one grid: rows = where the ball went, columns = where the keeper dived,
# each cell = conversion. The diagonal (keeper reads the side) is where saves live; step one
# cell off it and the penalty is all but in.

# %%
mx = pen.payoff_matrix(df)
print(pd.crosstab(df.ShotDir, df.Keeper, values=df.Goal, aggfunc="mean").round(2))
print("\ncell counts:")
print(pd.crosstab(df.ShotDir, df.Keeper))

# %% [markdown]
# ## 3. Is anyone playing Nash?
#
# The clean game-theory prediction: at a mixed-strategy equilibrium every option a taker
# uses must pay the same, otherwise they would shift toward the better one. So is conversion
# flat across left / centre / right? A high χ² p-value here is a *null worth printing* — it
# is exactly what equilibrium play looks like. Unlike the open-data version, this read no
# longer leans on the shooter alone: the keeper's real dive is in every cell above.

# %%
nash = pen.nash_indifference(df)
for b in nash["by_dir"]:
    print(f"  {b['dir']}: conv {b['conv']:.1%}  used {b['usage']:.1%}  "
          f"95% CI [{b['lo']:.1%}, {b['hi']:.1%}]  (n={b['n']})")
print(f"\n  chi-square goal~side: chi2={nash['chisq']['chi2']}, p={nash['chisq']['p']}, "
      f"spread={nash['spread_pp']} pts")

# %% [markdown]
# ## 4. The abandoned centre
#
# Keepers almost always dive — they hold the middle on barely a tenth of kicks — so a ball
# hit straight down the centre usually meets thin air where the keeper just left. The
# panenka is a read, not a flourish. (The "keeper stays central" cell is small-n, so treat
# its conversion as a warning, not a precise rate.)

# %%
c = pen.abandoned_centre(df)
print(f"keeper stays central     : {c['keeper_stays_centre']:.1%}")
print(f"shooter aims centre      : {c['shooter_centre_usage']:.1%}")
print(f"centre vs committed keeper: {c['centre_vs_committed_conv']:.1%} (n={c['centre_vs_committed_n']})")
print(f"centre vs centred keeper  : {c['centre_vs_centre_conv']:.1%} (n={c['centre_vs_centre_n']})")

# %% [markdown]
# ## 5. Footedness — the one tell left
#
# A right-footer striking across the ball favours the viewer-left; left-footers mirror it.
# It is the one place a keeper who knows the taker's stronger foot starts a half-step ahead.

# %%
print(pd.DataFrame({f["foot"]: f["dist"] for f in pen.footedness(df)["by_foot"]}).T)

# %% [markdown]
# ## 6. The pressure cooker — honest nulls
#
# Conversion by the taker's order number, and the must-score elimination kicks. If pressure
# bites it should show here; it largely doesn't. The confound to keep in mind: kick order is
# manager-chosen, so order effects and taker quality are entangled.

# %%
pr = pen.pressure(df)
for k in pr["by_kick"]:
    print(f"  kick {k['num']:>2}: {k['conv']:.1%}  (n={k['n']})")
el = pr["elimination"]
print(f"\n  must-score elimination : {el['must_conv']:.1%} (n={el['must_n']})")
print(f"  everything else        : {el['rest_conv']:.1%} (n={el['rest_n']})")

# %% [markdown]
# ## Emit the bundle
#
# Everything the page needs is one static `site/data/penalties.json` — no runtime compute.

# %%
out = pen.export()
print("written site/data/penalties.json:",
      f"{out['meta']['n_clean']} kicks, Nash p={out['nash']['chisq']['p']}, "
      f"keeper correct {out['coin_flip']['keeper_correct_rate']:.1%}")
