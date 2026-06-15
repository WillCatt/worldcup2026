"""Forecast — predict every World Cup match as probabilities, then mark the model's
homework against the actual results.

The Dixon-Coles goals engine (`ratings.py`) already turns match history into per-fixture
score probabilities. This module wraps it into a forecast you can hold to account:

  1. Fit the model **frozen the day before kickoff** (`ASOF`), so no result that happens
     during the tournament can leak back into the ratings — every prediction is a genuine
     pre-tournament call.
  2. Predict all 72 group fixtures: 1X2 probabilities, expected goals, and the most likely
     scorelines (the Dixon-Coles score grid).
  3. As results land (openfootball feed, public domain, no key), keep a scorecard: how often
     the model called the right result, how many exact scorelines it nailed, and its Brier /
     log-loss against a coin-flip baseline — plus a reliability curve. Distinct from the
     Model-vs-Market piece: here the yardstick is reality, not the bookmaker.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from mlfootball import data, ratings, travel

ROOT = Path(__file__).resolve().parent.parent
ASOF = pd.Timestamp("2026-06-10")  # day before the opening match — freeze the model here
HOST_COUNTRIES = {"United States", "Canada", "Mexico"}

# schedule spellings -> the martj42/model spellings
SCHED_ALIAS = {
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
}
# openfootball feed spellings -> model spellings
FEED_URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
FEED_ALIASES = {
    "United States of America": "United States", "USA": "United States",
    "Korea Republic": "South Korea", "IR Iran": "Iran",
    "Côte d'Ivoire": "Ivory Coast", "Czechia": "Czech Republic",
    "Türkiye": "Turkey", "Bosnia & Herzegovina": "Bosnia and Herzegovina",
}


def _m(name: str) -> str:
    return SCHED_ALIAS.get(name, name)


def fixtures() -> list[dict]:
    out = []
    for date, group, a, b, venue_key in travel.SCHEDULE:
        v = travel.VENUES.get(venue_key, {})
        out.append({"date": date, "group": group,
                    "home": _m(a), "away": _m(b),
                    "venue": v.get("name", venue_key), "country": v.get("country", "")})
    return out


# ── prediction ────────────────────────────────────────────────────────────────
def _hosts(home: str, away: str, country: str) -> frozenset[str]:
    """A host nation gets the edge only when the match is in its own country."""
    return frozenset(t for t in (home, away) if t in HOST_COUNTRIES and t == country)


def top_scorelines(grid: np.ndarray, k: int = 4) -> list[dict]:
    flat = np.argsort(grid, axis=None)[::-1][:k]
    return [{"h": int(h), "a": int(a), "p": round(float(grid[h, a]), 4)}
            for h, a in (np.unravel_index(i, grid.shape) for i in flat)]


def predict(s: ratings.TeamStrengths, fx: dict) -> dict:
    h, a, hosts = fx["home"], fx["away"], _hosts(fx["home"], fx["away"], fx["country"])
    known = h in s.attack and a in s.attack
    op = s.outcome_probs(h, a, hosts=hosts) if known else {"home": None, "draw": None, "away": None}
    eg = s.expected_goals(h, a, hosts=hosts) if known else (None, None)
    grid = s.score_matrix(h, a, hosts=hosts) if known else None
    tops = top_scorelines(grid) if grid is not None else []
    # compact 0-5 goal grid for the heatmap (tail mass is negligible)
    gsmall = [[round(float(grid[i, j]), 4) for j in range(6)] for i in range(6)] if grid is not None else None
    return {
        **fx, "host_edge": sorted(hosts), "known": known, "grid": gsmall,
        "p_home": round(op["home"], 4) if known else None,
        "p_draw": round(op["draw"], 4) if known else None,
        "p_away": round(op["away"], 4) if known else None,
        "exp_home": round(float(eg[0]), 2) if known else None,
        "exp_away": round(float(eg[1]), 2) if known else None,
        "top_scores": tops,
        "likely": {"h": tops[0]["h"], "a": tops[0]["a"]} if tops else None,
    }


# ── actual results ──────────────────────────────────────────────────────────────
def fetch_results() -> dict[frozenset, dict[str, int]]:
    """{frozenset({home,away}): {team: goals}} for played matches. Empty on any feed error."""
    try:
        import urllib.request
        with urllib.request.urlopen(FEED_URL, timeout=30) as r:
            feed = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — a feed hiccup must not break the build
        print(f"[forecast] feed unavailable ({e}); no results to score yet.")
        return {}
    known = {}
    for m in feed.get("matches", []):
        s1, s2 = m.get("score1"), m.get("score2")
        if s1 is None or s2 is None:
            ft = (m.get("score") or {}).get("ft")
            if not ft:
                continue
            s1, s2 = ft[0], ft[1]
        home = FEED_ALIASES.get(str(m.get("team1", "")), str(m.get("team1", "")))
        away = FEED_ALIASES.get(str(m.get("team2", "")), str(m.get("team2", "")))
        if home and away:
            known[frozenset((home, away))] = {home: int(s1), away: int(s2)}
    return known


def _outcome(gh: int, ga: int) -> str:
    return "home" if gh > ga else ("away" if ga > gh else "draw")


# ── scorecard: predictions vs reality ─────────────────────────────────────────
def score(predictions: list[dict], results: dict) -> dict:
    OC = ["home", "draw", "away"]
    log, briers, briers_u, lls, lls_u = [], [], [], [], []
    n_correct = n_exact = 0
    cal_pred, cal_hit = [], []  # per (match,outcome) for reliability
    for p in predictions:
        if not p["known"]:
            continue
        res = results.get(frozenset((p["home"], p["away"])))
        if not res:
            continue
        gh, ga = res[p["home"]], res[p["away"]]
        actual = _outcome(gh, ga)
        probs = {"home": p["p_home"], "draw": p["p_draw"], "away": p["p_away"]}
        pred = max(probs, key=probs.get)
        correct = pred == actual
        exact = p["likely"] and p["likely"]["h"] == gh and p["likely"]["a"] == ga
        n_correct += correct
        n_exact += bool(exact)
        oh = {o: 1.0 if o == actual else 0.0 for o in OC}
        briers.append(sum((probs[o] - oh[o]) ** 2 for o in OC))
        briers_u.append(sum((1 / 3 - oh[o]) ** 2 for o in OC))
        lls.append(-np.log(max(probs[actual], 1e-9)))
        lls_u.append(-np.log(1 / 3))
        for o in OC:
            cal_pred.append(probs[o]); cal_hit.append(1.0 if o == actual else 0.0)
        log.append({"date": p["date"], "group": p["group"], "home": p["home"], "away": p["away"],
                    "p_home": p["p_home"], "p_draw": p["p_draw"], "p_away": p["p_away"],
                    "pred": pred, "likely": p["likely"], "actual": {"h": gh, "a": ga},
                    "actual_outcome": actual, "correct": correct, "exact": bool(exact)})
    n = len(log)
    # reliability: 5 confidence bins on predicted outcome probability
    cal = []
    if n:
        cp, ch = np.array(cal_pred), np.array(cal_hit)
        for lo in np.linspace(0, 0.8, 5):
            hi = lo + 0.2
            mask = (cp >= lo) & (cp < (hi if hi < 1 else 1.01))
            if mask.sum():
                cal.append({"lo": round(lo, 2), "hi": round(hi, 2),
                            "pred_mean": round(float(cp[mask].mean()), 3),
                            "obs_freq": round(float(ch[mask].mean()), 3), "n": int(mask.sum())})
    return {
        "n_played": n, "n_correct": n_correct,
        "pct_correct": round(n_correct / n, 4) if n else None,
        "n_exact": n_exact, "pct_exact": round(n_exact / n, 4) if n else None,
        "brier_model": round(float(np.mean(briers)), 4) if n else None,
        "brier_uniform": round(float(np.mean(briers_u)), 4) if n else None,
        "logloss_model": round(float(np.mean(lls)), 4) if n else None,
        "logloss_uniform": round(float(np.mean(lls_u)), 4) if n else None,
        "calibration": cal,
        "log": sorted(log, key=lambda r: r["date"]),
    }


def build_export() -> dict:
    s = ratings.fit(data.load(), asof=ASOF)
    fx = fixtures()
    preds = [predict(s, f) for f in fx]
    results = fetch_results()
    sc = score(preds, results)
    return {
        "meta": {
            "asof": ASOF.strftime("%Y-%m-%d"), "n_fitted_teams": len(s.attack),
            "home_adv": round(s.home_adv, 3), "rho": round(s.rho, 3),
            "n_fixtures": len(preds), "n_played": sc["n_played"],
            "model": "Dixon-Coles bivariate-Poisson, exponential time-decay",
        },
        "fixtures": preds,
        "scorecard": {k: sc[k] for k in sc if k not in ("log", "calibration")},
        "calibration": sc["calibration"],
        "log": sc["log"],
        "sources": [
            {"label": "Match history — martj42 international results", "url": "https://github.com/martj42/international_results"},
            {"label": "Live results — openfootball/worldcup.json", "url": "https://github.com/openfootball/worldcup.json"},
        ],
    }


def export(path: Path | None = None) -> dict:
    out = build_export()
    path = path or ROOT / "site" / "data" / "forecast.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return out


if __name__ == "__main__":
    d = export()
    m, sc = d["meta"], d["scorecard"]
    print(f"forecast.json: {m['n_fixtures']} fixtures predicted (model frozen {m['asof']}), "
          f"{sc['n_played']} played")
    if sc["n_played"]:
        print(f"  result called right: {sc['n_correct']}/{sc['n_played']} ({sc['pct_correct']:.0%}); "
              f"exact scores: {sc['n_exact']}; Brier {sc['brier_model']} vs {sc['brier_uniform']} (coin-flip)")
