"""Monte Carlo the 2026 World Cup from fitted team strengths.

Each replication: simulate all group matches from the goals model, rank groups, take
the 8 best third-placed teams, build the bracket, play the knockout, record how far
each team gets. Aggregate over many replications -> per-team odds of reaching each
round and winning the trophy.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from src import data, ratings, tournament

OUTPUT = Path(__file__).resolve().parent.parent / "output"
ROUNDS = ["R32", "R16", "QF", "SF", "F", "W"]  # reached-at-least milestones


def _sample_score(strengths: ratings.TeamStrengths, home: str, away: str, rng) -> tuple[int, int]:
    """Draw a scoreline from the model (neutral venue)."""
    grid = strengths.score_matrix(home, away, neutral=True)
    flat = grid.ravel()
    k = rng.choice(flat.size, p=flat / flat.sum())
    n = grid.shape[1]
    return divmod(int(k), n)


def _knockout_winner(strengths, home, away, rng) -> str:
    """Single match; if drawn, decide by a coin weighted to the stronger side
    (proxy for extra-time/penalties)."""
    hg, ag = _sample_score(strengths, home, away, rng)
    if hg > ag:
        return home
    if ag > hg:
        return away
    p = strengths.outcome_probs(home, away)
    edge = p["home"] / (p["home"] + p["away"]) if (p["home"] + p["away"]) > 0 else 0.5
    return home if rng.random() < edge else away


def simulate_once(strengths, groups, rng) -> dict[str, str]:
    """Return {team: furthest_round_reached}."""
    reached = {}
    standings = {}
    thirds = []  # (group, team, pts, gd, gf)

    for g, teams in groups.items():
        pts = dict.fromkeys(teams, 0)
        gf = dict.fromkeys(teams, 0)
        ga = dict.fromkeys(teams, 0)
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                a, b = teams[i], teams[j]
                sa, sb = _sample_score(strengths, a, b, rng)
                gf[a] += sa; ga[a] += sb; gf[b] += sb; ga[b] += sa
                if sa > sb:
                    pts[a] += 3
                elif sb > sa:
                    pts[b] += 3
                else:
                    pts[a] += 1; pts[b] += 1
        # Rank: points, goal difference, goals for, then random tiebreak.
        order = sorted(teams, key=lambda t: (pts[t], gf[t] - ga[t], gf[t], rng.random()), reverse=True)
        standings[g] = order
        thirds.append((g, order[2], pts[order[2]], gf[order[2]] - ga[order[2]], gf[order[2]]))
        for t in teams:
            reached[t] = "Group"  # eliminated in group unless they advance below

    # 8 best third-placed teams.
    thirds.sort(key=lambda x: (x[2], x[3], x[4], rng.random()), reverse=True)
    qualifying_thirds = thirds[:8]
    third_team_by_group = {g: team for g, team, *_ in qualifying_thirds}
    qualified_groups = [g for g, *_ in qualifying_thirds]

    assign = tournament.assign_thirds(qualified_groups, rng)
    if assign is None:  # pathological; fall back to order-preserving
        assign = dict(zip(tournament.THIRD_SLOTS, qualified_groups))

    # Resolve R32 slots to concrete teams and play the round.
    winners = {}
    for m, (sa, sb) in tournament.R32.items():
        a = standings[sa[1]][0] if sa[0] == "W" else standings[sa[1]][1] if sa[0] == "R" else third_team_by_group[assign[m]]
        b = standings[sb[1]][0] if sb[0] == "W" else standings[sb[1]][1] if sb[0] == "R" else third_team_by_group[assign[m]]
        for t in (a, b):
            reached[t] = "R32"
        winners[m] = _knockout_winner(strengths, a, b, rng)

    # Knockout flow.
    for m, (x, y) in tournament.KO.items():
        a, b = winners[x], winners[y]
        rnd = tournament.ROUND_OF[m]
        for t in (a, b):
            reached[t] = rnd
        winners[m] = _knockout_winner(strengths, a, b, rng)
    reached[winners[104]] = "W"
    return reached


def run(n: int = 50000, since: str = "2006-01-01", seed: int = 42) -> dict:
    df = data.load()
    df = df[df.date >= since]
    strengths = ratings.fit(df)
    groups = tournament.load_groups()

    # Validate every WC team has a rating.
    missing = [t for t in tournament.all_teams() if t not in strengths.attack]
    if missing:
        raise SystemExit(f"Missing ratings for: {missing}\n(add NAME_ALIASES in tournament.py)")

    rng = np.random.default_rng(seed)
    order = ["Group", "R32", "R16", "QF", "SF", "F", "W"]
    rank = {r: i for i, r in enumerate(order)}
    counts = defaultdict(lambda: np.zeros(len(order), dtype=int))

    for _ in range(n):
        for t, r in simulate_once(strengths, groups, rng).items():
            counts[t][rank[r]] += 1

    # Convert to "reached at least round X" probabilities.
    teams = tournament.all_teams()
    table = {}
    for t in teams:
        c = counts[t]
        cum = np.cumsum(c[::-1])[::-1]  # at-least counts
        table[t] = {
            "group_of": next(g for g, ts in groups.items() if t in ts),
            "advance": round(cum[rank["R32"]] / n, 4),   # out of group
            "R16": round(cum[rank["R16"]] / n, 4),
            "QF": round(cum[rank["QF"]] / n, 4),
            "SF": round(cum[rank["SF"]] / n, 4),
            "final": round(cum[rank["F"]] / n, 4),
            "win": round(c[rank["W"]] / n, 4),
        }
    out = {
        "n_sims": n,
        "fit_since": since,
        "teams": dict(sorted(table.items(), key=lambda kv: kv[1]["win"], reverse=True)),
    }
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "forecast.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return out


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    out = run(n=n)
    print(f"\n{out['n_sims']:,} sims. Title odds (top 16):\n")
    for t, row in list(out["teams"].items())[:16]:
        print(f"  {t:<16} win {row['win']*100:5.1f}%   final {row['final']*100:5.1f}%   "
              f"advance {row['advance']*100:5.1f}%   (Grp {row['group_of']})")
