"""Who missed out — the strongest teams not at the 2026 World Cup.

Forty-eight places, and still some heavyweights are watching from home. This pulls the
nations that *didn't* qualify and ranks the strongest of them on four honest signals,
all from data the project already has on disk:

  * FIFA / world ranking position + points   (Transfermarkt's cached world-ranking pages)
  * total squad market value                  (the same pages carry it — €/squad)
  * pre-tournament Elo                         (built over the full martj42 match history)
  * World Cup pedigree                         (a compact hand-checked reference: last
                                                appearance, best finish, titles)

The qualified 48 come from the fixture schedule, so the split is exact. No live API; the
ranking pages are the cache the Squad-Value piece already fetched (30-day TTL).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from mlfootball import historical, squad_value, squads, travel

ROOT = Path(__file__).resolve().parent.parent

# How many of the strongest non-qualifiers to feature (by FIFA rank).
TOP_N = 20

# Flags for non-qualifiers (they aren't in squads.NATION_CODE). Display name -> ISO 3166-1
# alpha-2; Wales uses the 🏴 tag-sequence via squads.flag.
ISO2 = {
    "Italy": "it", "Denmark": "dk", "Nigeria": "ng", "Ukraine": "ua", "Russia": "ru",
    "Poland": "pl", "Hungary": "hu", "Serbia": "rs", "Cameroon": "cm", "Slovakia": "sk",
    "Greece": "gr", "Venezuela": "ve", "Chile": "cl", "Peru": "pe", "Costa Rica": "cr",
    "Romania": "ro", "Mali": "ml", "Republic of Ireland": "ie", "Slovenia": "si",
    "Sweden": "se", "Austria": "at", "Bolivia": "bo", "Iceland": "is", "Finland": "fi",
    "Burkina Faso": "bf", "Guinea": "gn", "Ivory Coast": "ci", "Turkey": "tr",
    "Czech Republic": "cz", "Norway": "no", "Colombia": "co", "Albania": "al",
    "North Macedonia": "mk", "Bulgaria": "bg", "Montenegro": "me", "Israel": "il",
}


def _flag(name: str) -> str:
    if name == "Wales":
        return squads.flag("WAL")
    iso = ISO2.get(name)
    if iso:
        return "".join(chr(0x1F1E6 + ord(c) - ord("a")) for c in iso)
    code = squads.NATION_CODE.get(name, "")
    return squads.flag(code) if code else "🏳️"


# Transfermarkt world-ranking display name -> martj42/model name (only where they differ).
RANK_TO_MODEL = {
    "Türkiye": "Turkey", "Czechia": "Czech Republic",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Korea Republic": "South Korea", "Côte d'Ivoire": "Ivory Coast",
    "IR Iran": "Iran", "Cabo Verde": "Cape Verde",
    "Democratic Republic of the Congo": "DR Congo", "China": "China PR",
}

# World Cup pedigree for the strongest sides that miss out — hand-checked, compact.
# {last_appearance (year or "never"), best ("Winners (Y)"/"Runners-up"/"Quarter-finals"…), titles}
WC_HISTORY = {
    "Italy": {"last": 2014, "best": "Winners ×4", "titles": 4, "note": "4-time world champions — a third straight World Cup missed."},
    "Nigeria": {"last": 2018, "best": "Round of 16", "titles": 0},
    "Sweden": {"last": 2018, "best": "Runners-up (1958)", "titles": 0},
    "Serbia": {"last": 2022, "best": "Group stage (best as Serbia)", "titles": 0},
    "Russia": {"last": 2018, "best": "Fourth (1966, as USSR)", "titles": 0, "note": "Suspended from international football."},
    "Denmark": {"last": 2022, "best": "Quarter-finals (1998)", "titles": 0},
    "Poland": {"last": 2022, "best": "Third ×2 (1974, 1982)", "titles": 0},
    "Wales": {"last": 2022, "best": "Quarter-finals (1958)", "titles": 0},
    "Austria": {"last": 1998, "best": "Third (1954)", "titles": 0},
    "Hungary": {"last": 1986, "best": "Runners-up ×2", "titles": 0},
    "Romania": {"last": 1998, "best": "Quarter-finals (1994)", "titles": 0},
    "Chile": {"last": 2014, "best": "Third (1962)", "titles": 0},
    "Peru": {"last": 2018, "best": "Quarter-finals (1970)", "titles": 0},
    "Cameroon": {"last": 2022, "best": "Quarter-finals (1990)", "titles": 0},
    "Mali": {"last": "never", "best": "Never qualified", "titles": 0},
    "Czech Republic": {"last": 2006, "best": "Runners-up (1962, as Czechoslovakia)", "titles": 0},
    "Ukraine": {"last": 2006, "best": "Quarter-finals (2006)", "titles": 0},
    "Greece": {"last": 2014, "best": "Round of 16 (2014)", "titles": 0},
    "Bolivia": {"last": 1994, "best": "Group stage", "titles": 0},
    "Venezuela": {"last": "never", "best": "Never qualified", "titles": 0},
    "Costa Rica": {"last": 2022, "best": "Quarter-finals (2014)", "titles": 0},
    "Republic of Ireland": {"last": 2002, "best": "Quarter-finals (1990)", "titles": 0},
    "Iceland": {"last": 2018, "best": "Group stage (2018)", "titles": 0},
    "Finland": {"last": "never", "best": "Never qualified", "titles": 0},
    "Slovakia": {"last": 2010, "best": "Round of 16 (2010)", "titles": 0},
    "Slovenia": {"last": 2010, "best": "Group stage (2002, 2010)", "titles": 0},
    "Burkina Faso": {"last": "never", "best": "Never qualified", "titles": 0},
    "Guinea": {"last": "never", "best": "Never qualified", "titles": 0},
}


def qualified_ids() -> set[str]:
    """Transfermarkt verein-ids of the 48 qualified nations (from the cached id map).

    Matching on the unambiguous id avoids every name-spelling trap (Türkiye/Turkey,
    Bosnia-Herzegovina/…) — `squad_value.nation_ids()` already resolved all 48."""
    return {vid for _slug, vid in squad_value.nation_ids().values()}


# ── parse the cached world-ranking pages ──────────────────────────────────────
ROW_RE = re.compile(
    r'<td class="zentriert cp">\s*(\d+).*?'                       # rank
    r'<a title="([^"]+)" href="/([a-z0-9-]+)/startseite/verein/(\d+)">\s*<img.*?'  # name slug id
    r'<td class="rechts">\s*(€[^<]*|-?)\s*</td>.*?'              # total value
    r'<td class="zentriert">([A-Z]+)</td>\s*'                    # confederation
    r'<td class="zentriert hauptlink">\s*([\d.]+|-)\s*</td>',    # points
    re.DOTALL)


def world_ranking(pages: int = 9) -> list[dict]:
    """[{rank, name, slug, id, value_eur, confed, points}] across all cached pages."""
    rows, seen = [], set()
    for page in range(1, pages + 1):
        html = squad_value.fetch(
            f"https://www.transfermarkt.com/statistik/weltrangliste?page={page}", ttl_days=30)
        for rank, name, slug, vid, val, confed, pts in ROW_RE.findall(html):
            key = squad_value.fold(name)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "rank": int(rank), "name": name.strip(), "slug": slug, "id": vid,
                "value_eur": squad_value.parse_value_eur(val) if val.startswith("€") else None,
                "confed": confed,
                "points": float(pts) if pts not in ("", "-") else None,
            })
    rows.sort(key=lambda r: r["rank"])
    return rows


# ── assemble the missed-out table ──────────────────────────────────────────────
def build_export() -> dict:
    qids = qualified_ids()
    ranking = world_ranking()
    # Elo over full history, snapshot the day before the opener
    elo_hist = historical.build_elo(historical._load())

    missed = []
    for r in ranking:
        if r["id"] in qids:
            continue  # qualified
        model = RANK_TO_MODEL.get(r["name"], r["name"])
        elo = historical.elo_before(elo_hist, model, "2026-06-11")
        code = squads.NATION_CODE.get(model, "")
        wc = WC_HISTORY.get(r["name"]) or WC_HISTORY.get(model) or {}
        missed.append({
            "name": r["name"], "model": model,
            "code": code, "flag": _flag(r["name"]),
            "fifa_rank": r["rank"], "fifa_points": r["points"],
            "confed": r["confed"], "value_eur": r["value_eur"],
            "elo": round(elo, 0) if elo != 1500.0 else None,
            "last_wc": wc.get("last"), "best_finish": wc.get("best"),
            "titles": wc.get("titles", 0), "note": wc.get("note"),
        })
    missed.sort(key=lambda m: m["fifa_rank"])
    feature = missed[:TOP_N]

    # context: the weakest *qualified* squads by value, to show who got in below them
    sv = json.loads((ROOT / "site" / "data" / "squad_value.json").read_text())
    weakest_qualified = sorted(
        [{"nation": k, "flag": v["flag"], "value_eur": v["squad_value"]}
         for k, v in sv["nations"].items() if v["squad_value"]],
        key=lambda x: x["value_eur"])[:8]

    return {
        "meta": {
            "n_qualified": len(qids), "n_ranked": len(ranking),
            "n_missed_featured": len(feature),
            "top_miss": feature[0]["name"] if feature else None,
            "note": ("Strongest non-qualifiers by FIFA world-ranking position. Value and points are "
                     "from Transfermarkt's world-ranking pages; Elo is built over the full martj42 "
                     "international history, snapshot 2026-06-10; World Cup pedigree is a hand-checked "
                     "reference."),
        },
        "missed": feature,
        "weakest_qualified": weakest_qualified,
        "sources": [
            {"label": "World ranking & squad values — Transfermarkt",
             "url": "https://www.transfermarkt.com/statistik/weltrangliste"},
            {"label": "Match history (Elo) — martj42 international results",
             "url": "https://github.com/martj42/international_results"},
        ],
    }


def export(path: Path | None = None) -> dict:
    out = build_export()
    path = path or ROOT / "site" / "data" / "missed.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return out


if __name__ == "__main__":
    d = export()
    m = d["meta"]
    print(f"missed.json: {m['n_ranked']} ranked nations, {m['n_qualified']} qualified, "
          f"featuring top {m['n_missed_featured']} misses (headline: {m['top_miss']})")
    for r in d["missed"][:12]:
        print(f"  #{r['fifa_rank']:>3}  {r['name']:<22} "
              f"€{(r['value_eur'] or 0)/1e6:>6.0f}m  Elo {r['elo']}  last WC {r['last_wc']}")
