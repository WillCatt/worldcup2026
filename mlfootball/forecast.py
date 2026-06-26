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
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
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


# ── feed (results + kickoff times) ────────────────────────────────────────────
@lru_cache(maxsize=1)
def _feed_matches() -> tuple:
    """openfootball match list, fetched once. Empty on any feed error (a hiccup must
    never break the build)."""
    try:
        import urllib.request
        with urllib.request.urlopen(FEED_URL, timeout=30) as r:
            return tuple(json.loads(r.read().decode("utf-8")).get("matches", []))
    except Exception as e:  # noqa: BLE001
        print(f"[forecast] feed unavailable ({e}); no results/kickoffs this run.")
        return ()


def fetch_results() -> dict[frozenset, dict[str, int]]:
    """{frozenset({home,away}): {team: goals}} for played matches."""
    known = {}
    for m in _feed_matches():
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


def _kickoff_utc(date_s: str, time_s: str) -> str | None:
    """openfootball date + 'HH:MM UTC±H[:MM]' (e.g. '13:00 UTC-6') -> UTC ISO 'Z' string."""
    if not date_s or not time_s:
        return None
    m = re.match(r"\s*(\d{1,2}):(\d{2})\s*UTC\s*([+-]\d{1,2})(?::(\d{2}))?", time_s)
    if not m:
        return None
    sign = -1 if m.group(3)[0] == "-" else 1
    offset = sign * timedelta(hours=abs(int(m.group(3))), minutes=int(m.group(4) or 0))
    try:
        local = datetime.strptime(f"{date_s} {int(m.group(1)):02d}:{m.group(2)}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return (local - offset).replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_kickoffs() -> dict[frozenset, str]:
    """{frozenset({home,away}): kickoff UTC ISO} from the feed's date+time fields."""
    out = {}
    for m in _feed_matches():
        home = FEED_ALIASES.get(str(m.get("team1", "")), str(m.get("team1", "")))
        away = FEED_ALIASES.get(str(m.get("team2", "")), str(m.get("team2", "")))
        k = _kickoff_utc(str(m.get("date", "")), str(m.get("time", "")))
        if home and away and k:
            out[frozenset((home, away))] = k
    return out


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
        log.append({"date": p["date"], "kickoff": p.get("kickoff"), "group": p["group"],
                    "home": p["home"], "away": p["away"],
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
    kicks = fetch_kickoffs()
    for f in fx:
        f["kickoff"] = kicks.get(frozenset((f["home"], f["away"])))
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


# ── parameter simulator ───────────────────────────────────────────────────────
# Ship genuinely-refit strengths at several decay settings + a market-value rating,
# so the browser can recompute true Dixon-Coles odds live as the user turns factors
# on/off and reweights them. No mockups: every knob produces real model output.
import math  # noqa: E402

DECAY_PRESETS = [  # (key, label, half-life in days; 0 = no decay)
    ("equal", "All history weighted equally", 0.0),
    ("slow", "Slow fade · 4-year half-life", math.log(2) / 1460),
    ("default", "Default · 2-year half-life", float(ratings.DEFAULT_XI)),
    ("fast", "Recent-leaning · 1-year half-life", math.log(2) / 365),
    ("hot", "Recent form only · 6-month half-life", math.log(2) / 183),
]
VALUE_SCALE = 0.15   # strength units per 1 SD of log market value, at full weight
SIM_MAX_GOALS = 8


def _value_z() -> dict[str, float]:
    """z-score of log(squad market value), keyed by model team name."""
    sv = json.loads((ROOT / "site" / "data" / "squad_value.json").read_text())
    vals = {n: v["squad_value"] for n, v in sv["nations"].items() if v["squad_value"]}
    logs = {n: math.log(v) for n, v in vals.items()}
    mu = sum(logs.values()) / len(logs)
    sd = (sum((x - mu) ** 2 for x in logs.values()) / len(logs)) ** 0.5
    return {n: round((x - mu) / sd, 4) for n, x in logs.items()}


def simulator_export(path: Path | None = None) -> dict:
    df = data.load()
    fx = fixtures()
    kicks = fetch_kickoffs()
    wc_teams = sorted({t for f in fx for t in (f["home"], f["away"])})
    presets = []
    for key, label, xi in DECAY_PRESETS:
        s = ratings.fit(df, xi=xi, asof=ASOF)
        presets.append({
            "key": key, "label": label,
            "half_life_days": round(math.log(2) / xi) if xi else None,
            "rho": round(s.rho, 5), "home_adv": round(s.home_adv, 5),
            "strengths": {t: [round(s.attack[t], 4), round(s.defence[t], 4)]
                          for t in wc_teams if t in s.attack},
        })
    out = {
        "meta": {"asof": ASOF.strftime("%Y-%m-%d"), "value_scale": VALUE_SCALE,
                 "max_goals": SIM_MAX_GOALS, "default_preset": "default"},
        "decay_presets": presets,
        "value_z": {t: z for t, z in _value_z().items() if t in wc_teams},
        "hosts": sorted(HOST_COUNTRIES),
        "fixtures": [{"date": f["date"], "kickoff": kicks.get(frozenset((f["home"], f["away"]))),
                      "group": f["group"], "home": f["home"],
                      "away": f["away"], "country": f["country"]} for f in fx],
    }
    path = path or ROOT / "site" / "data" / "simulator.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return out


def sim_recompute(sim: dict, preset_key: str, home: str, away: str, country: str,
                  w_value: float = 0.0, w_home: float = 1.0) -> dict:
    """Python mirror of the browser recompute — used to prove the JS will be faithful.
    Returns 1X2 under the chosen knobs."""
    pre = next(p for p in sim["decay_presets"] if p["key"] == preset_key)
    S, vz, sc = pre["strengths"], sim["value_z"], sim["meta"]["value_scale"]
    rho, ha, hosts = pre["rho"], pre["home_adv"], set(sim["hosts"])

    def adj(team):
        a, d = S[team]
        bump = w_value * sc * vz.get(team, 0.0)
        return a + bump, d + bump
    ah, dh = adj(home); aa, da = adj(away)
    adv_h = ha * w_home if (home in hosts and home == country) else 0.0
    adv_a = ha * w_home if (away in hosts and away == country) else 0.0
    mu_h, mu_a = math.exp(ah - da + adv_h), math.exp(aa - dh + adv_a)
    N = sim["meta"]["max_goals"]
    ph = [math.exp(-mu_h) * mu_h ** i / math.factorial(i) for i in range(N + 1)]
    pa = [math.exp(-mu_a) * mu_a ** j / math.factorial(j) for j in range(N + 1)]
    g = [[ph[i] * pa[j] for j in range(N + 1)] for i in range(N + 1)]
    g[0][0] *= 1 - mu_h * mu_a * rho
    g[0][1] *= 1 + mu_h * rho
    g[1][0] *= 1 + mu_a * rho
    g[1][1] *= 1 - rho
    tot = sum(sum(r) for r in g)
    home_p = sum(g[i][j] for i in range(N + 1) for j in range(N + 1) if i > j) / tot
    draw_p = sum(g[i][i] for i in range(N + 1)) / tot
    return {"home": round(home_p, 4), "draw": round(draw_p, 4),
            "away": round(1 - home_p - draw_p, 4)}


if __name__ == "__main__":
    d = export()
    m, sc = d["meta"], d["scorecard"]
    print(f"forecast.json: {m['n_fixtures']} fixtures predicted (model frozen {m['asof']}), "
          f"{sc['n_played']} played")
    if sc["n_played"]:
        print(f"  result called right: {sc['n_correct']}/{sc['n_played']} ({sc['pct_correct']:.0%}); "
              f"exact scores: {sc['n_exact']}; Brier {sc['brier_model']} vs {sc['brier_uniform']} (coin-flip)")
