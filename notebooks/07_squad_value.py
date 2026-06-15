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
# # The price of a starting XI
#
# `squads.py` already knows *who* is in every 2026 World Cup squad (name / club / position,
# parsed from Wikipedia). The only thing missing for a strength view is the price tag. This
# notebook adds it from Transfermarkt — the de-facto crowd-sourced market value — and turns
# the result into a fixtures hub: every group game as a value mismatch you can open into two
# starting elevens.
#
# The interesting work is **entity resolution and honest coverage**, not the scrape:
#
# 1. **Resolving national-team ids** without a usable search endpoint (TM 502s on search /
#    competition pages from here) — harvested instead from the one reliable aggregation page,
#    the FIFA world ranking.
# 2. **Matching Wikipedia names to Transfermarkt names** across accents, captain markup, and
#    *swapped name order* (Korean "Son Heung-min" vs TM "Heung-min Son").
# 3. **Saying what we can't price** — coverage is reported, unmatched players shown as
#    unvalued rather than guessed.

# %%
from mlfootball import squad_value as sv, squads

# %% [markdown]
# ## 1. Resolve the 48 national-team Transfermarkt ids
#
# One reliable page (the FIFA ranking) lists every national team as
# `title="England" href="/england/.../verein/3299"`. We match its English names to our
# Wikipedia spellings, with a tiny alias map for the four that differ (Türkiye, Czechia,
# Bosnia-Herzegovina, DR Congo). Cached to `data/tm_cache/nation_ids.json`.

# %%
ids = sv.discover_ids()
print(f"resolved {len(ids)}/48 national teams")
print("e.g.", {k: ids[k] for k in ["Brazil", "England", "South Korea", "Turkey"]})

# %% [markdown]
# ## 2. Scrape + parse one squad page
#
# Each national-team squad page yields `{tm_id: {name, value_eur}}`. The market value links
# via `/marktwertverlauf/spieler/{id}`; the name comes from the profile anchor's text, its
# title, or — for captains, whose name hides behind a `<span title="Team captain">` — the
# portrait image title. Missing that last fallback is what dropped Mbappé on the first pass.

# %%
fr = sv.parse_squad(sv.fetch(sv.squad_url(*ids["France"])))
top = sorted(fr.values(), key=lambda v: -(v["value_eur"] or 0))[:5]
for v in top:
    print(f"  {v['name']:22} €{v['value_eur'] / 1e6:.0f}m")

# %% [markdown]
# ## 3. Match to the squad and value every nation
#
# Names are folded (lowercased, accent-stripped) and matched exact → order-independent
# token-set → last-name+initial. Token-set is what bridges the Korean name-order swap.

# %%
nations = sv.value_nations()
covered = sum(n["n_valued"] for n in nations.values())
total = sum(n["n_players"] for n in nations.values())
print(f"matched {covered}/{total} players ({covered / total:.1%})")
worst = sorted(nations.items(), key=lambda kv: kv[1]["n_valued"] / kv[1]["n_players"])[:3]
print("lowest coverage:", [(k, f"{v['n_valued']}/{v['n_players']}") for k, v in worst])

# %% [markdown]
# ## 4. The value ladder
#
# Total squad value, richest first. These totals reproduce Transfermarkt's published
# squad-value ranking (France ≈ €1.52bn, England ≈ €1.36bn, Spain ≈ €1.22bn) — a good
# external check that the matching is sound.

# %%
rank = sorted(nations.items(), key=lambda kv: -kv[1]["squad_value"])
for nat, v in rank[:8]:
    print(f"  {nat:14} squad €{v['squad_value'] / 1e6:>5.0f}m   best XI €{v['xi_value'] / 1e6:>5.0f}m")

# %% [markdown]
# ## 5. Emit the bundle
#
# One static `site/data/squad_value.json`: meta + coverage, the ranking, every nation's
# squad (players, values, best-XI flags) and the 72 group fixtures annotated with each
# side's best-XI worth. No runtime compute on the page.

# %%
out = sv.export()
m = out["meta"]
print(f"written site/data/squad_value.json: {m['n_valued']}/{m['n_players']} "
      f"players priced ({m['coverage']:.1%}), {len(out['fixtures'])} fixtures")
