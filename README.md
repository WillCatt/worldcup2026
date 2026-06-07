# The shape of the football world

A network analysis of 150 years of international football. Treat every nation as a **node**
and every match as an **edge**, then read the structure of the resulting graph. The headline:
**the world barely plays itself** — ~86% of games stay within a team's own confederation — and
that sparse cross-continental connectivity is *why* ranking national teams (and seeding a
48-team World Cup) is genuinely hard.

The deliverable is a standalone interactive page (`site/`) driven by a small (~11 KB)
confederation-level export. No live API, no scoreboard — the structure is the story.

## The five parts

1. **Six blocs, barely touching** — a confederation **chord** diagram, a 6×6 **flow matrix**,
   and an **insularity** ranking. Louvain community detection (blind to geography) recovers the
   confederations at NMI 0.96 — but finds *five* blocs, not six: CONMEBOL and CONCACAF fuse
   into one "Americas" community.
2. **Is the world coming together?** — cross-continental match share by year since 1930.
   Intercontinental play climbed for a century to an **18% peak in the 1990s**, then **retreated
   to ~12%** as confederations built out their own packed calendars.
3. **Two degrees of football** — small-world metrics: average shortest path **1.89**, diameter
   4, clustering 0.60 vs 0.23 for a random graph. ~88% of all team-pairs are within two matches.
   Includes an interactive widget that BFS-walks the real match-chain between any two nations.
4. **Who really holds it together** — **betweenness** centrality finds the true structural
   brokers (Mexico, Qatar, Ghana, the Central American sides), which are *not* the teams that
   merely travel most (cross-share). By **eigenvector** centrality the dense core of world
   football is the **Americas**, not Europe.
5. **Structure at every scale** — turn up the community-detection resolution and the six
   confederations fracture into recognizable sub-regions (Western Europe, the Caribbean, the
   Gulf, two African halves…) — the world is structured all the way down.

## Architecture

```
worldcup2026/
├── data/
│   ├── results.csv            # match history (auto-downloaded, gitignored)
│   └── confederations.json    # 217 national teams → confederation (hand-mapped)
├── mlfootball/                # pip-installed editable analysis package
│   ├── data.py                # download / load the results history
│   ├── network.py             # graph build + structure, communities, centrality,
│   │                          #   small-world, nested partition, exports
│   └── temporal.py            # cross-confederation share over time
├── notebooks/
│   └── 01_network.py          # jupytext percent-format notebook: narrates all five
│                              #   parts and writes the site's data exports
└── site/                      # standalone interactive page
    ├── index.html
    ├── css/style.css
    ├── js/charts.js           # D3: chord, matrix, bars, temporal, small-world,
    │                          #   connector (in-browser BFS), scatter, sunburst
    └── data/
        ├── network.json         # ~11 KB aggregate the charts read
        └── graph_adjacency.json # compact adjacency for the connector widget
```

## Data source

[martj42/international_results](https://github.com/martj42/international_results) — every men's
international, 1872→present (`results.csv`). No auth; raw GitHub fetch via `mlfootball/data.py`.

## Run

```bash
pip install -e .                      # editable install of the mlfootball package

# Reproduce the analysis + regenerate the site's data exports.
# (PYTHONPATH is needed because this Python 3.14 venv ignores the editable .pth.)
PYTHONPATH="$(pwd)" python -m jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.kernel_name=python3 notebooks/01_network.ipynb

# Serve the page.
cd site && python3 -m http.server      # → http://localhost:8000
```

## Status

Standalone build on branch `network-redesign`. Moves into the portfolio site
(`williamcatt.dev`, house style) once happy.
