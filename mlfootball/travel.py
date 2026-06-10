"""The 2026 World Cup Travel Burden Index.

Three host countries, 16 venues, brutal distances. This module turns the final
(Dec 2025 draw) group-stage schedule into a defensible, from-scratch "burden
index" for every team: how far they fly, how many time-zones they cross, how
much altitude they breathe, and how little they get to rest.

Design choices (the kind an interviewer probes):
  * Scope = group stage only. Every team plays exactly three matches in a fixed
    structure, so all 48 are compared on equal footing. Knockout travel is
    path-dependent (you don't know who you'll be), so it's a caveat, not a number.
  * Travel = sum of great-circle (haversine) distance between *consecutive* match
    venues. We deliberately don't invent a "base camp" leg — base locations are
    private and would add a fabricated constant; inter-match legs are what every
    team verifiably flies.
  * The composite is a z-scored weighted sum of four sub-burdens. Weights are a
    judgement call, so we ship a sensitivity analysis instead of pretending the
    default weighting is the truth.

Everything below is static data — refreshingly no scraping.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ── Venues ────────────────────────────────────────────────────────────────────
# lat/lon = stadium; alt = metres above sea level; tz = UTC offset *in June 2026*
# (US/Canada on DST; Mexico abolished DST in 2022, so its venues stay UTC-6).
VENUES: dict[str, dict] = {
    "mexico_city":  {"name": "Estadio Azteca",        "city": "Mexico City",   "country": "Mexico",  "lat": 19.3029, "lon": -99.1505, "alt": 2200, "tz": -6},
    "guadalajara":  {"name": "Estadio Akron",         "city": "Guadalajara",   "country": "Mexico",  "lat": 20.6819, "lon": -103.4626, "alt": 1560, "tz": -6},
    "monterrey":    {"name": "Estadio BBVA",          "city": "Monterrey",     "country": "Mexico",  "lat": 25.6692, "lon": -100.2447, "alt": 500,  "tz": -6},
    "toronto":      {"name": "BMO Field",             "city": "Toronto",       "country": "Canada",  "lat": 43.6332, "lon": -79.4185,  "alt": 76,   "tz": -4},
    "vancouver":    {"name": "BC Place",              "city": "Vancouver",     "country": "Canada",  "lat": 49.2768, "lon": -123.1119, "alt": 3,    "tz": -7},
    "los_angeles":  {"name": "SoFi Stadium",          "city": "Los Angeles",   "country": "USA",     "lat": 33.9535, "lon": -118.3392, "alt": 30,   "tz": -7},
    "bay_area":     {"name": "Levi's Stadium",        "city": "SF Bay Area",   "country": "USA",     "lat": 37.4030, "lon": -121.9698, "alt": 6,    "tz": -7},
    "seattle":      {"name": "Lumen Field",           "city": "Seattle",       "country": "USA",     "lat": 47.5952, "lon": -122.3316, "alt": 5,    "tz": -7},
    "dallas":       {"name": "AT&T Stadium",          "city": "Dallas",        "country": "USA",     "lat": 32.7473, "lon": -97.0945,  "alt": 150,  "tz": -5},
    "houston":      {"name": "NRG Stadium",           "city": "Houston",       "country": "USA",     "lat": 29.6847, "lon": -95.4107,  "alt": 15,   "tz": -5},
    "kansas_city":  {"name": "Arrowhead Stadium",     "city": "Kansas City",   "country": "USA",     "lat": 39.0489, "lon": -94.4839,  "alt": 270,  "tz": -5},
    "atlanta":      {"name": "Mercedes-Benz Stadium", "city": "Atlanta",       "country": "USA",     "lat": 33.7553, "lon": -84.4006,  "alt": 290,  "tz": -4},
    "miami":        {"name": "Hard Rock Stadium",     "city": "Miami",         "country": "USA",     "lat": 25.9580, "lon": -80.2389,  "alt": 2,    "tz": -4},
    "new_york":     {"name": "MetLife Stadium",       "city": "New York/NJ",   "country": "USA",     "lat": 40.8136, "lon": -74.0745,  "alt": 3,    "tz": -4},
    "philadelphia": {"name": "Lincoln Financial",     "city": "Philadelphia",  "country": "USA",     "lat": 39.9008, "lon": -75.1675,  "alt": 12,   "tz": -4},
    "boston":       {"name": "Gillette Stadium",      "city": "Boston",        "country": "USA",     "lat": 42.0909, "lon": -71.2643,  "alt": 70,   "tz": -4},
}

# ── Group draw (final draw, 5 Dec 2025) ───────────────────────────────────────
GROUPS: dict[str, list[str]] = {
    "A": ["Mexico", "South Africa", "South Korea", "Czechia"],
    "B": ["Canada", "Bosnia & Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["United States", "Paraguay", "Australia", "Türkiye"],
    "E": ["Germany", "Curaçao", "Ivory Coast", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Iraq", "Norway"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "DR Congo", "Uzbekistan", "Colombia"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

# ── Group-stage schedule (date, group, teamA, teamB, venue_id) ─────────────────
# All 72 matches from the published daily schedule. Dates are 2026.
SCHEDULE: list[tuple[str, str, str, str, str]] = [
    # Group A
    ("2026-06-11", "A", "Mexico", "South Africa", "mexico_city"),
    ("2026-06-11", "A", "South Korea", "Czechia", "guadalajara"),
    ("2026-06-18", "A", "Czechia", "South Africa", "atlanta"),
    ("2026-06-18", "A", "Mexico", "South Korea", "guadalajara"),
    ("2026-06-24", "A", "Czechia", "Mexico", "mexico_city"),
    ("2026-06-24", "A", "South Africa", "South Korea", "monterrey"),
    # Group B
    ("2026-06-12", "B", "Canada", "Bosnia & Herzegovina", "toronto"),
    ("2026-06-13", "B", "Qatar", "Switzerland", "bay_area"),
    ("2026-06-18", "B", "Switzerland", "Bosnia & Herzegovina", "los_angeles"),
    ("2026-06-18", "B", "Canada", "Qatar", "vancouver"),
    ("2026-06-24", "B", "Switzerland", "Canada", "vancouver"),
    ("2026-06-24", "B", "Bosnia & Herzegovina", "Qatar", "seattle"),
    # Group C
    ("2026-06-13", "C", "Brazil", "Morocco", "new_york"),
    ("2026-06-13", "C", "Haiti", "Scotland", "boston"),
    ("2026-06-19", "C", "Scotland", "Morocco", "boston"),
    ("2026-06-19", "C", "Brazil", "Haiti", "philadelphia"),
    ("2026-06-24", "C", "Scotland", "Brazil", "miami"),
    ("2026-06-24", "C", "Morocco", "Haiti", "atlanta"),
    # Group D
    ("2026-06-12", "D", "United States", "Paraguay", "los_angeles"),
    ("2026-06-14", "D", "Australia", "Türkiye", "vancouver"),
    ("2026-06-19", "D", "United States", "Australia", "seattle"),
    ("2026-06-20", "D", "Türkiye", "Paraguay", "bay_area"),
    ("2026-06-25", "D", "Türkiye", "United States", "los_angeles"),
    ("2026-06-25", "D", "Paraguay", "Australia", "bay_area"),
    # Group E
    ("2026-06-14", "E", "Germany", "Curaçao", "houston"),
    ("2026-06-14", "E", "Ivory Coast", "Ecuador", "philadelphia"),
    ("2026-06-20", "E", "Germany", "Ivory Coast", "toronto"),
    ("2026-06-20", "E", "Ecuador", "Curaçao", "kansas_city"),
    ("2026-06-25", "E", "Curaçao", "Ivory Coast", "philadelphia"),
    ("2026-06-25", "E", "Ecuador", "Germany", "new_york"),
    # Group F
    ("2026-06-14", "F", "Netherlands", "Japan", "dallas"),
    ("2026-06-14", "F", "Sweden", "Tunisia", "monterrey"),
    ("2026-06-20", "F", "Netherlands", "Sweden", "houston"),
    ("2026-06-21", "F", "Tunisia", "Japan", "monterrey"),
    ("2026-06-25", "F", "Japan", "Sweden", "dallas"),
    ("2026-06-25", "F", "Tunisia", "Netherlands", "kansas_city"),
    # Group G
    ("2026-06-15", "G", "Belgium", "Egypt", "seattle"),
    ("2026-06-15", "G", "Iran", "New Zealand", "los_angeles"),
    ("2026-06-21", "G", "Belgium", "Iran", "los_angeles"),
    ("2026-06-21", "G", "New Zealand", "Egypt", "vancouver"),
    ("2026-06-26", "G", "Egypt", "Iran", "seattle"),
    ("2026-06-26", "G", "New Zealand", "Belgium", "vancouver"),
    # Group H
    ("2026-06-15", "H", "Spain", "Cape Verde", "atlanta"),
    ("2026-06-15", "H", "Saudi Arabia", "Uruguay", "miami"),
    ("2026-06-21", "H", "Spain", "Saudi Arabia", "atlanta"),
    ("2026-06-21", "H", "Uruguay", "Cape Verde", "miami"),
    ("2026-06-26", "H", "Cape Verde", "Saudi Arabia", "houston"),
    ("2026-06-26", "H", "Uruguay", "Spain", "guadalajara"),
    # Group I
    ("2026-06-16", "I", "France", "Senegal", "new_york"),
    ("2026-06-16", "I", "Iraq", "Norway", "boston"),
    ("2026-06-22", "I", "France", "Iraq", "philadelphia"),
    ("2026-06-22", "I", "Norway", "Senegal", "new_york"),
    ("2026-06-26", "I", "Norway", "France", "boston"),
    ("2026-06-26", "I", "Senegal", "Iraq", "toronto"),
    # Group J
    ("2026-06-16", "J", "Argentina", "Algeria", "kansas_city"),
    ("2026-06-17", "J", "Austria", "Jordan", "bay_area"),
    ("2026-06-22", "J", "Argentina", "Austria", "dallas"),
    ("2026-06-22", "J", "Jordan", "Algeria", "bay_area"),
    ("2026-06-27", "J", "Algeria", "Austria", "kansas_city"),
    ("2026-06-27", "J", "Jordan", "Argentina", "dallas"),
    # Group K
    ("2026-06-17", "K", "Portugal", "DR Congo", "houston"),
    ("2026-06-17", "K", "Uzbekistan", "Colombia", "mexico_city"),
    ("2026-06-23", "K", "Portugal", "Uzbekistan", "houston"),
    ("2026-06-23", "K", "Colombia", "DR Congo", "guadalajara"),
    ("2026-06-27", "K", "Colombia", "Portugal", "miami"),
    ("2026-06-27", "K", "DR Congo", "Uzbekistan", "atlanta"),
    # Group L
    ("2026-06-17", "L", "England", "Croatia", "dallas"),
    ("2026-06-17", "L", "Ghana", "Panama", "toronto"),
    ("2026-06-23", "L", "England", "Ghana", "boston"),
    ("2026-06-23", "L", "Panama", "Croatia", "toronto"),
    ("2026-06-27", "L", "Panama", "England", "new_york"),
    ("2026-06-27", "L", "Croatia", "Ghana", "philadelphia"),
]

# Default sub-burden weights. Sum to 1. The sensitivity analysis stress-tests these.
DEFAULT_WEIGHTS = {"distance": 0.35, "timezone": 0.25, "altitude": 0.25, "recovery": 0.15}

ALT_THRESHOLD = 1500  # metres; above this, altitude is physiologically meaningful


# ── Geometry ──────────────────────────────────────────────────────────────────
def haversine(a: str, b: str) -> float:
    """Great-circle distance in km between two venue ids."""
    va, vb = VENUES[a], VENUES[b]
    R = 6371.0
    p1, p2 = math.radians(va["lat"]), math.radians(vb["lat"])
    dphi = math.radians(vb["lat"] - va["lat"])
    dlam = math.radians(vb["lon"] - va["lon"])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


# ── Per-team itinerary + raw metrics ─────────────────────────────────────────
@dataclass
class TeamTravel:
    team: str
    group: str
    legs: list[dict]          # ordered venues with dates/opponents
    total_km: float
    max_leg_km: float
    tz_changes: int           # summed |Δ UTC offset| across legs
    altitude_load: float      # summed venue altitude over matches at/above threshold
    alt_matches: int          # count of matches at altitude
    min_rest: int             # fewest days between consecutive matches
    mean_rest: float


def _itinerary(team: str) -> list[tuple[str, str, str]]:
    """Ordered (date, venue_id, opponent) for a team's three group matches."""
    rows = []
    for date, _grp, a, b, venue in SCHEDULE:
        if a == team:
            rows.append((date, venue, b))
        elif b == team:
            rows.append((date, venue, a))
    rows.sort(key=lambda r: r[0])
    return rows


