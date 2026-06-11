# Machine Learning in Football — Explorations

A growing set of small, self-contained football data explorations — each one a single question,
taken as far as the data honestly goes. Static HTML, charts hand-drawn in D3, **no build step and no
live API**. Open `index.html` (or serve the folder) and start anywhere.

## Pieces

| # | Piece | What it is |
|---|-------|-----------|
| 01 | **Network** | The shape of the football world as a graph — six blocs, a small world two matches wide. |
| 03 | **Travel Burden** | The 2026 Travel Burden Index — drag the weights, watch the ranking re-sort. |
| 04 | **Club & Country** | A Sankey of where 1,246 squad players earn their living, with the entity-resolution behind it. |
| 05 | **Player Similarity** | A per-90 style fingerprint for every coverable player; meet anyone's five closest matches. |
| 06 | **Penalty Geometry & Game Theory** | Where shooters aim, where keepers go, and whether anyone is playing Nash — KDE placement maps, a mixed-strategy equilibrium test, and a playable keeper game, on StatsBomb open data. |

## Run it

```bash
python3 -m http.server 8000   # then open http://localhost:8000
```

Pieces 01 & 06 are hand-written D3 (`js/charts.js`, `js/penalties.js`); 03–05 are built static apps
under `pieces/`. Data lives in `data/*.json`. Analysis notebooks and the data pipelines live in the
companion source repos.
