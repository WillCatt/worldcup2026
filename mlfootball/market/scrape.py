"""Run one capture cycle for a book and persist it.

This is the hardened entry point the scheduler calls. It owns the operational concerns that
keep a month-long unattended run alive: bounded retry with exponential backoff, raw-payload
archiving whenever a parse fails, schema-drift detection (and a single Selenium re-discovery
attempt before giving up), team-name matching to our seeded fixtures, and a row in
``scrape_log`` every single run so the watchdog can tell a silent death from a quiet night.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from mlfootball.market import db
from mlfootball.market.book import Book, MockBook, SchemaDriftError, SportsbetBook, norm_team

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw_html"
MAX_RETRIES = 4
BACKOFF_BASE = 2.0  # seconds: 2, 4, 8, 16


def _fixture_index(con) -> dict[tuple[str, str], str]:
    """{(norm_home, norm_away): match_id} for matches not yet kicked off."""
    rows = con.execute(
        "SELECT match_id, home, away FROM matches WHERE kickoff_utc > ?", (db.utcnow(),)
    ).fetchall()
    idx = {}
    for r in rows:
        idx[(norm_team(r["home"]), norm_team(r["away"]))] = r["match_id"]
    return idx


def _archive_raw(book_name: str, raw: str, tag: str) -> str:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{book_name}_{tag}_{db.utcnow().replace(':', '').replace('-', '')}.txt"
    path.write_text(raw)
    return str(path.relative_to(RAW_DIR.parents[1]))


def _fetch_with_retry(book: Book) -> tuple[list, str]:
    """Fetch with exponential backoff. SchemaDrift bypasses retry (re-fetching won't fix
    a structural change) and bubbles up to the caller's one-shot re-discovery."""
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            return book.fetch()
        except SchemaDriftError:
            raise
        except Exception as e:  # network/timeout/5xx — worth retrying
            last = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF_BASE ** (attempt + 1))
    raise last  # type: ignore[misc]


def capture(book: Book, con=None) -> dict:
    """Run one capture cycle for ``book``. Returns a small status dict and logs to the DB."""
    own = con is None
    con = con or db.init_db()
    scrape_ts = db.utcnow()
    status, n, err, raw_ref = "ok", 0, None, None
    try:
        try:
            quotes, raw = _fetch_with_retry(book)
        except SchemaDriftError as e:
            # one re-discovery attempt for the live book before declaring drift
            raw = ""
            if isinstance(book, SportsbetBook):
                try:
                    book.endpoint = None
                    book.discover()
                    quotes, raw = _fetch_with_retry(book)
                except Exception as e2:
                    raw_ref = _archive_raw(book.name, str(e2), "drift")
                    db.log_scrape(con, book=book.name, status="drift", error=str(e))
                    return {"status": "drift", "n": 0, "error": str(e), "raw": raw_ref}
            else:
                db.log_scrape(con, book=book.name, status="drift", error=str(e))
                return {"status": "drift", "n": 0, "error": str(e)}

        idx = _fixture_index(con)
        matched = 0
        for q in quotes:
            mid = idx.get((norm_team(q.home), norm_team(q.away)))
            if mid is None:  # try the swapped orientation (book may list away first)
                mid = idx.get((norm_team(q.away), norm_team(q.home)))
                if mid is not None:  # orientation flipped → swap home/away odds to OUR frame
                    q.home_dec, q.away_dec = q.away_dec, q.home_dec
            if mid is None or not q.valid():
                continue
            db.insert_snapshot(con, match_id=mid, book=book.name, scrape_ts=scrape_ts,
                               home_dec=q.home_dec, draw_dec=q.draw_dec, away_dec=q.away_dec,
                               book_ts=q.book_ts)
            matched += 1
        con.commit()
        n = matched
        if matched == 0:
            status, err = "partial", "fetched but matched 0 fixtures"
    except Exception as e:
        status, err = "error", str(e)
        if "raw" in dir() and raw:  # archive whatever we got for forensics
            raw_ref = _archive_raw(book.name, raw, "error")

    db.log_scrape(con, book=book.name, status=status, n_matches=n, error=err)
    if own:
        con.close()
    return {"status": status, "n": n, "error": err, "raw": raw_ref}


def _make_book(name: str, con) -> Book:
    if name == "sportsbet":
        return SportsbetBook()
    if name == "mock":
        rows = con.execute("SELECT home, away FROM matches LIMIT 8").fetchall()
        return MockBook([(r["home"], r["away"]) for r in rows])
    from mlfootball.market.backstop import make_backstop
    return make_backstop(name)


def main():
    ap = argparse.ArgumentParser(description="One odds-capture cycle.")
    ap.add_argument("book", nargs="?", default="sportsbet",
                    help="sportsbet | mock | backstop:<name>")
    args = ap.parse_args()
    con = db.init_db()
    book = _make_book(args.book, con)
    res = capture(book, con)
    print(f"[{book.name}] {res['status']} — {res['n']} matches"
          + (f" ({res['error']})" if res.get("error") else ""))


if __name__ == "__main__":
    main()