def _days_between(d1: str, d2: str) -> int:
    from datetime import date
    y1, m1, day1 = map(int, d1.split("-"))
    y2, m2, day2 = map(int, d2.split("-"))
    return (date(y2, m2, day2) - date(y1, m1, day1)).days


def team_travel(team: str, group: str) -> TeamTravel:
    itin = _itinerary(team)
    legs = []
    total_km = max_leg = 0.0
    tz_changes = 0
    rests: list[int] = []
    for i, (date, venue, opp) in enumerate(itin):
        leg_km = 0.0
        rest = None
        if i > 0:
            prev_date, prev_venue, _ = itin[i - 1]
            leg_km = haversine(prev_venue, venue)
            total_km += leg_km
            max_leg = max(max_leg, leg_km)
            tz_changes += abs(VENUES[venue]["tz"] - VENUES[prev_venue]["tz"])
            rest = _days_between(prev_date, date)
            rests.append(rest)
        legs.append({
            "date": date, "venue": venue, "city": VENUES[venue]["city"],
            "country": VENUES[venue]["country"], "opponent": opp,
            "alt": VENUES[venue]["alt"], "lat": VENUES[venue]["lat"],
            "lon": VENUES[venue]["lon"], "leg_km": round(leg_km), "rest": rest,
        })
    alt_venues = [VENUES[v]["alt"] for _, v, _ in itin if VENUES[v]["alt"] >= ALT_THRESHOLD]
    return TeamTravel(
        team=team, group=group, legs=legs,
        total_km=round(total_km),
        max_leg_km=round(max_leg),
        tz_changes=tz_changes,
        altitude_load=float(sum(alt_venues)),
        alt_matches=len(alt_venues),
        min_rest=min(rests) if rests else 0,
        mean_rest=round(sum(rests) / len(rests), 1) if rests else 0.0,
    )


