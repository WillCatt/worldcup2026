# %% [markdown]
# # 01 · The shape of the football world
#
# Treat every nation as a **node** and every match as an **edge**, and read 150 years of
# results as a single graph. This notebook is the analysis behind the interactive page; it
# quantifies five things and exports a small (~11 KB) confederation-level payload the D3
# charts render.
#
# **Thesis.** National teams overwhelmingly play *within* their own confederation, so the
# match graph is clustered by continent with only thin "bridge" games linking the blocs.
# That sparse cross-continental connectivity is *why* ranking across confederations — and
# seeding a 48-team World Cup — is genuinely hard.
#
# The five lenses: **(I)** the bloc structure, **(II)** how it has changed over time,
# **(III)** how small-world the graph is, **(IV)** who structurally holds it together, and
# **(V)** the nested sub-regions hiding inside the confederations.

# %%
import json
from pathlib import Path

import numpy as np
import pandas as pd

from mlfootball import data, network as net, temporal

pd.set_option("display.max_rows", 20)

df = data.load()
conf = net.load_confederations()
print(f"{len(df):,} internationals, {df.date.min().date()} → {df.date.max().date()}")

# The undirected "who-plays-whom" graph: modern window + iterative min-matches filter.
Gu = net.build_undirected(df)
print(f"Graph: {Gu.number_of_nodes()} teams, {Gu.number_of_edges()} edges")

# %% [markdown]
# ## Part I — Six blocs, barely touching
#
# What share of games stay *within* a confederation, and how inward-looking is each bloc?

# %%
rep = net.connectivity_report(Gu)
print(f"WITHIN-confederation: {rep['within_share']:.1%}")
print(f"CROSS-confederation:  {rep['cross_share']:.1%}\n")
pd.Series(rep["insularity"], name="insularity").sort_values(ascending=False).map("{:.1%}".format)

# %% [markdown]
# ~86% of games never cross a continent. The 6×6 flow matrix makes the whole picture exact —
# the diagonal (games kept at home) dominates every row, and the one fat off-diagonal cell is
# CONMEBOL↔CONCACAF.

# %%
M = net.flow_matrix(Gu)
share = M / M.sum(axis=1, keepdims=True)
pd.DataFrame((share * 100).round(1), index=net.CONF_ORDER, columns=net.CONF_ORDER)

# %% [markdown]
# Run Louvain community detection (it knows nothing of geography) and it recovers the
# confederations almost perfectly — **but five blocs, not six**: CONMEBOL and CONCACAF fuse
# into a single "Americas" community.

# %%
com = net.communities(Gu)
print(f"Louvain communities: {com['n_communities']}  (vs 6 real)   NMI: {com['nmi']:.3f}")

# %% [markdown]
# ## Part II — Is the world coming together?
#
# Of all internationals played each year, what share crossed continents? The answer is a
# rise *and* a retreat.

# %%
tser = temporal.cross_share_over_time(df, conf=conf)
dec = pd.DataFrame(tser["decades"])
dec["cross"] = (dec["cross"] * 100).round(1)
print(dec.to_string(index=False))
print(f"\nPeak: {tser['peak']['decade']}s at {tser['peak']['cross']:.0%}  →  "
      f"latest: {tser['latest']['decade']}s at {tser['latest']['cross']:.0%}")

# %% [markdown]
# Intercontinental play climbed for a century to an **18% peak in the 1990s**, then fell back
# to ~12% — as confederations built out their own packed calendars (continental Nations
# Leagues, more regional qualifiers), friendlies abroad got crowded out.

# %% [markdown]
# ## Part III — Two degrees of football
#
# For all the silos, is the graph a *small world* — short paths, tight clustering?

# %%
sw = net.smallworld_stats(Gu)
print(f"avg shortest path: {sw['avg_path']}   diameter: {sw['diameter']}")
print(f"clustering: {sw['clustering']}  (random graph of same size: {sw['rand_clustering']})")
print("path-length distribution:",
      {d["hops"]: f"{d['share']:.0%}" for d in sw["distribution"]})
