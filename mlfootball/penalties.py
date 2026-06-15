"""Penalty shootouts as a game of mixed strategies.

The old version of this piece had to confess it couldn't see where keepers dive —
StatsBomb open data only records a dive when it ends in a save. This rebuild uses a
World Cup-specific corpus that *does* record the keeper's dive on every kick, so the
penalty becomes what game theory always said it was: a 3x3 payoff matrix of where the
ball goes versus which way the keeper commits.

Source: every men's World Cup shootout kick 1982->2022 (Llanderos via the Bizarro
GitHub mirror), `data/raw/WorldCupShootouts.csv`. Columns:
  Game_id, Team, Zone(1-9), Foot(L/R), Keeper(L/C/R dive), OnTarget, Goal,
  Penalty_Number, Elimination.
Both the shot Zone and the Keeper dive are coded from the *shooter's view of the goal*
(the dataset's Goal.png / Keeper.png), so "did the keeper pick the right side" is a
direct comparison.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

CSV = Path(__file__).resolve().parent.parent / "data" / "raw" / "WorldCupShootouts.csv"

# Zone 1-9 grid (shooter's view) -> horizontal third and vertical band.
ZONE_COL = {1: "L", 2: "C", 3: "R", 4: "L", 5: "C", 6: "R", 7: "L", 8: "C", 9: "R"}
ZONE_ROW = {1: "T", 2: "T", 3: "T", 4: "M", 5: "M", 6: "M", 7: "B", 8: "B", 9: "B"}
DIRS = ["L", "C", "R"]


def load_kicks() -> pd.DataFrame:
    """Clean kick table. Keeps only kicks with a known zone + keeper dive + outcome."""
    df = pd.read_csv(CSV)
    df["Keeper"] = df["Keeper"].astype(str).str.upper().str.strip()
    df.loc[~df["Keeper"].isin(DIRS), "Keeper"] = np.nan
    df = df.dropna(subset=["Zone", "Keeper", "Goal"]).copy()
    df["Zone"] = df["Zone"].astype(int)
    df["ShotDir"] = df["Zone"].map(ZONE_COL)
    df["ShotHt"] = df["Zone"].map(ZONE_ROW)
    df["Goal"] = df["Goal"].astype(int)
    df["KeeperRight"] = df["ShotDir"] == df["Keeper"]  # guessed the side
    return df


def _wilson(k: int, n: int) -> tuple[float, float]:
    """Wilson 95% interval for a proportion — honest with small n."""
    if n == 0:
        return (0.0, 0.0)
    lo, hi = stats.binomtest(k, n).proportion_ci(confidence_level=0.95, method="wilson")
    return (round(lo, 4), round(hi, 4))


def _dist(s: pd.Series, keys=DIRS) -> dict:
    vc = s.value_counts(normalize=True)
    return {k: round(float(vc.get(k, 0.0)), 4) for k in keys}


def payoff_matrix(df: pd.DataFrame) -> dict:
    """3x3 goal-rate matrix: shot direction (rows) x keeper dive (cols)."""
    cells = []
    for sd in DIRS:
        for kd in DIRS:
            sub = df[(df.ShotDir == sd) & (df.Keeper == kd)]
            n = len(sub)
            cells.append({
                "shot": sd, "keeper": kd, "n": n,
                "conv": round(float(sub.Goal.mean()), 4) if n else None,
            })
    return {"dirs": DIRS, "cells": cells}


def coin_flip(df: pd.DataFrame) -> dict:
    """How often the keeper reads the side, and what it's worth."""
    right, wrong = df[df.KeeperRight], df[~df.KeeperRight]
    return {
        "keeper_correct_rate": round(float(df.KeeperRight.mean()), 4),
        "n_right": int(len(right)), "n_wrong": int(len(wrong)),
        "conv_when_right": round(float(right.Goal.mean()), 4),
        "conv_when_wrong": round(float(wrong.Goal.mean()), 4),
        "keeper_dive_dist": _dist(df.Keeper),
        "shot_dist": _dist(df.ShotDir),
    }


def nash_indifference(df: pd.DataFrame) -> dict:
    """Mixed-strategy prediction: a taker at equilibrium scores equally with every
    direction they use. Test whether conversion is flat across L/C/R."""
    by_dir = []
    for d in DIRS:
        sub = df[df.ShotDir == d]
        n, k = len(sub), int(sub.Goal.sum())
        lo, hi = _wilson(k, n)
        by_dir.append({
            "dir": d, "n": n, "conv": round(float(sub.Goal.mean()), 4),
            "usage": round(n / len(df), 4), "lo": lo, "hi": hi,
        })
    ct = pd.crosstab(df.ShotDir, df.Goal)
    chi2, p, dof, _ = stats.chi2_contingency(ct)
    convs = [b["conv"] for b in by_dir]
    return {
        "by_dir": by_dir,
        "chisq": {"chi2": round(float(chi2), 3), "p": round(float(p), 4), "dof": int(dof)},
        "spread_pp": round((max(convs) - min(convs)) * 100, 1),
    }


