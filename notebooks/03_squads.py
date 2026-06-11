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
# # Club & Country — the league dependency map
#
# Where does each 2026 World Cup squad actually earn its living? This notebook
# maps every one of the 1,246 players to the club — and league/country — they
# play for, then turns that into flows (nation → league) and a **domestic
# dependency** stat per team.
#
# The modelling is light; the **data engineering** is the point. The same club
# appears as "Manchester City F.C.", "FC Bayern Munich", "Al Hilal SFC" — messy,
# inconsistent entities that have to be reconciled before a single number is
# trustworthy. Logic lives in `mlfootball/squads.py`; source is the Wikipedia
# 2026 squad tables (raw wikitext, parsed — no scraping).

# %%
from pathlib import Path
import json
from mlfootball import squads as S

players = S.load_players()
print(f"{len(players)} players · {len(set(p['nation'] for p in players))} nations · "
      f"{len(set(p['code'] for p in players))} club-countries")

# %% [markdown]
# ## 1 · Entity resolution — cleaning the clubs
#
# Raw club strings carry club-form noise (F.C./FC/AFC/SC/CF/AS/SSC…). We peel it
# off to land on clean, consistent labels — the difference between one node and
# three for the same club.

# %%
for ex in ["Manchester City F.C.", "FC Bayern Munich", "Paris Saint-Germain FC",
           "Al Hilal SFC", "AS Monaco", "SSC Napoli", "TSG 1899 Hoffenheim"]:
    print(f"  {ex:24} → {S.normalize_club(ex)}")
print(f"\n{len(set(p['club_raw'] for p in players))} raw club strings → "
      f"{len(set(p['club'] for p in players))} normalised clubs")

# %% [markdown]
# ## 2 · Domestic dependency — who plays at home?
#
# Share of each squad employed in its own country's league.

# %%
nb = S.nation_breakdowns(players)
print("Most home-based:")
for r in nb[:5]:
    print(f"  {r['nation']:14} {r['domestic_pct']:5}%  ({r['domestic']}/{r['n_players']})")
print("\nMost exported (spread across the most leagues):")
for r in sorted(nb, key=lambda x: -x["n_leagues"])[:5]:
    print(f"  {r['nation']:14} {r['domestic_pct']:5}% domestic · {r['n_leagues']} leagues")

# %% [markdown]
# Two clean poles: the Gulf hosts (**Qatar, Saudi Arabia ~96%**) keep their squads
# home, and **England (~81%)** sits in the Premier League's gravity well — while
# diaspora and smaller nations (**Panama, Bosnia, Haiti**) scatter across 15+
# leagues with almost nobody playing at home.

# %% [markdown]
# ## 3 · The flows — nation → league

# %%
sk = S.sankey_league(players)
print(f"league Sankey: {len(sk['nodes'])} nodes, {len(sk['links'])} links")
print("destination leagues:", ", ".join(sk["leagues"]))
print("\nbiggest leagues by World Cup players:")
for lg in S.league_leaderboard(players)[:8]:
    print(f"  {lg['league']:22} {lg['count']}")

# %% [markdown]
# ## 4 · Export for the web app

# %%
# Ship the per-nation breakdowns (the source of truth) + the league ranking; the
# web app builds both the league- and club-level Sankeys from these client-side.
out = {
    "n_players": len(players),
    "nations": nb,
    "league_leaderboard": S.league_leaderboard(players),
}
dest = Path(S.__file__).resolve().parent.parent / "site" / "data" / "squads.json"
dest.write_text(json.dumps(out, ensure_ascii=False))
print(f"wrote {dest} ({dest.stat().st_size/1024:.1f} KB)")
