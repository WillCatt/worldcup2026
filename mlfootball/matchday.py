"""Matchday — today's (or tomorrow's) World Cup fixtures, in depth.

For each upcoming/live fixture this assembles a full preview out of data the project
already produces, with no new heavy computation:

  * the frozen Dixon-Coles match prediction              (site/data/forecast.json)
  * both value-ranked best XIs + every squad player's
    club / caps / goals / market value                   (squad_value.json + squads.py)
  * each team's manager                                  (Wikipedia squad wikitext)
  * recent international form coming in                   (martj42 history, pre-tournament)
  * an auto factual 'tournament so far' summary          (openfootball live results feed)

Honest about the gaps. There is no clean, free source for per-player *minutes played* at
this tournament — the live feed carries results and goal events only, not lineups — so the
player detail is career caps/goals + club + market value + any tournament goals, and the XI
is value-ranked (same basis as the Squad-Value piece), not a tactical lineup prediction.

Like forecast.json this is a *live* artifact: re-run it (`python -m mlfootball.matchday`) as
results land to refresh scores, scorers and the 'tournament so far' lines.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import urllib.request
from pathlib import Path

from mlfootball import forecast, squad_value, squads, travel

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "squads_wikitext.txt"
RESULTS_CSV = ROOT / "data" / "results.csv"
FORECAST_JSON = ROOT / "site" / "data" / "forecast.json"
SQUAD_VALUE_JSON = ROOT / "site" / "data" / "squad_value.json"

# everything is keyed by the model/squad spelling (e.g. "Czech Republic", "Turkey",
# "United States", "Ivory Coast") — forecast.json, squad_value.json, squads.py and the
# martj42 history all already agree on it; only the live feed needs translating.
fold = squad_value.fold


# ── managers (Wikipedia squad wikitext) ───────────────────────────────────────
def managers() -> dict[str, str]:
    """{nation: head-coach name} parsed from the cached 2026 squad wikitext.

    Each nation section carries a `Coach: [[Name]]` line; foreign coaches get a
    `{{#invoke:flag|icon|XXX}}` flag prefix we strip. Same section-splitting as
    `squads.load_players`, so the nation keys line up exactly."""
    t = RAW.read_text(encoding="utf-8")
    heads = [(m.start(), m.group(1).strip())
             for m in re.finditer(r"\n===\s*([^=\n][^=]*?)\s*===\n", t)]
    nations = [(p, n) for p, n in heads if not n.lower().startswith(("group", "note"))]
    bounds = [p for p, _ in nations] + [len(t)]
    out: dict[str, str] = {}
    for i, (p, nat) in enumerate(nations):
        # drop HTML comments first — some Coach lines hide one after "Coach:" or
        # even inside the {{#invoke:flag}} template ("Coach:<!--..--> [[Name]]").
        section = re.sub(r"<!--.*?-->", "", t[p:bounds[i + 1]], flags=re.DOTALL)
        m = re.search(
            r"Coach:\s*(?:\{\{[^}]*\}\}\s*)?\[\[(?:[^\]|]*\|)?([^\]]+)\]\]",
            section)
        if m:
            out[nat] = m.group(1).strip()
    return out


# ── recent international form (martj42 history, pre-tournament) ────────────────
def _results_rows() -> list[dict]:
    with open(RESULTS_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def recent_form(rows: list[dict], team: str, n: int = 5,
                before: str = "2026-06-11") -> dict:
    """Last `n` internationals before kickoff (form coming into the tournament)."""
    games = []
    for r in rows:
        if r["date"] >= before:
            continue
        h, a = r["home_team"], r["away_team"]
        if team not in (h, a):
            continue
        try:
            hs, as_ = int(r["home_score"]), int(r["away_score"])
        except (ValueError, KeyError):
            continue
        gf, ga = (hs, as_) if team == h else (as_, hs)
        neutral = str(r.get("neutral", "")).upper() == "TRUE"
        games.append({
            "date": r["date"],
            "opp": a if team == h else h,
            "gf": gf, "ga": ga,
            "res": "W" if gf > ga else "D" if gf == ga else "L",
            "venue": "N" if neutral else ("H" if team == h else "A"),
        })
    games.sort(key=lambda g: g["date"])
    last = games[-n:]
    return {
        "games": last,
        "w": sum(g["res"] == "W" for g in last),
        "d": sum(g["res"] == "D" for g in last),
        "l": sum(g["res"] == "L" for g in last),
    }


# ── tournament so far (openfootball live feed) ────────────────────────────────
def _ordinal(i: int) -> str:
    return f"{i}{'th' if 11 <= i % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(i % 10, 'th')}"


def _fetch_feed() -> dict:
    try:
        with urllib.request.urlopen(forecast.FEED_URL, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — a feed hiccup must not break the build
        print(f"[matchday] feed unavailable ({e}); building with predictions only.")
        return {"matches": []}


def _feed_team(name: str) -> str:
    return forecast.FEED_ALIASES.get(str(name), str(name))


def _ft(m: dict):
    """(home_goals, away_goals) if the match is played, else None."""
    s1, s2 = m.get("score1"), m.get("score2")
    if s1 is None or s2 is None:
        ft = (m.get("score") or {}).get("ft")
        if not ft:
            return None
        s1, s2 = ft[0], ft[1]
    return int(s1), int(s2)


def feed_index(feed: dict) -> dict[tuple, dict]:
    """{(date, frozenset({home,away})): {kickoff, ground, score, scorers}} keyed by model names."""
    idx = {}
    for m in feed.get("matches", []):
        h, a = _feed_team(m.get("team1", "")), _feed_team(m.get("team2", ""))
        if not h or not a:
            continue
        ft = _ft(m)
        idx[(m.get("date", ""), frozenset((h, a)))] = {
            "home": h, "away": a, "kickoff": m.get("time", ""), "ground": m.get("ground", ""),
            "group": (m.get("group", "") or "").replace("Group ", ""),
            "score": {"h": ft[0], "a": ft[1]} if ft else None,
            "scorers": {
                "home": [{"name": g.get("name", ""), "minute": str(g.get("minute", ""))}
                         for g in (m.get("goals1") or [])],
                "away": [{"name": g.get("name", ""), "minute": str(g.get("minute", ""))}
                         for g in (m.get("goals2") or [])],
            },
        }
    return idx


def tournament_so_far(feed: dict) -> dict[str, dict]:
    """Per-team standing + scorers + an auto factual summary, computed from played games."""
    stand: dict[str, dict] = {}
    scorers: dict[str, list] = {}
    for m in feed.get("matches", []):
        ft = _ft(m)
        if not ft:
            continue
        h, a = _feed_team(m.get("team1", "")), _feed_team(m.get("team2", ""))
        gh, ga = ft
        grp = (m.get("group", "") or "").replace("Group ", "")
        for t, gf, gaa in ((h, gh, ga), (a, ga, gh)):
            s = stand.setdefault(t, {"group": grp, "p": 0, "w": 0, "d": 0, "l": 0,
                                     "gf": 0, "ga": 0, "pts": 0})
            s["p"] += 1
            s["gf"] += gf
            s["ga"] += gaa
            if gf > gaa:
                s["w"] += 1
                s["pts"] += 3
            elif gf == gaa:
                s["d"] += 1
                s["pts"] += 1
            else:
                s["l"] += 1
        for t, goals in ((h, m.get("goals1")), (a, m.get("goals2"))):
            for g in (goals or []):
                scorers.setdefault(t, []).append(
                    {"name": g.get("name", ""), "minute": str(g.get("minute", ""))})
    # group ranks
    by_group: dict[str, list] = {}
    for t, s in stand.items():
        by_group.setdefault(s["group"], []).append((t, s))
    rank = {}
    for grp, teams in by_group.items():
        teams.sort(key=lambda ts: (-ts[1]["pts"], -(ts[1]["gf"] - ts[1]["ga"]), -ts[1]["gf"]))
        for i, (t, _) in enumerate(teams):
            rank[t] = i + 1
    out = {}
    for t, s in stand.items():
        gd = s["gf"] - s["ga"]
        wdl = f"W{s['w']} D{s['d']} L{s['l']}"
        summary = (f"P{s['p']} · {wdl} · {s['pts']} pt{'s' if s['pts'] != 1 else ''}"
                   f" · {_ordinal(rank[t])} in Group {s['group']}")
        out[t] = {**s, "gd": gd, "rank": rank[t], "summary": summary,
                  "scorers": sorted(scorers.get(t, []),
                                    key=lambda g: int(re.sub(r"\D", "", g["minute"]) or 0))}
    return out


# ── assemble ──────────────────────────────────────────────────────────────────
def build_export() -> dict:
    fc = json.loads(FORECAST_JSON.read_text())
    sv = json.loads(SQUAD_VALUE_JSON.read_text())
    rows = _results_rows()
    mgr = managers()
    feed = _fetch_feed()
    fidx = feed_index(feed)
    tsf = tournament_so_far(feed)

    # goals per player (squad_value player records carry caps but not goals)
    goals_by = {}
    for p in squads.load_players():
        goals_by.setdefault(p["nation"], {})[fold(p["name"])] = p["goals"]

    teams = {}
    for nat, info in sv["nations"].items():
        gmap = goals_by.get(nat, {})
        primary, secondary = squads.FED_COLORS.get(nat, ("#5B5751", "#8A857C"))
        players = [{
            "name": p["name"], "pos": p["pos"], "pos_group": p["pos_group"],
            "club": p["club"], "caps": p["caps"], "goals": gmap.get(fold(p["name"])),
            "value_eur": p["value_eur"], "in_xi": p["in_xi"],
        } for p in info["players"]]
        teams[nat] = {
            "flag": info["flag"], "colors": {"primary": primary, "secondary": secondary},
            "manager": mgr.get(nat),
            "squad_value": info["squad_value"], "xi_value": info["xi_value"],
            "n_players": info["n_players"], "n_valued": info["n_valued"],
            "recent_form": recent_form(rows, nat),
            "tournament": tsf.get(nat),
            "players": players,
        }

    fixtures = []
    for f in fc["fixtures"]:
        key = (f["date"], frozenset((f["home"], f["away"])))
        live = fidx.get(key, {})
        fixtures.append({
            "date": f["date"], "group": f["group"], "home": f["home"], "away": f["away"],
            "venue": f.get("venue", ""), "kickoff": live.get("kickoff", ""),
            "ground": live.get("ground", ""),
            "status": "done" if live.get("score") else "upcoming",
            "score": live.get("score"), "scorers": live.get("scorers"),
            "model": {
                "p_home": f.get("p_home"), "p_draw": f.get("p_draw"), "p_away": f.get("p_away"),
                "exp_home": f.get("exp_home"), "exp_away": f.get("exp_away"),
                "top_score": (f.get("top_scores") or [None])[0],
                "known": f.get("known", False),
            },
        })
    fixtures.sort(key=lambda f: (f["date"], f["group"], f["home"]))

    today = dt.date.today().isoformat()
    return {
        "meta": {
            "generated_for": today,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "asof_model": fc["meta"]["asof"],
            "n_fixtures": len(fixtures),
            "n_played": sum(f["status"] == "done" for f in fixtures),
            "note": ("XIs are value-ranked (Transfermarkt), not tactical lineups; the live feed "
                     "carries results and goal events only, so there are no per-player minutes."),
        },
        "teams": teams,
        "fixtures": fixtures,
        "sources": [
            {"label": "Predictions — Dixon-Coles model (this project)", "url": ""},
            {"label": "Squads & managers — Wikipedia 2026 World Cup squads",
             "url": "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads"},
            {"label": "Market values — Transfermarkt", "url": "https://www.transfermarkt.com"},
            {"label": "Live results — openfootball/worldcup.json",
             "url": "https://github.com/openfootball/worldcup.json"},
            {"label": "Match history — martj42 international results",
             "url": "https://github.com/martj42/international_results"},
        ],
    }


def export(path: Path | None = None) -> dict:
    out = build_export()
    path = path or ROOT / "site" / "data" / "matchday.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return out


if __name__ == "__main__":
    d = export()
    m = d["meta"]
    print(f"matchday.json: {m['n_fixtures']} fixtures ({m['n_played']} played), "
          f"{len(d['teams'])} teams, generated_for {m['generated_for']}")
    today = [f for f in d["fixtures"] if f["date"] == m["generated_for"]]
    print(f"  today ({m['generated_for']}): " +
          (", ".join(f"{f['home']} v {f['away']}" for f in today) or "no fixtures"))
    miss_mgr = [n for n, t in d["teams"].items() if not t["manager"]]
    if miss_mgr:
        print(f"  ! no manager parsed for: {miss_mgr}")