def abandoned_centre(df: pd.DataFrame) -> dict:
    """Both sides under-use the middle — and a centre shot against a committed (diving)
    keeper is nearly automatic."""
    centre_shots = df[df.ShotDir == "C"]
    committed = centre_shots[centre_shots.Keeper != "C"]
    return {
        "keeper_stays_centre": round(float((df.Keeper == "C").mean()), 4),
        "shooter_centre_usage": round(float((df.ShotDir == "C").mean()), 4),
        "centre_vs_committed_conv": round(float(committed.Goal.mean()), 4),
        "centre_vs_committed_n": int(len(committed)),
        "centre_vs_centre_conv": round(float(centre_shots[centre_shots.Keeper == "C"].Goal.mean()), 4),
        "centre_vs_centre_n": int((centre_shots.Keeper == "C").sum()),
    }


def footedness(df: pd.DataFrame) -> dict:
    """The one readable tell: a right-footer's across-body strike favours the viewer-left."""
    out = []
    for foot in ["R", "L"]:
        sub = df[df.Foot == foot]
        if not len(sub):
            continue
        out.append({"foot": foot, "n": int(len(sub)), "dist": _dist(sub.ShotDir)})
    return {"by_foot": out}


def pressure(df: pd.DataFrame) -> dict:
    """Honest nulls: order number and must-score elimination kicks."""
    by_kick = []
    for num, sub in df.groupby("Penalty_Number"):
        n, k = len(sub), int(sub.Goal.sum())
        if n < 5:
            continue
        lo, hi = _wilson(k, n)
        by_kick.append({"num": int(num), "n": n, "conv": round(float(sub.Goal.mean()), 4),
                        "lo": lo, "hi": hi})
    elim = df.dropna(subset=["Elimination"])
    must = elim[elim.Elimination == 1]
    rest = elim[elim.Elimination == 0]
    return {
        "by_kick": by_kick,
        "elimination": {
            "must_conv": round(float(must.Goal.mean()), 4), "must_n": int(len(must)),
            "rest_conv": round(float(rest.Goal.mean()), 4), "rest_n": int(len(rest)),
        },
    }


def game_deck(df: pd.DataFrame) -> dict:
    """Real kicks for the 'you're the keeper' game + the data-grounded resolution rule.

    Resolution: the player picks a dive direction. If it misses the shot's column the
    keeper is out of the play (a goal); if it matches, the save lands with the empirical
    rate observed when keepers committed to that direction's zone."""
    on = df[df.OnTarget != 0]
    # P(save | keeper dives the correct side) per zone, with a direction-level fallback.
    save_when_right = {}
    for z in range(1, 10):
        zsub = on[(on.Zone == z) & (on.KeeperRight)]
        save_when_right[z] = round(1 - float(zsub.Goal.mean()), 4) if len(zsub) >= 4 else None
    dir_save = {}
    for d in DIRS:
        dsub = on[(on.ShotDir == d) & (on.KeeperRight)]
        dir_save[d] = round(1 - float(dsub.Goal.mean()), 4) if len(dsub) else 0.0
    kicks = [{"zone": int(r.Zone), "dir": r.ShotDir, "ht": r.ShotHt,
              "keeper": r.Keeper, "scored": int(r.Goal)}
             for r in on.itertuples()]
    real_save = round(1 - float(df.Goal.mean()), 4)
    return {
        "kicks": kicks,
        "save_when_right_by_zone": save_when_right,
        "save_when_right_by_dir": dir_save,
        "real_keeper_save_rate": real_save,
    }


def build_export() -> dict:
    df = load_kicks()
    raw = pd.read_csv(CSV)
    off = df[df.OnTarget == 0]
    misses = df[df.Goal == 0]
    cf = coin_flip(df)
    nash = nash_indifference(df)
    ac = abandoned_centre(df)
    return {
        "meta": {
            "n_total": int(len(raw)),
            "n_clean": int(len(df)),
            "n_games": int(df.Game_id.nunique()),
            "year_min": 1982, "year_max": 2022,
            "overall_conv": round(float(df.Goal.mean()), 4),
            "off_target_rate": round(float((df.OnTarget == 0).mean()), 4),
            "unforced_miss_share": round(float((misses.OnTarget == 0).mean()), 4) if len(misses) else 0.0,
        },
        "matrix": payoff_matrix(df),
        "coin_flip": cf,
        "nash": nash,
        "centre": ac,
        "foot": footedness(df),
        "pressure": pressure(df),
        "game": game_deck(df),
        "sources": [
            {"label": "World Cup Penalty Shootouts 1982-2022 (Llanderos / Bizarro mirror)",
             "url": "https://github.com/LuigiBizarro/world-cup-penalty-shootouts-82-22"},
            {"label": "Chiappori, Levitt & Groseclose (2002); Palacios-Huerta (2003) — penalties as mixed-strategy games",
             "url": "https://www.aeaweb.org/articles?id=10.1257/00028280260344678"},
        ],
    }


def export(path: Path | None = None) -> dict:
    out = build_export()
    path = path or Path(__file__).resolve().parent.parent / "site" / "data" / "penalties.json"
    path.write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    d = export()
    print(f"penalties.json written: {d['meta']['n_clean']} clean kicks, "
          f"{d['meta']['n_games']} shootouts, keeper correct "
          f"{d['coin_flip']['keeper_correct_rate']:.1%}, Nash p={d['nash']['chisq']['p']}")
