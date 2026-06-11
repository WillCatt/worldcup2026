"""Build ``site/data/market.json`` — the single static file the page reads.

Everything the D3 page needs, computed server-side and frozen into JSON: per-match de-vigged
implied-probability time-series for each book, the frozen model line, steam markers, results
and per-match "who was less wrong"; plus the tournament scoreboard (cumulative + rolling
Brier/log-loss per series, always with N), reliability bins, editorial cards, the de-vig
method comparison, and a freshness block. No ML or DB at runtime — the page is static.

The piece must render at N=0 (the tournament has only just started), so every aggregate is
written defensively and the headline is always paired with its match count.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from mlfootball.market import db, devig, score

SITE_DATA = Path(__file__).resolve().parents[2] / "site" / "data"
PORTFOLIO_DATA = Path.home() / "Documents" / "Projects" / "Portfolio" / "explorations" / "data"
BOOK = "sportsbet"
BACKSTOP = "backstop:tab"
MODEL_VERSION = "dixon-coles-1.0"
METHOD = "shin"


def _series_for_match(con, match_id, book):
    rows = con.execute(
        """SELECT scrape_ts, home_dec, draw_dec, away_dec FROM odds_snapshots
           WHERE match_id=? AND book=? AND home_dec>1 AND draw_dec>1 AND away_dec>1
           ORDER BY scrape_ts""", (match_id, book)).fetchall()
    out = []
    for r in rows:
        p = devig.devig([r["home_dec"], r["draw_dec"], r["away_dec"]], METHOD)
        out.append({"ts": r["scrape_ts"], "home": round(p[0], 4),
                    "draw": round(p[1], 4), "away": round(p[2], 4)})
    return out


def _freshness(con) -> dict:
    block = {"generated_at": db.utcnow()}
    for tag, fname in (("watchdog", "watchdog_status.json"), ("integrity", "integrity_status.json")):
        p = SITE_DATA.parent.parent / "data" / fname
        block[tag] = json.loads(p.read_text()) if p.exists() else None
    # last successful primary capture, for the "last updated" stamp
    row = con.execute(
        "SELECT run_ts FROM scrape_log WHERE book=? AND status IN ('ok','partial') "
        "ORDER BY id DESC LIMIT 1", (BOOK,)).fetchone()
    block["last_capture"] = row["run_ts"] if row else None
    lvl = (block.get("watchdog") or {}).get("level")
    clean = (block.get("integrity") or {}).get("clean", True)
    block["status"] = "ok" if (lvl in (None, "ok") and clean) else (lvl or "degraded")
    return block


def _devig_comparison(con) -> dict:
    """Pick the most lopsided live market (largest overround / longest longshot) to show
    proportional vs Shin diverging, plus a near-coin-flip where they agree."""
    rows = con.execute(
        """SELECT m.home, m.away, s.home_dec, s.draw_dec, s.away_dec
           FROM odds_snapshots s JOIN matches m USING (match_id)
           WHERE s.book=? AND s.home_dec>1 AND s.draw_dec>1 AND s.away_dec>1""", (BOOK,)).fetchall()
    examples = []
    if rows:
        def longest(r):  # biggest single decimal odd = the clearest longshot
            return max(r["home_dec"], r["draw_dec"], r["away_dec"])
        lop = max(rows, key=longest)
        flat = min(rows, key=lambda r: abs(r["home_dec"] - r["away_dec"]))
        for tag, r in (("lopsided", lop), ("coin-flip", flat)):
            c = devig.compare([r["home_dec"], r["draw_dec"], r["away_dec"]])
            c["label"] = f"{r['home']} v {r['away']}"
            c["kind"] = tag
            examples.append(c)
    return {"method_used": METHOD, "examples": examples}


def _n_needed(per_match) -> dict:
    """Honest 'how big must N be' note: how many matches before a model–closing Brier gap of
    the size we see would clear two standard errors. Uses the per-match Brier-difference SD."""
    diffs = [p["brier_closing"] - p["brier_model"] for p in per_match]  # +ve = model better
    n = len(diffs)
    if n < 2:
        return {"n": n, "mean_edge": None, "sd": None, "n_for_signif": None}
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    sd = var ** 0.5
    n_needed = (2 * sd / abs(mean)) ** 2 if mean != 0 else None
    return {"n": n, "mean_edge": round(mean, 4), "sd": round(sd, 4),
            "n_for_signif": int(n_needed) + 1 if n_needed else None}


def build(con=None) -> dict:
    own = con is None
    con = con or db.connect()

    scored = score.score_all(con, book=BOOK, model_version=MODEL_VERSION, method=METHOD)
    settled = {r["match_id"]: r for r in con.execute(
        "SELECT match_id, home_goals, away_goals, outcome FROM results").fetchall()}
    per_match_idx = {p["match_id"]: p for p in scored["per_match"]}

    matches = []
    for m in con.execute(
            "SELECT * FROM matches ORDER BY kickoff_utc").fetchall():
        mid = m["match_id"]
        fm = con.execute(
            "SELECT p_home,p_draw,p_away,frozen_at FROM frozen_model "
            "WHERE match_id=? AND model_version=?", (mid, MODEL_VERSION)).fetchone()
        res = settled.get(mid)
        pm = per_match_idx.get(mid)
        matches.append({
            "match_id": mid, "home": m["home"], "away": m["away"],
            "grp": m["grp"], "stage": m["stage"], "venue": m["venue"],
            "kickoff_utc": m["kickoff_utc"], "kickoff_src": m["kickoff_src"],
            "model": ({"home": fm["p_home"], "draw": fm["p_draw"], "away": fm["p_away"],
                       "frozen_at": fm["frozen_at"]} if fm else None),
            "market": {BOOK: _series_for_match(con, mid, BOOK),
                       BACKSTOP: _series_for_match(con, mid, BACKSTOP)},
            "steam": score.detect_steam(con, mid, book=BOOK, method=METHOD),
            "result": ({"home_goals": res["home_goals"], "away_goals": res["away_goals"],
                        "outcome": res["outcome"]} if res else None),
            "score": ({"brier_model": pm["brier_model"], "brier_closing": pm["brier_closing"],
                       "model_less_wrong": pm["model_less_wrong"], "edge": pm["edge"]}
                      if pm else None),
        })

    # editorial cards (biggest model win / worst miss) — always carry cumulative N
    pm_sorted = sorted(scored["per_match"], key=lambda p: p["edge"], reverse=True)
    cards = {
        "best": pm_sorted[0] if pm_sorted else None,
        "worst": pm_sorted[-1] if pm_sorted else None,
        "n": scored["n"],
    }

    payload = {
        "meta": {
            "generated_at": db.utcnow(),
            "model_version": MODEL_VERSION, "devig": METHOD,
            "book": BOOK, "backstop": BACKSTOP,
            "n_settled": scored["n"],
            "tournament": {"start": "2026-06-11", "end": "2026-07-19"},
        },
        "freshness": _freshness(con),
        "devig_comparison": _devig_comparison(con),
        "scoreboard": {
            "series": {s: {k: d[k] for k in ("n", "mean_brier", "mean_logloss", "rolling_brier")}
                       | {"history": d["history"]}
                       for s, d in scored["series"].items()},
            "cards": cards,
            "calibration": {
                "model": score.calibration(con, series="model", method=METHOD),
                "closing": score.calibration(con, series="closing", book=BOOK, method=METHOD),
            },
            "n_needed": _n_needed(scored["per_match"]),
        },
        "matches": matches,
    }
    if own:
        con.close()
    return payload


def write(payload=None) -> Path:
    payload = payload or build()
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    out = SITE_DATA / "market.json"
    out.write_text(json.dumps(payload, separators=(",", ":")))
    if PORTFOLIO_DATA.exists():
        (PORTFOLIO_DATA / "market.json").write_text(json.dumps(payload, separators=(",", ":")))
    return out


if __name__ == "__main__":
    p = write()
    size = p.stat().st_size
    pay = json.loads(p.read_text())
    print(f"wrote {p} ({size/1024:.1f} KB) — {len(pay['matches'])} matches, "
          f"N={pay['meta']['n_settled']} settled, status={pay['freshness']['status']}")
