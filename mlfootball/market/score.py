"""Scoring: how wrong was the model, and how wrong was the market?

Four series are scored on the *identical* set of settled matches:
  (a) the frozen model,
  (b) de-vigged **closing** odds  — the benchmark to beat,
  (c) de-vigged **opening** odds  — earlier, worse; opening-vs-closing is the market learning,
  (d) a uniform 1/3-1/3-1/3 dummy — the floor any real forecaster must clear.

Two proper scoring rules: the multiclass **Brier score** (Σ(pᵢ−yᵢ)², range 0–2) and
**log-loss** (−log p of the realised outcome). Both are reported cumulatively *and* on a
rolling window, and **never without N** — early in a tournament a one-match lead over the
closing line is noise, and the page is built to say so.

Calibration pools every (predicted-probability, outcome) pair across the three outcomes into
reliability bins with their counts shown, because the bins are thin early and that
uncertainty is part of the honest story. ``detect_steam`` flags sharp implied-probability
moves within a short window — the market suddenly repricing on team news.
"""
from __future__ import annotations

import math
from datetime import datetime

from mlfootball.market import db, devig

OUTCOMES = ("home", "draw", "away")
UNIFORM = (1 / 3, 1 / 3, 1 / 3)


# ── scoring rules ────────────────────────────────────────────────────────────
def brier(p: tuple[float, float, float], outcome: str) -> float:
    y = [1.0 if o == outcome else 0.0 for o in OUTCOMES]
    return sum((p[i] - y[i]) ** 2 for i in range(3))


def logloss(p: tuple[float, float, float], outcome: str, eps: float = 1e-15) -> float:
    pi = p[OUTCOMES.index(outcome)]
    return -math.log(max(pi, eps))


# ── pulling probabilities out of the DB ──────────────────────────────────────
def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _market_snapshot_probs(con, match_id, book, which, method) -> tuple | None:
    """De-vigged (home,draw,away) from the opening or closing snapshot of a book, where
    'closing' is the last snapshot strictly before kickoff."""
    ko = con.execute("SELECT kickoff_utc FROM matches WHERE match_id=?", (match_id,)).fetchone()
    if ko is None:
        return None
    order = "ASC" if which == "opening" else "DESC"
    row = con.execute(
        f"""SELECT home_dec, draw_dec, away_dec FROM odds_snapshots
            WHERE match_id=? AND book=? AND scrape_ts < ?
              AND home_dec>1 AND draw_dec>1 AND away_dec>1
            ORDER BY scrape_ts {order} LIMIT 1""",
        (match_id, book, ko["kickoff_utc"]),
    ).fetchone()
    if row is None:
        return None
    return tuple(devig.devig([row["home_dec"], row["draw_dec"], row["away_dec"]], method))


def _model_probs(con, match_id, model_version) -> tuple | None:
    r = con.execute(
        "SELECT p_home,p_draw,p_away FROM frozen_model WHERE match_id=? AND model_version=?",
        (match_id, model_version)).fetchone()
    return (r["p_home"], r["p_draw"], r["p_away"]) if r else None


def _probs_for(con, series, match_id, *, book, model_version, method):
    if series == "model":
        return _model_probs(con, match_id, model_version)
    if series == "closing":
        return _market_snapshot_probs(con, match_id, book, "closing", method)
    if series == "opening":
        return _market_snapshot_probs(con, match_id, book, "opening", method)
    if series == "uniform":
        return UNIFORM
    raise ValueError(series)


