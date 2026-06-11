"""The freeze protocol.

The model's per-match win/draw/loss probabilities are written **once, before kickoff,
timestamped, and never edited** — that immutability is the only thing separating an honest
evaluation from hindsight. ``mlfootball.market.db.freeze_model`` enforces write-once at the
storage layer; this module produces the numbers and decides which matches are due to freeze.

The probabilities come straight from the resurrected Dixon-Coles engine
(``mlfootball.ratings``): fit attack/defence strengths on international-results history,
build the scoreline grid for the fixture, and collapse it to P(home)/P(draw)/P(away) via
``TeamStrengths.outcome_probs``. The model spec is fixed (``MODEL_VERSION``); each freeze
records an ``inputs_hash`` of the data snapshot it was fit on.

**No market leakage.** The only input is match history — see ``MODEL_INPUTS`` and the
assertion in ``_fit`` that nothing odds-derived can enter. A model that read the odds and
then "beat" them would be circular; this guarantees it can't.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pandas as pd

from mlfootball import data, ratings
from mlfootball.market import db

MODEL_VERSION = "dixon-coles-1.0"
SINCE = "2006-01-01"          # modern-era fit window (matches the engine's __main__)
HOSTS = frozenset({"Mexico", "Canada", "United States"})
MODEL_INPUTS = ["international_results_history"]  # provably no market features

# fixture display name (mlfootball.travel) → results.csv convention
MODEL_NAME = {
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
}


def _assert_no_leakage() -> None:
    banned = ("odds", "market", "book", "implied", "vig", "price")
    for feat in MODEL_INPUTS:
        if any(b in feat.lower() for b in banned):
            raise AssertionError(f"market feature leaked into model inputs: {feat!r}")


def _fit(asof: pd.Timestamp):
    _assert_no_leakage()
    df = data.load()
    df = df[df.date >= SINCE]
    strengths = ratings.fit(df, asof=asof)
    snapshot = {
        "model_version": MODEL_VERSION,
        "inputs": MODEL_INPUTS,
        "fit_since": SINCE,
        "asof": str(asof.date()),
        "n_matches": int((df.date <= asof).sum()),
        "data_max_date": str(df.date.max().date()),
        "n_teams": len(strengths.teams),
        "home_adv": round(strengths.home_adv, 4),
        "rho": round(strengths.rho, 4),
    }
    inputs_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()[:16]
    return strengths, inputs_hash, snapshot


def _model_team(name: str) -> str:
    return MODEL_NAME.get(name, name)


def freeze_upcoming(within_hours: int = 36, con=None, now: datetime | None = None) -> dict:
    """Freeze every not-yet-frozen match kicking off within ``within_hours``. Idempotent:
    matches already frozen for ``MODEL_VERSION`` are skipped by the write-once guard."""
    own = con is None
    con = con or db.init_db()
    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(hours=within_hours)

    rows = con.execute(
        """SELECT m.match_id, m.home, m.away, m.kickoff_utc
           FROM matches m
           LEFT JOIN frozen_model f
             ON f.match_id = m.match_id AND f.model_version = ?
           WHERE f.match_id IS NULL
             AND m.kickoff_utc > ? AND m.kickoff_utc <= ?""",
        (MODEL_VERSION, db.utcnow(), horizon.replace(microsecond=0).isoformat().replace("+00:00", "Z")),
    ).fetchall()
    if not rows:
        if own:
            con.close()
        return {"frozen": 0, "skipped": 0, "missing_teams": []}

    strengths, inputs_hash, snapshot = _fit(pd.Timestamp(now.date()))
    known = set(strengths.teams)
    frozen, skipped, missing = 0, 0, []
    for r in rows:
        h, a = _model_team(r["home"]), _model_team(r["away"])
        if h not in known or a not in known:
            missing.append((r["match_id"], h if h not in known else a))
            continue
        p = strengths.outcome_probs(h, a, neutral=True, hosts=HOSTS)
        wrote = db.freeze_model(
            con, match_id=r["match_id"], model_version=MODEL_VERSION,
            p_home=p["home"], p_draw=p["draw"], p_away=p["away"], inputs_hash=inputs_hash)
        frozen += int(wrote)
        skipped += int(not wrote)
    if own:
        con.close()
    return {"frozen": frozen, "skipped": skipped, "missing_teams": missing,
            "model_snapshot": snapshot}


def main():
    ap = argparse.ArgumentParser(description="Freeze model probabilities for upcoming matches.")
    ap.add_argument("--within-hours", type=int, default=36)
    args = ap.parse_args()
    out = freeze_upcoming(within_hours=args.within_hours)
    print(f"froze {out['frozen']} match(es), skipped {out['skipped']} already-frozen.")
    if out["missing_teams"]:
        print("  unresolved teams (no rating):", out["missing_teams"])
    if out.get("model_snapshot"):
        s = out["model_snapshot"]
        print(f"  model {s['model_version']} fit on {s['n_matches']:,} matches "
              f"(home_adv={s['home_adv']}, rho={s['rho']}), inputs={s['inputs']}")


if __name__ == "__main__":
    main()
