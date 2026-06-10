"""Does travel actually hurt? A historical reality check on the burden thesis.

The 2026 index measures travel; it doesn't prove travel *matters*. Here we test
the claim on three past World Cups with real intra-tournament travel variance —
South Africa 2010, Brazil 2014, Russia 2018 — by asking: controlling for team
strength, did teams that flew further do worse in the group stage?

Method:
  * Strength = pre-tournament Elo, built over the full martj42 match history
    (every international back to 1872), snapshotted the day before each WC.
  * Travel  = great-circle km between a team's three group-match host cities,
    in date order (same definition as the 2026 index).
  * Outcome = group-stage points (3/1/0), the thing travel would erode.
  * Model   = pooled OLS of points on Elo + within-tournament-standardized travel.
    Travel is z-scored inside each tournament so a long Brazilian haul and a long
    Russian one are comparable, and tournament scale doesn't drive the fit.

A null or weak result is a finding too: it tells you how much to trust the index.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

# Host-city coordinates, keyed to the exact martj42 city strings.
CITY_COORDS: dict[str, tuple[float, float]] = {
    # South Africa 2010
    "Bloemfontein": (-29.0852, 26.1596), "Cape Town": (-33.9249, 18.4241),
    "Durban": (-29.8587, 31.0218), "Johannesburg": (-26.2041, 28.0473),
    "Nelspruit": (-25.4753, 30.9694), "Polokwane": (-23.9045, 29.4689),
    "Port Elizabeth": (-33.9608, 25.6022), "Pretoria": (-25.7479, 28.2293),
    "Rustenburg": (-25.6672, 27.2424),
    # Brazil 2014
    "Belo Horizonte": (-19.9167, -43.9345), "Brasília": (-15.7939, -47.8828),
    "Cuiabá": (-15.6014, -56.0979), "Curitiba": (-25.4284, -49.2733),
    "Fortaleza": (-3.7172, -38.5433), "Manaus": (-3.1190, -60.0217),
    "Natal": (-5.7945, -35.2110), "Porto Alegre": (-30.0346, -51.2177),
    "Recife": (-8.0476, -34.8770), "Rio de Janeiro": (-22.9068, -43.1729),
    "Salvador": (-12.9777, -38.5016), "São Paulo": (-23.5505, -46.6333),
    # Russia 2018
    "Ekaterinburg": (56.8389, 60.6057), "Kaliningrad": (54.7104, 20.4522),
    "Kazan": (55.8304, 49.0661), "Moscow": (55.7558, 37.6173),
    "Nizhny Novgorod": (56.2965, 43.9361), "Rostov-on-Don": (47.2357, 39.7015),
    "Saint Petersburg": (59.9311, 30.3609), "Samara": (53.1959, 50.1002),
    "Saransk": (54.1838, 45.1749), "Sochi": (43.6028, 39.7342),
    "Volgograd": (48.7080, 44.5133),
}

TOURNAMENTS = {"2010": 48, "2014": 48, "2018": 48}  # first N matches = group stage (32-team format)

DATA = Path(__file__).resolve().parent.parent / "data" / "results.csv"


def _haversine_ll(a: tuple[float, float], b: tuple[float, float]) -> float:
    R = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi = math.radians(b[0] - a[0])
    dlam = math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _load() -> list[dict]:
    return list(csv.DictReader(open(DATA, encoding="utf-8")))


# ── Elo strength model ────────────────────────────────────────────────────────
def build_elo(rows: list[dict], k: float = 30.0, home_adv: float = 65.0) -> dict[str, list]:
    """Elo over the full history, returning per-team [(date, rating)] snapshots."""
    rating: dict[str, float] = {}
    history: dict[str, list] = {}
    for r in sorted(rows, key=lambda x: x["date"]):
        h, a = r["home_team"], r["away_team"]
        try:
            hs, as_ = int(r["home_score"]), int(r["away_score"])
        except (ValueError, KeyError):
            continue
        Rh = rating.get(h, 1500.0)
        Ra = rating.get(a, 1500.0)
        adv = 0.0 if str(r.get("neutral", "")).upper() == "TRUE" else home_adv
        Eh = 1.0 / (1.0 + 10 ** (-((Rh + adv) - Ra) / 400))
        Sh = 1.0 if hs > as_ else 0.5 if hs == as_ else 0.0
        rating[h] = Rh + k * (Sh - Eh)
        rating[a] = Ra + k * ((1 - Sh) - (1 - Eh))
        history.setdefault(h, []).append((r["date"], rating[h]))
        history.setdefault(a, []).append((r["date"], rating[a]))
    return history


def elo_before(history: dict[str, list], team: str, date: str) -> float:
    snaps = history.get(team, [])
    val = 1500.0
    for d, rt in snaps:
        if d < date:
            val = rt
        else:
            break
    return val


# ── Build the per-team-per-tournament panel ───────────────────────────────────
def build_panel() -> list[dict]:
    rows = _load()
    history = build_elo(rows)
    panel = []
    for yr, n_group in TOURNAMENTS.items():
        wc = sorted([r for r in rows if r["tournament"] == "FIFA World Cup" and r["date"][:4] == yr],
                    key=lambda x: (x["date"], x["city"]))
        group = wc[:n_group]
        start = group[0]["date"]
        # collect each team's group matches in date order
        per_team: dict[str, list[dict]] = {}
        for r in group:
            for side, opp_side in (("home_team", "away_team"), ("away_team", "home_team")):
                t = r[side]
                hs, as_ = int(r["home_score"]), int(r["away_score"])
                gf, ga = (hs, as_) if side == "home_team" else (as_, hs)
                pts = 3 if gf > ga else 1 if gf == ga else 0
                per_team.setdefault(t, []).append(
                    {"date": r["date"], "city": r["city"], "pts": pts, "gd": gf - ga})
        for t, matches in per_team.items():
            if len(matches) != 3:
                continue  # safety: only full group campaigns
            matches.sort(key=lambda m: m["date"])
            km = sum(_haversine_ll(CITY_COORDS[matches[i - 1]["city"]], CITY_COORDS[matches[i]["city"]])
                     for i in range(1, len(matches)))
            panel.append({
                "year": yr, "team": t,
                "travel_km": round(km),
                "points": sum(m["pts"] for m in matches),
                "gd": sum(m["gd"] for m in matches),
                "elo": round(elo_before(history, t, start), 1),
            })
    return panel


# ── Minimal OLS (no statsmodels dependency) ───────────────────────────────────
def _ols(X: list[list[float]], y: list[float]) -> dict:
    """Ordinary least squares with t-stats. X includes an intercept column."""
    import numpy as np
    Xm = np.array(X, dtype=float)
    yv = np.array(y, dtype=float)
    n, p = Xm.shape
    beta, *_ = np.linalg.lstsq(Xm, yv, rcond=None)
    resid = yv - Xm @ beta
    dof = n - p
    sigma2 = (resid @ resid) / dof
    cov = sigma2 * np.linalg.inv(Xm.T @ Xm)
    se = np.sqrt(np.diag(cov))
    t = beta / se
    # two-sided p via normal approx (n large enough)
    from math import erfc, sqrt
    pval = [erfc(abs(ti) / sqrt(2)) for ti in t]
    ss_tot = ((yv - yv.mean()) ** 2).sum()
    r2 = 1 - (resid @ resid) / ss_tot
    return {"beta": beta.tolist(), "se": se.tolist(), "t": t.tolist(), "p": pval, "r2": float(r2), "n": n}


def _zscore_within(panel: list[dict], key: str, by: str) -> dict[int, float]:
    groups: dict[str, list[float]] = {}
    for row in panel:
        groups.setdefault(row[by], []).append(row[key])
    stats = {}
    for g, vals in groups.items():
        mu = sum(vals) / len(vals)
        sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
        stats[g] = (mu, sd)
    return {i: (row[key] - stats[row[by]][0]) / stats[row[by]][1] for i, row in enumerate(panel)}


def regression() -> dict:
    """Pooled OLS: group-stage points ~ Elo + within-tournament-standardized travel."""
    panel = build_panel()
    travel_z = _zscore_within(panel, "travel_km", "year")
    elo = [row["elo"] for row in panel]
    elo_mu = sum(elo) / len(elo)
    elo_sd = (sum((e - elo_mu) ** 2 for e in elo) / len(elo)) ** 0.5 or 1.0
    X, y = [], []
    for i, row in enumerate(panel):
        X.append([1.0, (row["elo"] - elo_mu) / elo_sd, travel_z[i]])
        y.append(float(row["points"]))
    fit = _ols(X, y)
    labels = ["intercept", "elo_z", "travel_z"]
    # raw correlation of travel with points (uncontrolled), for contrast
    import numpy as np
    tv = np.array([travel_z[i] for i in range(len(panel))])
    pts = np.array(y)
    raw_r = float(np.corrcoef(tv, pts)[0, 1])
    return {
        "n": fit["n"],
        "tournaments": list(TOURNAMENTS),
        "coef": {labels[i]: {"beta": round(fit["beta"][i], 4),
                             "se": round(fit["se"][i], 4),
                             "t": round(fit["t"][i], 3),
                             "p": round(fit["p"][i], 4)} for i in range(len(labels))},
        "r2": round(fit["r2"], 4),
        "raw_travel_points_corr": round(raw_r, 4),
        "panel": panel,
    }
