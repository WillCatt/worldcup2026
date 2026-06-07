"""Has the football world come together over time, or stayed apart?

Tracks the *cross-confederation* share of internationals through history: of all the games
played in a given year, what fraction crossed continents? The answer is not a tidy upward
line -- intercontinental play climbed for a century, peaked in the 1990s, and has since
pulled back as confederations built out their own packed calendars.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .network import load_confederations


def cross_share_over_time(df: pd.DataFrame, start_year: int = 1930,
                          conf: dict[str, str] | None = None) -> dict:
    """Annual + per-decade cross-confederation match share since ``start_year``.

    Only games between two *mapped* national teams count (both ends have a confederation),
    so the denominator is comparable across eras. Returns annual points (for a smooth line)
    and decade aggregates (for labelled markers).
    """
    conf = conf or load_confederations()
    d = df.copy()
    d["year"] = d.date.dt.year
    cu = d.home_team.map(conf)
    cv = d.away_team.map(conf)
    keep = cu.notna() & cv.notna() & (d.year >= start_year)
    d = d[keep]
    d["cross"] = (cu[keep].values != cv[keep].values)

    annual = []
    for yr, g in d.groupby("year"):
        annual.append({"year": int(yr), "n": int(len(g)),
                       "cross": round(float(g.cross.mean()), 4)})

    d["decade"] = (d.year // 10) * 10
    decades = []
    for dec, g in d.groupby("decade"):
        if len(g) < 50:
            continue
        decades.append({"decade": int(dec), "n": int(len(g)),
                        "cross": round(float(g.cross.mean()), 4)})

    peak = max(decades, key=lambda r: r["cross"])
    latest = decades[-1]
    return {
        "annual": annual,
        "decades": decades,
        "peak": peak,
        "latest": latest,
        "start_year": start_year,
    }
