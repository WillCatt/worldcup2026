"""Capture cadence.

The spec calls for snapshots every 6h from market open, tightening to hourly inside the
final 24h and every 15 minutes in the last 2h before kickoff. Rather than run a fragile
long-lived process for a month, a ``launchd`` job ticks this script every few minutes and it
*self-throttles*: each tick it computes the tightest cadence implied by the nearest upcoming
kickoff and captures only if that interval has elapsed since the last successful run. A
crashed tick costs one interval, not the whole capture — the design degrades gracefully.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from mlfootball.market import db, scrape
from mlfootball.market.book import SportsbetBook

# (hours-to-kickoff threshold, capture interval minutes) — first match wins, tightest last.
CADENCE = [(2, 15), (24, 60), (10**6, 360)]


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def required_interval_minutes(con, now: datetime | None = None) -> int | None:
    """Tightest cadence across all not-yet-kicked-off matches. None if nothing is upcoming."""
    now = now or datetime.now(timezone.utc)
    rows = con.execute("SELECT kickoff_utc FROM matches").fetchall()
    horizons = [( _parse_ts(r["kickoff_utc"]) - now).total_seconds() / 3600
                for r in rows]
    upcoming = [h for h in horizons if h > 0]
    if not upcoming:
        return None
    nearest = min(upcoming)
    for thresh, interval in CADENCE:
        if nearest <= thresh:
            return interval
    return CADENCE[-1][1]


def minutes_since_last_ok(con, book: str = "sportsbet", now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    row = con.execute(
        "SELECT run_ts FROM scrape_log WHERE book=? AND status IN ('ok','partial') "
        "ORDER BY id DESC LIMIT 1", (book,)).fetchone()
    if row is None:
        return float("inf")
    return (now - _parse_ts(row["run_ts"])).total_seconds() / 60


def due(con, now: datetime | None = None) -> bool:
    interval = required_interval_minutes(con, now)
    if interval is None:
        return False
    return minutes_since_last_ok(con, "sportsbet", now) >= interval


def tick(con=None, force=False) -> dict:
    """One scheduler tick: capture both books iff a capture is due."""
    own = con is None
    con = con or db.init_db()
    interval = required_interval_minutes(con)
    if interval is None:
        return {"ran": False, "reason": "no upcoming matches"}
    if not force and not due(con):
        return {"ran": False, "reason": f"not due (interval {interval}m)",
                "since": round(minutes_since_last_ok(con), 1)}
    results = {
        "sportsbet": scrape.capture(SportsbetBook(), con),
        "backstop": scrape.capture(scrape._make_book("backstop:tab", con), con),
    }
    if own:
        con.close()
    return {"ran": True, "interval_m": interval, "results": results}


def main():
    ap = argparse.ArgumentParser(description="Self-throttling capture tick (run from launchd).")
    ap.add_argument("--force", action="store_true", help="capture now regardless of cadence")
    ap.add_argument("--status", action="store_true", help="print cadence state and exit")
    args = ap.parse_args()
    con = db.init_db()
    if args.status:
        print(f"required interval: {required_interval_minutes(con)} min")
        print(f"since last ok:     {minutes_since_last_ok(con):.1f} min")
        print(f"due:               {due(con)}")
        return
    out = tick(con, force=args.force)
    print(out)


if __name__ == "__main__":
    main()
