"""Bracket — the World Cup knockout ladder, read by the same frozen Dixon-Coles model.

The group stage is over; 32 teams remain. This module takes the openfootball knockout
draw (Round of 32 → Final, plus the third-place game) and, using the *same pre-tournament
strengths* the Forecast piece is held to (`forecast.ASOF`, frozen the day before the
opening match), does two things:

  1. **Per-tie odds.** For every tie whose two teams are known, the model's 1X2, expected
     goals, most-likely scorelines and — the knockout-specific number — each side's
     probability of *advancing*. A knockout has no draws: 90-minute level games go to
     extra time and, if still level, penalties, which the Penalties piece showed to be
     close to a coin flip. So  P(advance) = P(win) + ½·P(draw).
  2. **The whole ladder, simulated.** Monte-Carlo the entire bracket from the current draw
     forward — sampling each tie by the model's advance probability and propagating winners
     up the tree — to get every remaining team's chance of reaching each round and lifting
     the trophy. Ties already played are locked to their real result, so the projection
     sharpens automatically as the tournament unfolds (the daily job re-runs it).

Host edge is applied exactly as in the group stage: a host nation (USA / Canada / Mexico)
gets the venue bump only when the tie is played in its own country.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np

from mlfootball import data, forecast, ratings, travel

ROOT = Path(__file__).resolve().parent.parent

# openfootball round labels, in bracket order, with the keys/labels the site uses.
ROUNDS = [
    ("r32", "Round of 32", "Round of 32"),
    ("r16", "Round of 16", "Round of 16"),
    ("qf", "Quarter-final", "Quarter-finals"),
    ("sf", "Semi-final", "Semi-finals"),
    ("final", "Final", "Final"),
]
FEED_ROUND_KEY = {feed: key for key, feed, _ in ROUNDS}
THIRD_FEED = "Match for third place"

# VENUES record their country as "USA"; the model speaks of "United States".
_COUNTRY_FIX = {"USA": "United States"}


# ── draw / venues ───────────────────────────────────────────────────────────
def _ground_country(ground: str | None) -> str:
    """openfootball 'ground' (a city, e.g. 'Los Angeles (Inglewood)') → host country,
    via the city table the Travel piece already maintains. '' if unmatched (treated
    as neutral — no host edge)."""
    if not ground:
        return ""
    g = ground.lower()
    for v in travel.VENUES.values():
        if v["city"].lower() in g:
            return _COUNTRY_FIX.get(v["country"], v["country"])
    return ""


def _team(name: str | None) -> str | None:
    """Resolve a feed team name to the model's spelling; None for a placeholder
    (e.g. 'W74', 'L101') that isn't a decided team yet."""
    if not name:
        return None
    if name[0] in "WL" and name[1:].isdigit():
        return None
    return forecast.FEED_ALIASES.get(name, name)


def _ref(name: str | None) -> tuple[str, int] | None:
    """A placeholder slot 'W74'/'L101' → ('W', 74); None for a real team."""
    if name and name[0] in "WL" and name[1:].isdigit():
        return name[0], int(name[1:])
    return None


def knockout_matches() -> list[dict]:
    """Every knockout fixture from the feed, in match-number order, normalised."""
    out = []
    for m in forecast._feed_matches():
        rnd = m.get("round")
        if rnd not in FEED_ROUND_KEY and rnd != THIRD_FEED:
            continue
        t1, t2 = str(m.get("team1", "")), str(m.get("team2", ""))
        s1, s2 = m.get("score1"), m.get("score2")
        if s1 is None or s2 is None:
            ft = (m.get("score") or {}).get("ft")
            if ft:
                s1, s2 = ft[0], ft[1]
        out.append({
            "num": int(m.get("num")),
            "round": rnd,
            "date": m.get("date"),
            "kickoff": forecast._kickoff_utc(str(m.get("date", "")), str(m.get("time", ""))),
            "ground": m.get("ground"),
            "country": _ground_country(m.get("ground")),
            "t1_raw": t1, "t2_raw": t2,
            "t1": _team(t1), "t2": _team(t2),
            "r1": _ref(t1), "r2": _ref(t2),
            "score": ([int(s1), int(s2)] if s1 is not None and s2 is not None else None),
        })
    return sorted(out, key=lambda t: t["num"])


# ── per-tie model read ────────────────────────────────────────────────────────
def _hosts(home, away, country):
    return frozenset(t for t in (home, away)
                     if t in forecast.HOST_COUNTRIES and t == country)


def tie_odds(s: ratings.TeamStrengths, home: str, away: str, country: str) -> dict | None:
    """Full model read on one knockout tie. None if either team is unrated."""
    if home not in s.attack or away not in s.attack:
        return None
    hosts = _hosts(home, away, country)
    op = s.outcome_probs(home, away, hosts=hosts)
    eg = s.expected_goals(home, away, hosts=hosts)
    grid = s.score_matrix(home, away, hosts=hosts)
    return {
        "host_edge": sorted(hosts),
        "p_home": round(op["home"], 4), "p_draw": round(op["draw"], 4), "p_away": round(op["away"], 4),
        "exp_home": round(float(eg[0]), 2), "exp_away": round(float(eg[1]), 2),
        # a knockout is decided: level after 90' → ET/pens ≈ coin flip
        "adv_home": round(op["home"] + op["draw"] / 2, 4),
        "adv_away": round(op["away"] + op["draw"] / 2, 4),
        "top_scores": forecast.top_scorelines(grid),
        "grid": [[round(float(grid[i, j]), 4) for j in range(6)] for i in range(6)],
    }


