# %% [markdown]
# # 01 · The international football network
#
# A different lens on 150 years of results: treat every nation as a **node** and every
# match as an **edge**, and ask what the *shape* of that graph says about how hard it is
# to rank national teams.
#
# **Thesis.** National teams overwhelmingly play *within* their own confederation, so the
# match graph is clustered by continent with only thin "bridge" games linking the blocs.
# That sparse cross-continental connectivity is *why* ranking across confederations — and
# seeding a 48-team World Cup — is genuinely hard.
#
# This notebook builds the graph, quantifies the structure, and exports
# `site/data/network.json` for the interactive D3 page. It's the analysis; the page is the
# showroom.

# %%
import json

import pandas as pd

from mlfootball import data, network as net

pd.set_option("display.max_rows", 20)

df = data.load()
print(f"{len(df):,} internationals, {df.date.min().date()} → {df.date.max().date()}")

# %%
# Build both graphs: undirected "who-plays-whom" (structure) and directed "beat-graph"
# (ranking). Restricted to the modern era with an iterative min-matches filter.
Gu = net.build_undirected(df)
Gd = net.build_directed(df)
print(f"Graph: {Gu.number_of_nodes()} teams, {Gu.number_of_edges()} edges")

# %% [markdown]
# ## Finding 1 — national teams almost never leave home
#
# The single most important number: what share of games stay *within* a confederation?

# %%
rep = net.connectivity_report(Gu)
print(f"WITHIN-confederation: {rep['within_share']:.1%}")
print(f"CROSS-confederation:  {rep['cross_share']:.1%}\n")
pd.Series(rep["insularity"], name="insularity").sort_values(ascending=False).map("{:.1%}".format)

# %% [markdown]
# ~86% of games never cross a continent. Big self-sufficient blocs (CAF, UEFA) barely look
# outward; CONMEBOL — just ten teams — is forced to. This is the structural reason the
# forecast is least certain about cross-continental match-ups: the evidence linking them is thin.

# %% [markdown]
# ## Finding 2 — the continents draw themselves
#
# Can an algorithm that knows nothing about geography recover the confederations from match
# patterns alone? Run Louvain community detection and compare to the real partition.

# %%
com = net.communities(Gu)
print(f"Louvain communities: {com['n_communities']}  (vs 6 real confederations)")
print(f"NMI vs confederations: {com['nmi']:.3f}")
print(f"Modularity — confed {com['modularity_confed']:.3f} · Louvain {com['modularity_louvain']:.3f}")

# Which confederations landed in each detected community?
from collections import Counter
conf = {n: Gu.nodes[n]["confederation"] for n in Gu}
comm_of = com["node_comm"]
mix = {}
for n, c in comm_of.items():
    mix.setdefault(c, Counter())[conf[n]] += 1
for c, cnt in sorted(mix.items()):
    print(f"  community {c}: " + ", ".join(f"{k}:{v}" for k, v in cnt.most_common()))

# %% [markdown]
# Almost perfect (NMI 0.96) — but **five blocs, not six**: CONMEBOL and CONCACAF fuse into a
# single "Americas" community. The ten South American sides play North/Central America so often
# (qualifiers, Copa América) that the graph can't separate them.

# %% [markdown]
# ## Finding 3 — a ranking for free, and where it's shaky

# %%
pr = net.pagerank_ranking(Gd)
pr.head(15)

# %% [markdown]
# The graph hands you a power ranking via PageRank on the beat-graph. The teams it's *least*
# sure about are the poorly-connected ones — exactly the teams the global match graph barely
# reaches. Those are the bridge teams that hold the whole ranking together:

# %%
print("Bridge teams (most cross-confederational, well-connected):")
print(", ".join(net.bridge_teams(Gu)))

# %% [markdown]
# ## Export for the D3 page
#
# Ship nodes + links + metrics; the page force-directs the layout in-browser so it stays
# interactive (drag, hover, filter) rather than a baked image.

# %%
export = net.to_graph_export(Gu, Gd)
out_path = net.DATA_DIR.parent / "site" / "data" / "network.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(export, separators=(",", ":")))
print(f"Wrote {out_path.relative_to(net.DATA_DIR.parent)}  "
      f"({len(export['nodes'])} nodes, {len(export['links'])} links, "
      f"{out_path.stat().st_size/1024:.0f} KB)")
