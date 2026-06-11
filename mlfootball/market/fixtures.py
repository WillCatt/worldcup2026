"""Seed the ``matches`` table from the published WC 2026 schedule.

The fixture list (dates, groups, teams, venues) is reused verbatim from
``mlfootball.travel`` — the travel-burden piece already curated all 72 group-stage matches
from the final 5-Dec-2025 draw, so there is one source of truth for the calendar.

Kickoff *times* are not in that list. Until the per-match times are wired in, we estimate a
local 18:00 kickoff at the venue and convert to UTC via the venue's June UTC offset; the row
is stamped ``kickoff_src='estimated'`` so the freeze protocol and the page can flag it. The
estimate only ever sets the capture cadence and the freeze deadline — it is replaced by the
real time (``kickoff_src='confirmed'``) as soon as it is known, which only *tightens* the
deadline, never loosens a frozen probability.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone

from mlfootball import travel
from mlfootball.market import db

DEFAULT_LOCAL_KICKOFF_HOUR = 18  # 6pm local, the modal WC slot; refined per-match later


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def match_id(date: str, home: str, away: str) -> str:
    return f"{date}_{slug(home)}_v_{slug(away)}"


def _estimated_kickoff_utc(date: str, venue_id: str) -> str:
    """Local 18:00 at the venue → UTC ISO (Z)."""
    tz = travel.VENUES[venue_id]["tz"]  # June offset, integer hours
    y, m, d = (int(x) for x in date.split("-"))
    local = datetime(y, m, d, DEFAULT_LOCAL_KICKOFF_HOUR, 0)
    utc = (local - timedelta(hours=tz)).replace(tzinfo=timezone.utc)
    return utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def seed(con=None) -> int:
    """Insert/refresh all group-stage fixtures. Returns the number of matches seeded."""
    own = con is None
    con = con or db.init_db()
    n = 0
    for date, grp, home, away, venue_id in travel.SCHEDULE:
        mid = match_id(date, home, away)
        db.upsert_match(
            con,
            match_id=mid, home=home, away=away, grp=grp, stage="group",
            kickoff_utc=_estimated_kickoff_utc(date, venue_id),
            kickoff_src="estimated",
            venue=travel.VENUES[venue_id]["name"],
            source_ref="mlfootball.travel.SCHEDULE (final draw, 5 Dec 2025)",
        )
        n += 1
    con.commit()
    if own:
        con.close()
    return n


if __name__ == "__main__":
    con = db.init_db()
    n = seed(con)
    print(f"Seeded {n} group-stage fixtures.")
    nxt = con.execute(
        "SELECT match_id, kickoff_utc FROM matches ORDER BY kickoff_utc LIMIT 3"
    ).fetchall()
    for r in nxt:
        print(f"  {r['kickoff_utc']}  {r['match_id']}")