print("example chain · Vanuatu → San Marino:", net.shortest_chain(Gu, "Vanuatu", "San Marino"))

# %% [markdown]
# Any two national teams are on average **1.9 matches** apart and at most **4**; ~88% of all
# pairs are within two. High clustering (0.60 vs 0.23 random) with short paths is the textbook
# small-world signature.

# %% [markdown]
# ## Part IV — Who really holds it together?
#
# Cross-share asks who *travels* most. **Betweenness** asks who sits on the most shortest
# paths between blocs — the brokers the world routes through. They are not the same teams.

# %%
cen = net.centrality_table(Gu)
print("Top betweenness (true structural brokers):")
for r in cen["betweenness"][:8]:
    print(f"  {r['team']:18s} btw={r['score']:.3f}  plays-abroad={r['cross']:.0%}  ({r['conf']})")
print(f"\nSpearman(betweenness, cross-share) = {cen['spearman_btw_cross']:.2f}  → they only partly agree")
print("Eigenvector core (densely embedded):", ", ".join(r["team"] for r in cen["eigenvector"][:6]))

# %% [markdown]
# Mexico brokers *and* travels, but Qatar, Ghana and the Central American sides are
# high-leverage brokers despite modest travel. And the densely-connected **core** of world
# football, by eigenvector centrality, is the **Americas** — not Europe — because intra-
# American play is so dense.

# %% [markdown]
# ## Part V — Structure at every scale
#
# Turn up the community-detection resolution and the six confederations fracture into
# recognizable sub-regions — the world is structured all the way down.

# %%
print("resolution sweep (γ → communities):",
      {r["gamma"]: r["n_communities"] for r in net.resolution_sweep(Gu)})
print("\nfine-grained sub-regions (γ=3.0):")
for s in net.nested_partition(Gu):
    print(f"  {s['label']:28s} ({s['size']:2d}, mostly {s['conf']})")

# %% [markdown]
# ## Part VI — Robust world, heavy bridges
#
# If a few brokers hold the continents together, how fragile is that? Remove teams worst-first
# by betweenness and watch the cross-continental links — against random removal of the same count.

# %%
rob = net.robustness(Gu)
print(f"removing the top 10 brokers strips {rob['top10_link_loss']:.0%} of all cross-continental links")
print(f"largest connected component never drops below {rob['lcc_min']:.0%} of teams (it never splits)")
print(f"cross-continental reachability after {rob['kmax']} removals: {rob['reach_retained_kmax']:.0%} retained")
print("removal order:", ", ".join(rob["order"][:8]))

# %% [markdown]
# Two-sided and honest: the bridges carry a *wildly* disproportionate load — the top 10 brokers
# account for a quarter of all cross-continental links, and targeted removal strips them about
# twice as fast as random. **And yet** the graph never disconnects: every confederation stays
# reachable, reachability barely moves. World connectivity is resilient — no single point of
# failure — even though a thin elite carries most of the inter-continental traffic.

# %% [markdown]
# ## Export for the interactive page
#
# One small `network.json` (structure + temporal + small-world + centrality + nested) plus a
# compact `graph_adjacency.json` the in-browser "connect any two nations" widget BFS-walks.

# %%
export = net.to_aggregate_export(Gu)
export["temporal"] = tser

site = net.DATA_DIR.parent / "site" / "data"
site.mkdir(parents=True, exist_ok=True)
(site / "network.json").write_text(json.dumps(export, separators=(",", ":")))
(site / "graph_adjacency.json").write_text(json.dumps(net.adjacency_export(Gu), separators=(",", ":")))

print(f"network.json       {(site / 'network.json').stat().st_size/1024:.1f} KB")
print(f"graph_adjacency.json {(site / 'graph_adjacency.json').stat().st_size/1024:.1f} KB")
