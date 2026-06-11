"""Synthetic mid-tournament data for building and previewing the page.

The live Sportsbet capture only runs on William's machine, and a portfolio page still needs
to be designed against realistic, populated data. This dev tool fabricates a plausible
"ten days in" state into a SEPARATE ``data/demo.sqlite`` (never the live ``odds.sqlite``) and
runs the *real* exporter over it, so every chart can be built and the export path is
exercised end-to-end. The output ``market.json`` is stamped ``meta.synthetic = true`` and the
page shows a clear preview banner; the real pipeline overwrites it with captured data.

The market model is deliberately honest about the thesis: a hidden "truth" probability is
drawn near the model's frozen probability, the market's *closing* line tracks that truth more
tightly than the model does, opening is noisier, and outcomes are sampled from truth. So the
closing line beats the model on Brier in expectation — exactly the result the piece expects.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from mlfootball import data, ratings
from mlfootball.market import db, export, fixtures, model_freeze

DEMO_DB = Path(__file__).resolve().parents[2] / "data" / "demo.sqlite"
ASOF = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)   # ~10 days in
OVERROUND = 0.05
RNG = random.Random(7)


def _dirichlet(p, conc):
    g = [RNG.gammavariate(max(pi, 1e-3) * conc, 1.0) for pi in p]
    s = sum(g)
    return [x / s for x in g]


def _to_odds(probs):
    """Add overround proportionally and invert to decimal odds."""
    inflated = [pi * (1 + OVERROUND) for pi in probs]
    return [round(1.0 / pi, 2) for pi in inflated]


def _snap_times(kickoff: datetime):
    """Opening (~14 days out) through the tightening cadence to kickoff."""
    times, t = [], kickoff - timedelta(days=14)
    while t < kickoff:
        times.append(t)
        h = (kickoff - t).total_seconds() / 3600
        step = 0.25 if h <= 2 else (1 if h <= 24 else 6)
        t = t + timedelta(hours=step)
    return times


def seed():
    if DEMO_DB.exists():
        DEMO_DB.unlink()
    con = db.init_db(DEMO_DB)
    fixtures.seed(con)

    # real engine fit, as of ASOF
    df = data.load(); df = df[df.date >= model_freeze.SINCE]
    strengths = ratings.fit(df, asof=pd.Timestamp(ASOF.date()))
    known = set(strengths.teams)

    matches = con.execute("SELECT match_id, home, away, kickoff_utc FROM matches").fetchall()
    for m in matches:
        h, a = model_freeze._model_team(m["home"]), model_freeze._model_team(m["away"])
        if h not in known or a not in known:
            continue
        ko = datetime.fromisoformat(m["kickoff_utc"].replace("Z", "+00:00"))
        model_p = strengths.outcome_probs(h, a, neutral=True, hosts=model_freeze.HOSTS)
        mp = [model_p["home"], model_p["draw"], model_p["away"]]

        # hidden truth near the model; the market closing line tracks truth more tightly
        truth = _dirichlet(mp, conc=80)
        # freeze the model before kickoff
        if ko > ASOF:                              # upcoming: freeze now, no result
            db.freeze_model(con, match_id=m["match_id"], model_version=model_freeze.MODEL_VERSION,
                            p_home=mp[0], p_draw=mp[1], p_away=mp[2],
                            frozen_at=(ko - timedelta(hours=24)).isoformat().replace("+00:00", "Z"))
        else:                                      # already played
            db.freeze_model(con, match_id=m["match_id"], model_version=model_freeze.MODEL_VERSION,
                            p_home=mp[0], p_draw=mp[1], p_away=mp[2],
                            frozen_at=(ko - timedelta(hours=24)).isoformat().replace("+00:00", "Z"))

        # market drift: opening noisy → closing ≈ truth; backstop = primary + small offset
        for ti, t in enumerate(_snap_times(ko)):
            if t > ASOF:
                break
            frac = ti / max(len(_snap_times(ko)) - 1, 1)     # 0 → 1 toward kickoff
            blend = [(1 - frac) * o + frac * tr
                     for o, tr in zip(_dirichlet(mp, 25), truth)]
            blend = _dirichlet(blend, 600)                    # light tick noise
            sb = _to_odds(blend)
            db.insert_snapshot(con, match_id=m["match_id"], book="sportsbet",
                               scrape_ts=t.isoformat().replace("+00:00", "Z"),
                               home_dec=sb[0], draw_dec=sb[1], away_dec=sb[2])
            tab = _to_odds(_dirichlet(blend, 400))
            db.insert_snapshot(con, match_id=m["match_id"], book="backstop:tab",
                               scrape_ts=t.isoformat().replace("+00:00", "Z"),
                               home_dec=tab[0], draw_dec=tab[1], away_dec=tab[2])

        # settle matches that have kicked off, sampling the outcome from truth
        if ko <= ASOF:
            r = RNG.random()
            outcome = "home" if r < truth[0] else ("draw" if r < truth[0] + truth[1] else "away")
            hg, ag = ({"home": (2, 0), "draw": (1, 1), "away": (0, 2)})[outcome]
            db.record_result(con, match_id=m["match_id"], home_goals=hg, away_goals=ag)
    con.commit()

    payload = export.build(con)
    payload["meta"]["synthetic"] = True
    payload["meta"]["synthetic_note"] = (
        "Preview data — fabricated mid-tournament state for layout. Replaced by live capture.")
    payload["meta"]["demo_asof"] = ASOF.isoformat().replace("+00:00", "Z")
    out = export.write(payload)
    con.close()
    return out, payload


if __name__ == "__main__":
    out, pay = seed()
    sb = pay["scoreboard"]["series"]
    print(f"wrote synthetic {out} — N={pay['meta']['n_settled']} settled")
    for s in ("model", "closing", "opening", "uniform"):
        d = sb[s]
        if d["mean_brier"] is not None:
            print(f"  {s:<8} N={d['n']:<3} Brier={d['mean_brier']:.4f} logloss={d['mean_logloss']:.4f}")
    nn = pay["scoreboard"]["n_needed"]
    print(f"  model edge over closing: {nn['mean_edge']} (sd {nn['sd']}), "
          f"N for significance ≈ {nn['n_for_signif']}")