def all_team_travel() -> list[TeamTravel]:
    out = []
    for grp, teams in GROUPS.items():
        for t in teams:
            out.append(team_travel(t, grp))
    return out


# ── Index construction ────────────────────────────────────────────────────────
def _zscores(values: list[float]) -> list[float]:
    n = len(values)
    mu = sum(values) / n
    var = sum((v - mu) ** 2 for v in values) / n
    sd = math.sqrt(var) or 1.0
    return [(v - mu) / sd for v in values]


def burden_table(weights: dict[str, float] | None = None) -> list[dict]:
    """Composite burden index for all 48 teams under the given weights.

    Each sub-burden is z-scored across the field so they're comparable, then
    combined. 'recovery' enters negatively: less rest = more burden.
    """
    w = weights or DEFAULT_WEIGHTS
    tt = all_team_travel()
    z_dist = _zscores([t.total_km for t in tt])
    z_tz = _zscores([float(t.tz_changes) for t in tt])
    z_alt = _zscores([t.altitude_load for t in tt])
    z_rec = _zscores([-float(t.min_rest) for t in tt])  # shorter rest -> higher burden
    rows = []
    for t, zd, zt, za, zr in zip(tt, z_dist, z_tz, z_alt, z_rec):
        score = w["distance"] * zd + w["timezone"] * zt + w["altitude"] * za + w["recovery"] * zr
        rows.append({
            "team": t.team, "group": t.group,
            "total_km": t.total_km, "max_leg_km": t.max_leg_km,
            "tz_changes": t.tz_changes, "altitude_load": t.altitude_load,
            "alt_matches": t.alt_matches, "min_rest": t.min_rest,
            "mean_rest": t.mean_rest, "legs": t.legs,
            "z": {"distance": round(zd, 3), "timezone": round(zt, 3),
                  "altitude": round(za, 3), "recovery": round(zr, 3)},
            "burden": round(score, 4),
        })
    rows.sort(key=lambda r: r["burden"], reverse=True)
    for rank, r in enumerate(rows, 1):
        r["rank"] = rank
    return rows