# ── series scoring ───────────────────────────────────────────────────────────
def score_all(con=None, *, book="sportsbet", model_version="dixon-coles-1.0",
              method="shin", rolling=5) -> dict:
    """Score every series on the common set of settled matches that have BOTH a frozen model
    probability and a closing market price (so the comparison is strictly like-for-like)."""
    own = con is None
    con = con or db.connect()

    settled = con.execute(
        """SELECT r.match_id, r.outcome, m.kickoff_utc, m.home, m.away, m.grp, m.stage
           FROM results r JOIN matches m USING (match_id)
           ORDER BY m.kickoff_utc""").fetchall()

    series_names = ("model", "closing", "opening", "uniform")
    common = []
    for r in settled:
        probs = {s: _probs_for(con, s, r["match_id"], book=book,
                               model_version=model_version, method=method)
                 for s in series_names}
        # require model + closing for inclusion; opening optional (early markets thin)
        if probs["model"] is None or probs["closing"] is None:
            continue
        common.append((r, probs))

    out = {"book": book, "model_version": model_version, "devig": method,
           "n": len(common), "series": {}, "per_match": [], "matches_scored": []}

    for s in series_names:
        cum_b = cum_l = 0.0
        n = 0
        history = []
        for r, probs in common:
            p = probs[s]
            if p is None:
                history.append(None)
                continue
            n += 1
            b, l = brier(p, r["outcome"]), logloss(p, r["outcome"])
            cum_b += b
            cum_l += l
            history.append({"match_id": r["match_id"], "brier": b, "logloss": l,
                            "cum_brier": cum_b / n, "cum_logloss": cum_l / n, "n": n})
        roll = [h for h in history if h]
        rolling_brier = (sum(x["brier"] for x in roll[-rolling:]) / min(rolling, len(roll))
                         if roll else None)
        out["series"][s] = {
            "n": n,
            "mean_brier": cum_b / n if n else None,
            "mean_logloss": cum_l / n if n else None,
            "rolling_brier": rolling_brier,
            "history": history,
        }

    # per-match "who was less wrong" (model vs closing)
    for r, probs in common:
        bm = brier(probs["model"], r["outcome"])
        bc = brier(probs["closing"], r["outcome"])
        out["per_match"].append({
            "match_id": r["match_id"], "home": r["home"], "away": r["away"],
            "grp": r["grp"], "stage": r["stage"], "outcome": r["outcome"],
            "model": probs["model"], "closing": probs["closing"],
            "brier_model": bm, "brier_closing": bc,
            "model_less_wrong": bm < bc, "edge": bc - bm,
        })
    out["matches_scored"] = [r["match_id"] for r, _ in common]
    if own:
        con.close()
    return out


# ── calibration ──────────────────────────────────────────────────────────────
def calibration(con, *, series="model", book="sportsbet",
                model_version="dixon-coles-1.0", method="shin", n_bins=5) -> list[dict]:
    """Reliability bins pooled over all three outcomes. Each bin reports predicted mean,
    observed frequency and the count it rests on (thin bins are shown, not hidden)."""
    con = con or db.connect()
    settled = con.execute(
        "SELECT match_id, outcome FROM results JOIN matches USING (match_id)").fetchall()
    pairs = []  # (predicted_prob, hit)
    for r in settled:
        p = _probs_for(con, series, r["match_id"], book=book,
                       model_version=model_version, method=method)
        if p is None:
            continue
        for i, o in enumerate(OUTCOMES):
            pairs.append((p[i], 1.0 if o == r["outcome"] else 0.0))
    edges = [i / n_bins for i in range(n_bins + 1)]
    bins = []
    for b in range(n_bins):
        lo, hi = edges[b], edges[b + 1]
        inb = [(p, y) for p, y in pairs if (lo <= p < hi or (b == n_bins - 1 and p == hi))]
        if inb:
            bins.append({"lo": lo, "hi": hi, "n": len(inb),
                         "pred": sum(p for p, _ in inb) / len(inb),
                         "obs": sum(y for _, y in inb) / len(inb)})
        else:
            bins.append({"lo": lo, "hi": hi, "n": 0, "pred": None, "obs": None})
    return bins


# ── steam detection ──────────────────────────────────────────────────────────
def detect_steam(con, match_id, *, book="sportsbet", method="shin",
                 threshold=0.05, window_min=120) -> list[dict]:
    """Flag implied-probability moves on any outcome exceeding ``threshold`` within
    ``window_min`` minutes — the market suddenly repricing (a 'steam' move)."""
    rows = con.execute(
        """SELECT scrape_ts, home_dec, draw_dec, away_dec FROM odds_snapshots
           WHERE match_id=? AND book=? AND home_dec>1 AND draw_dec>1 AND away_dec>1
           ORDER BY scrape_ts""", (match_id, book)).fetchall()
    series = [(_parse(r["scrape_ts"]),
               devig.devig([r["home_dec"], r["draw_dec"], r["away_dec"]], method))
              for r in rows]
    steams = []
    for i in range(1, len(series)):
        t1, p1 = series[i]
        for j in range(i - 1, -1, -1):
            t0, p0 = series[j]
            if (t1 - t0).total_seconds() / 60 > window_min:
                break
            moves = [p1[k] - p0[k] for k in range(3)]
            k = max(range(3), key=lambda k: abs(moves[k]))
            if abs(moves[k]) >= threshold:
                steams.append({
                    "from_ts": t0.isoformat().replace("+00:00", "Z"),
                    "to_ts": t1.isoformat().replace("+00:00", "Z"),
                    "outcome": OUTCOMES[k], "delta": round(moves[k], 4)})
                break
    return steams


if __name__ == "__main__":
    out = score_all()
    print(f"Scored {out['n']} matches with both a frozen model and a closing line.")
    for s, d in out["series"].items():
        if d["mean_brier"] is not None:
            print(f"  {s:<8} N={d['n']:<3} Brier={d['mean_brier']:.4f}  "
                  f"logloss={d['mean_logloss']:.4f}")
