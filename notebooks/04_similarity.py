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
# # Player Similarity Engine — who plays like whom at the 2026 World Cup
#
# Give the model a player and it answers a simple question: *who else plays like
# this?* Under the hood, every coverable squad player gets a per-90 statistical
# fingerprint from FBref; we partition by position, standardise within each group,
# and measure likeness as **cosine similarity in that standardised feature space**.
#
# Three honest-engineering decisions define the piece — each narrated below:
#
# 1. **The coverage gap is surfaced, not hidden.** Features come from FBref's Big-5
#    European leagues only; World Cup players who spent 2024-25 elsewhere are
#    *flagged*, never silently dropped.
# 2. **Positions come first.** Keepers, defenders, midfielders and forwards live in
#    separate spaces. A goalkeeper must never sit next to a winger.
# 3. **The map is for navigation; the maths lives in full dimensionality.** UMAP
#    gives a 2D layout, but similarity scores are computed in the original ~28-dim
#    standardised space — *not* from distance on the map.
#
# Logic lives in `mlfootball/similarity.py`; this notebook narrates it and emits the
# single static `site/data/similarity.json` the web app renders.

# %%
from pathlib import Path
import numpy as np
import pandas as pd
from mlfootball import similarity as S

feat = S.build_feature_frame()
print(f"FBref Big-5 {S.SEASON_LABEL}: {len(feat)} player rows across {feat['Comp'].nunique()} leagues")
print("position groups:", feat["pos_group"].value_counts().to_dict())

# %% [markdown]
# ## 1 · The join, and the coverage gap we refuse to hide
#
# The squad list (1,246 players from the Wikipedia 2026 tables) is matched to FBref
# rows by folded name. A WC player who played 2024-25 in the Saudi Pro League, MLS,
# Liga MX, the Eredivisie, the Championship or Liga Portugal has **no Big-5 vector**
# — we record them as *flagged*, with a reason, and never plot them.

# %%
allp = S.squads.load_players()
out_players = [p for p in allp if S._grp(p["pos"]) != "GK"]
matched, flagged = S.join_squads(feat, out_players)
print(f"outfield matched: {len(matched)} / {len(out_players)}")
print(f"flagged (outside Big-5 in {S.SEASON_LABEL}): {len(flagged)}")
print("\nexample flagged players (covered nowhere we can measure):")
for f in flagged[:6]:
    print(f"  {f['name']:22} {f['nation']:14} {f['club']}  →  {f['reason']}")

# %% [markdown]
# This is the kind of gap a less honest piece would paper over. ~36% coverage is a
# real number; the front end shows the flagged players as faint, un-plottable
# outlines so the reader *sees* who the map can and cannot speak for.

# %% [markdown]
# ## 2 · Per-90 fingerprints, standardised *within* position
#
# Counting stats are divided by 90s played; rates are kept as-is. We then z-score
# **within each position group** — so a centre-back is judged against centre-backs,
# not against forwards. Same 28-feature vocabulary everywhere; standardising within
# the group is what makes sub-archetypes (a ball-playing CB vs a stopper) separate.

# %%
print(f"{len(S.OUTFIELD_FEATURES)} outfield features:")
print("  " + ", ".join(S.FEATURE_LABELS[f] for f in S.OUTFIELD_FEATURES))

# %% [markdown]
# ## 3 · Why similarity uses the original space, not the map
#
# UMAP is a *non-linear projection*: it preserves neighbourhoods but distorts global
# distances, and its axes carry no units. Reading "similarity" off the 2D map would
# be measuring the projection's artefacts. So we compute cosine similarity on the
# full standardised vectors and keep the map purely for navigation. To make the
# point visible, the methods aside contrasts the UMAP layout against a linear PCA
# one — we ship both sets of coordinates.

# %%
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity

mf = matched[matched["pos_group"] == "MF"].reset_index(drop=True)
X = mf[S.OUTFIELD_FEATURES].to_numpy(dtype=float, copy=True)
X[np.isnan(X)] = np.take(np.nanmedian(X, axis=0), np.where(np.isnan(X))[1])
Z = StandardScaler().fit_transform(X)
sim = cosine_similarity(Z)
np.fill_diagonal(sim, -1)
i = int(mf.index[mf["wc_name"] == "Jude Bellingham"][0])
print("Closest stylistic comps for Jude Bellingham (cosine in 28-dim z-space):")
for j in np.argsort(sim[i])[::-1][:6]:
    print(f"  {sim[i, j] * 100:4.1f}%  {mf.at[j, 'wc_name']:22} {mf.at[j, 'nation']}")

# %% [markdown]
# Musiala, Olmo, Güler, Wirtz — fellow young creators. The number is honest cosine,
# not an inflated headline figure; the radar and the "what drives the similarity"
# strip in the app carry the rest of the story.

# %% [markdown]
# ## 4 · Archetypes — labelling the landscape
#
# K-means on the standardised vectors finds clusters; each cluster centroid is
# scored against a small library of archetype signatures (e.g. *Stoppers* =
# high clearances + aerials; *Ball-playing CBs* = high progressive passing) and
# given the best-matching, unique label. The map's hulls turn the scatter into a
# readable landscape rather than a blob.

# %%
data = S.build_export()
for g, ex in data["positions"].items():
    print(f"\n{g} — {len(ex['players'])} players")
    for c in ex["clusters"]:
        print(f"  [{c['n']:3}] {c['label']:24} {c['blurb']}")

# %% [markdown]
# ## 5 · Export for the web app
#
# Everything the browser needs, precomputed: per-player coordinates (UMAP + PCA),
# percentile vectors, top-10 cosine neighbours, archetype clusters with hulls, the
# featured heroes, the editorial tours, and the flagged-coverage list. No runtime ML.

# %%
data = S.write_export()
m = data["meta"]
dest = Path(S.__file__).resolve().parent.parent / "site" / "data" / "similarity.json"
print(f"wrote {dest.name} ({dest.stat().st_size / 1024:.0f} KB)")
print(f"coverage: {m['n_matched']}/{m['n_squad_players']} ({m['coverage_pct']}%) matched · "
      f"{m['n_flagged']} flagged · season {m['season']}")
print("featured heroes:", data["featured"])
print("tours:", [t["title"] for t in data["tours"]])
