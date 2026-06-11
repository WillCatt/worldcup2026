"""Daily data-integrity report.

Catches the quiet failures that a row count alone misses: null/implausible odds, duplicate
snapshots, overrounds outside a sane band (a sign the parser grabbed the wrong market), and
the two books drifting apart (a sign one of them is stale or mis-parsed). Writes a status
block to ``data/integrity_status.json`` that the page surfaces as its freshness indicator.
"""
from __future__ import annotations

import json
from pathlib import Path

from mlfootball.market import db

STATUS_PATH = Path(__file__).resolve().parents[2] / "data" / "integrity_status.json"
OVERROUND_BAND = (0.02, 0.30)  # 1X2 implied-prob sum minus 1; outside this = suspicious


def _implied_overround(h, d, a) -> float | None:
    if not all(x and x > 1 for x in (h, d, a)):
        return None
    return (1 / h + 1 / d + 1 / a) - 1.0


def check(con=None) -> dict:
    own = con is None
    con = con or db.connect()
    snaps = con.execute("SELECT count(*) FROM odds_snapshots").fetchone()[0]
    matches = con.execute("SELECT count(*) FROM matches").fetchone()[0]
    frozen = con.execute("SELECT count(*) FROM frozen_model").fetchone()[0]
    results = con.execute("SELECT count(*) FROM results").fetchone()[0]

    null_odds = con.execute(
        "SELECT count(*) FROM odds_snapshots WHERE home_dec IS NULL OR draw_dec IS NULL "
        "OR away_dec IS NULL OR home_dec<=1 OR draw_dec<=1 OR away_dec<=1").fetchone()[0]

    dupes = con.execute(
        "SELECT count(*) FROM (SELECT match_id, book, scrape_ts, count(*) c "
        "FROM odds_snapshots GROUP BY match_id, book, scrape_ts HAVING c>1)").fetchone()[0]

    bad_overround = 0
    for r in con.execute("SELECT home_dec,draw_dec,away_dec FROM odds_snapshots"):
        ov = _implied_overround(r["home_dec"], r["draw_dec"], r["away_dec"])
        if ov is None or not (OVERROUND_BAND[0] <= ov <= OVERROUND_BAND[1]):
            bad_overround += 1

    # latest implied-prob disagreement between primary and backstop, per match
    disagree = con.execute("""
        WITH latest AS (
          SELECT match_id, book, home_dec, draw_dec, away_dec,
                 ROW_NUMBER() OVER (PARTITION BY match_id, book ORDER BY scrape_ts DESC) rn
          FROM odds_snapshots)
        SELECT p.match_id,
               1.0/p.home_dec AS ph, 1.0/b.home_dec AS bh
        FROM latest p JOIN latest b USING (match_id)
        WHERE p.rn=1 AND b.rn=1 AND p.book='sportsbet' AND b.book LIKE 'backstop:%'
    """).fetchall()
    gaps = [abs(r["ph"] - r["bh"]) for r in disagree]
    max_book_gap = round(max(gaps), 3) if gaps else None

    issues = []
    if null_odds:        issues.append(f"{null_odds} null/invalid odds rows")
    if dupes:            issues.append(f"{dupes} duplicate snapshots")
    if bad_overround:    issues.append(f"{bad_overround} rows with implausible overround")
    if max_book_gap is not None and max_book_gap > 0.08:
        issues.append(f"books disagree by up to {max_book_gap:.1%} implied")

    state = {
        "checked_at": db.utcnow(),
        "counts": {"matches": matches, "snapshots": snaps, "frozen": frozen, "results": results},
        "null_odds": null_odds, "duplicate_snapshots": dupes,
        "bad_overround": bad_overround, "max_book_gap": max_book_gap,
        "clean": not issues, "issues": issues,
    }
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(state, indent=2))
    if own:
        con.close()
    return state


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