def group_burden() -> list[dict]:
    """Mean burden per group — 'who got screwed by the draw'."""
    table = burden_table()
    by_group: dict[str, list[float]] = {}
    for r in table:
        by_group.setdefault(r["group"], []).append(r["burden"])
    rows = [{"group": g, "mean_burden": round(sum(v) / len(v), 4)} for g, v in by_group.items()]
    rows.sort(key=lambda r: r["mean_burden"], reverse=True)
    return rows


# ── Sensitivity analysis ──────────────────────────────────────────────────────
def _kendall_tau(rank_a: dict[str, int], rank_b: dict[str, int]) -> float:
    """Kendall's tau between two team->rank maps. +1 identical, -1 reversed."""
    teams = list(rank_a)
    conc = disc = 0
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            ti, tj = teams[i], teams[j]
            s = (rank_a[ti] - rank_a[tj]) * (rank_b[ti] - rank_b[tj])
            if s > 0:
                conc += 1
            elif s < 0:
                disc += 1
    return (conc - disc) / (conc + disc) if (conc + disc) else 1.0


def sensitivity(scenarios: dict[str, dict[str, float]] | None = None) -> dict:
    """Does the ranking survive reweighting? Compare default vs alternative weightings.

    Returns per-scenario rank correlation to the default plus, for each team, the
    spread of ranks it occupies across all scenarios (small spread = robust).
    """
    if scenarios is None:
        scenarios = {
            "equal":          {"distance": .25, "timezone": .25, "altitude": .25, "recovery": .25},
            "distance_heavy": {"distance": .55, "timezone": .20, "altitude": .15, "recovery": .10},
            "altitude_heavy": {"distance": .20, "timezone": .15, "altitude": .55, "recovery": .10},
            "timezone_heavy": {"distance": .20, "timezone": .55, "altitude": .15, "recovery": .10},
            "recovery_heavy": {"distance": .25, "timezone": .15, "altitude": .15, "recovery": .45},
        }
    default_rank = {r["team"]: r["rank"] for r in burden_table(DEFAULT_WEIGHTS)}
    per_scenario = []
    team_ranks: dict[str, list[int]] = {t: [default_rank[t]] for t in default_rank}
    for name, w in scenarios.items():
        rank = {r["team"]: r["rank"] for r in burden_table(w)}
        per_scenario.append({"scenario": name, "tau": round(_kendall_tau(default_rank, rank), 3)})
        for t, rk in rank.items():
            team_ranks[t].append(rk)
    stability = []
    for t, ranks in team_ranks.items():
        stability.append({
            "team": t, "best": min(ranks), "worst": max(ranks),
            "spread": max(ranks) - min(ranks), "default": default_rank[t],
        })
    stability.sort(key=lambda r: r["default"])
    mean_tau = round(sum(s["tau"] for s in per_scenario) / len(per_scenario), 3)
    return {"scenarios": per_scenario, "mean_tau": mean_tau, "stability": stability}