def _adv_home(s, cache, home, away, country):
    """Cached P(home advances) for a (home, away, country) matchup."""
    key = (home, away, country)
    if key not in cache:
        hosts = _hosts(home, away, country)
        op = s.outcome_probs(home, away, hosts=hosts)
        cache[key] = op["home"] + op["draw"] / 2
    return cache[key]


# ── full-bracket Monte-Carlo ──────────────────────────────────────────────────
def simulate(s: ratings.TeamStrengths, ties: list[dict], n: int = 40000,
             seed: int = 20260628) -> dict:
    """Roll the whole draw forward n times. Decided ties are locked to reality; the
    rest are sampled by the model. Returns per-team P(reach each round) and P(champion)."""
    by_num = {t["num"]: t for t in ties}
    final_num = max(t["num"] for t in ties if FEED_ROUND_KEY.get(t["round"]) == "final")
    rng = random.Random(seed)
    cache: dict = {}

    teams = sorted({t for tie in ties for t in (tie["t1"], tie["t2"]) if t})
    reach = {t: {"r16": 0, "qf": 0, "sf": 0, "final": 0, "champ": 0} for t in teams}
    # which round-key a *participant* of match `num` has reached by playing in it
    PARTICIPATION = {"r16": "r16", "qf": "qf", "sf": "sf", "final": "final"}

    def resolve(tie, winners, losers):
        def side(team, ref):
            if team:
                return team
            if ref is None:
                return None
            return (winners if ref[0] == "W" else losers).get(ref[1])
        return side(tie["t1"], tie["r1"]), side(tie["t2"], tie["r2"])

    for _ in range(n):
        winners, losers = {}, {}
        for num in sorted(by_num):  # ascending: every ref points to a lower number
            tie = by_num[num]
            home, away = resolve(tie, winners, losers)
            if not home or not away:
                continue
            key = FEED_ROUND_KEY.get(tie["round"])
            if key in PARTICIPATION:
                reach[home][PARTICIPATION[key]] += 1
                reach[away][PARTICIPATION[key]] += 1
            if tie["score"] is not None:  # locked to the real result
                hw = tie["score"][0] > tie["score"][1]
            else:
                hw = rng.random() < _adv_home(s, cache, home, away, tie["country"])
            w, l = (home, away) if hw else (away, home)
            winners[num], losers[num] = w, l
        champ = winners.get(final_num)
        if champ:
            reach[champ]["champ"] += 1

    return {t: {k: round(v / n, 4) for k, v in r.items()} for t, r in reach.items()}


# ── export ────────────────────────────────────────────────────────────────────
def build_export() -> dict:
    s = ratings.fit(data.load(), asof=forecast.ASOF)
    matches = knockout_matches()
    sim = simulate(s, matches)

    def pack(tie):
        home, away = tie["t1"], tie["t2"]
        played = tie["score"] is not None
        winner = None
        if played and home and away:
            winner = home if tie["score"][0] > tie["score"][1] else away
        out = {
            "num": tie["num"], "round": FEED_ROUND_KEY.get(tie["round"], "third"),
            "date": tie["date"], "kickoff": tie["kickoff"], "ground": tie["ground"],
            "country": tie["country"],
            "home": home, "away": away, "home_raw": tie["t1_raw"], "away_raw": tie["t2_raw"],
            "known": bool(home and away),
            "played": played, "score": tie["score"], "winner": winner,
        }
        odds = tie_odds(s, home, away, tie["country"]) if home and away else None
        if odds:
            out.update(odds)
        return out

    rounds = [{"key": key, "name": label,
               "ties": [pack(t) for t in matches if FEED_ROUND_KEY.get(t["round"]) == key]}
              for key, _feed, label in ROUNDS]
    third = next((pack(t) for t in matches if t["round"] == THIRD_FEED), None)

    # tournament table: remaining teams, by championship chance
    table = sorted(
        ({"team": t, **probs} for t, probs in sim.items()),
        key=lambda r: (-r["champ"], -r["final"], -r["sf"]))

    n_played_ko = sum(1 for t in matches if t["score"] is not None)
    n_ties_ko = len(matches)
    return {
        "meta": {
            "asof": forecast.ASOF.strftime("%Y-%m-%d"),
            "n_teams": len(table), "n_ties": n_ties_ko, "n_played": n_played_ko,
            "sims": 40000,
            "model": "Dixon-Coles bivariate-Poisson, exponential time-decay (frozen pre-tournament)",
        },
        "rounds": rounds,
        "third": third,
        "tournament": table,
        "sources": [
            {"label": "Match history — martj42 international results", "url": "https://github.com/martj42/international_results"},
            {"label": "Knockout draw + results — openfootball/worldcup.json", "url": "https://github.com/openfootball/worldcup.json"},
        ],
    }


def export(path: Path | None = None) -> dict:
    out = build_export()
    path = path or ROOT / "site" / "data" / "bracket.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return out


if __name__ == "__main__":
    d = export()
    m = d["meta"]
    print(f"bracket.json: {m['n_ties']} knockout ties, {m['n_played']} played "
          f"(model frozen {m['asof']})")
    print("Title favourites:")
    for r in d["tournament"][:8]:
        print(f"  {r['team']:<18} champ {r['champ']:.1%}  final {r['final']:.1%}  sf {r['sf']:.1%}")
