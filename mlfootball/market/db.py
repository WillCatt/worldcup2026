"""SQLite layer for the Model-vs-Market piece.

One database, ``data/odds.sqlite`` (gitignored — it's an unattended live capture, not a
committed artefact). The schema philosophy is lifted from a greyhound odds-logger: a thin
append-only ``odds_snapshots`` table is the spine, everything else hangs off ``match_id``.

The one table that is *not* append-anything is ``frozen_model``: model probabilities are
written **exactly once per (match, model_version)** before kickoff and can never be edited.
That immutability is the whole credibility argument of the piece, so it is enforced here in
the DB layer (``freeze_model`` refuses to overwrite) rather than trusted to callers.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "odds.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id      TEXT PRIMARY KEY,
    home          TEXT NOT NULL,
    away          TEXT NOT NULL,
    grp           TEXT,                 -- group letter, NULL for knockouts
    stage         TEXT NOT NULL,        -- 'group' | 'R32' | 'R16' | 'QF' | 'SF' | 'F'
    kickoff_utc   TEXT NOT NULL,        -- ISO8601 UTC
    kickoff_src   TEXT DEFAULT 'estimated',
    venue         TEXT,
    source_ref    TEXT                  -- where the fixture came from
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id  TEXT NOT NULL REFERENCES matches(match_id),
    book      TEXT NOT NULL,            -- 'sportsbet' (primary) | 'backstop:<name>'
    market    TEXT NOT NULL DEFAULT '1x2',
    scrape_ts TEXT NOT NULL,            -- when WE captured it (UTC ISO)
    book_ts   TEXT,                     -- the book's own timestamp if exposed
    home_dec  REAL,                     -- decimal odds
    draw_dec  REAL,
    away_dec  REAL,
    raw_path  TEXT                      -- archived raw payload on parse trouble
);
CREATE INDEX IF NOT EXISTS ix_snap_match ON odds_snapshots(match_id, book, scrape_ts);

CREATE TABLE IF NOT EXISTS results (
    match_id   TEXT PRIMARY KEY REFERENCES matches(match_id),
    home_goals INTEGER NOT NULL,
    away_goals INTEGER NOT NULL,
    outcome    TEXT NOT NULL,           -- 'home' | 'draw' | 'away'
    settled_ts TEXT NOT NULL
);

-- WRITE ONCE. One row per (match_id, model_version). Never updated.
CREATE TABLE IF NOT EXISTS frozen_model (
    match_id      TEXT NOT NULL REFERENCES matches(match_id),
    model_version TEXT NOT NULL,
    frozen_at     TEXT NOT NULL,        -- UTC ISO; must precede kickoff
    p_home        REAL NOT NULL,
    p_draw        REAL NOT NULL,
    p_away        REAL NOT NULL,
    inputs_hash   TEXT,                 -- provenance of the fit (no market features)
    PRIMARY KEY (match_id, model_version)
);

CREATE TABLE IF NOT EXISTS scrape_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_ts    TEXT NOT NULL,
    book      TEXT NOT NULL,
    status    TEXT NOT NULL,            -- 'ok' | 'partial' | 'error' | 'drift'
    n_matches INTEGER DEFAULT 0,
    error     TEXT
);
"""


def utcnow() -> str:
    """UTC timestamp, second precision, ISO8601 with trailing Z."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(str(path), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")      # survives concurrent reader (the exporter)
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def init_db(path: Path | str = DB_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = connect(path)
    con.executescript(SCHEMA)
    con.commit()
    return con


# ── writers ──────────────────────────────────────────────────────────────────
def upsert_match(con, *, match_id, home, away, grp, stage, kickoff_utc,
                 kickoff_src="estimated", venue=None, source_ref=None) -> None:
    con.execute(
        """INSERT INTO matches (match_id, home, away, grp, stage, kickoff_utc,
                                kickoff_src, venue, source_ref)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(match_id) DO UPDATE SET
             home=excluded.home, away=excluded.away, grp=excluded.grp,
             stage=excluded.stage, kickoff_utc=excluded.kickoff_utc,
             kickoff_src=excluded.kickoff_src, venue=excluded.venue,
             source_ref=excluded.source_ref""",
        (match_id, home, away, grp, stage, kickoff_utc, kickoff_src, venue, source_ref),
    )


def insert_snapshot(con, *, match_id, book, scrape_ts, home_dec, draw_dec, away_dec,
                    market="1x2", book_ts=None, raw_path=None) -> None:
    con.execute(
        """INSERT INTO odds_snapshots
             (match_id, book, market, scrape_ts, book_ts, home_dec, draw_dec, away_dec, raw_path)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (match_id, book, market, scrape_ts, book_ts, home_dec, draw_dec, away_dec, raw_path),
    )


def log_scrape(con, *, book, status, n_matches=0, error=None) -> None:
    con.execute(
        "INSERT INTO scrape_log (run_ts, book, status, n_matches, error) VALUES (?,?,?,?,?)",
        (utcnow(), book, status, n_matches, error),
    )
    con.commit()


def record_result(con, *, match_id, home_goals, away_goals) -> None:
    outcome = ("home" if home_goals > away_goals
               else "away" if away_goals > home_goals else "draw")
    con.execute(
        """INSERT INTO results (match_id, home_goals, away_goals, outcome, settled_ts)
           VALUES (?,?,?,?,?)
           ON CONFLICT(match_id) DO UPDATE SET
             home_goals=excluded.home_goals, away_goals=excluded.away_goals,
             outcome=excluded.outcome, settled_ts=excluded.settled_ts""",
        (match_id, home_goals, away_goals, outcome, utcnow()),
    )
    con.commit()


class FrozenModelError(RuntimeError):
    """Raised on any attempt to mutate an already-frozen model probability."""


def freeze_model(con, *, match_id, model_version, p_home, p_draw, p_away,
                 inputs_hash=None, frozen_at=None) -> bool:
    """Write a model probability triple ONCE. Returns True if written, False if a row for
    (match_id, model_version) already exists. Refuses to write after kickoff, and refuses
    to overwrite an existing row with *different* numbers (that would be retroactive editing
    — the exact thing the freeze protocol forbids)."""
    row = con.execute("SELECT kickoff_utc FROM matches WHERE match_id=?", (match_id,)).fetchone()
    if row is None:
        raise FrozenModelError(f"unknown match_id {match_id!r}; seed the fixture first")
    frozen_at = frozen_at or utcnow()
    if frozen_at >= row["kickoff_utc"]:
        raise FrozenModelError(
            f"refusing to freeze {match_id} at {frozen_at} — kickoff is {row['kickoff_utc']}")

    existing = con.execute(
        "SELECT p_home, p_draw, p_away FROM frozen_model WHERE match_id=? AND model_version=?",
        (match_id, model_version),
    ).fetchone()
    if existing is not None:
        same = all(abs(existing[k] - v) < 1e-12
                   for k, v in zip(("p_home", "p_draw", "p_away"), (p_home, p_draw, p_away)))
        if not same:
            raise FrozenModelError(
                f"{match_id} / {model_version} already frozen with different probabilities "
                f"— retroactive edits are forbidden. Bump model_version instead.")
        return False  # idempotent no-op
    con.execute(
        """INSERT INTO frozen_model
             (match_id, model_version, frozen_at, p_home, p_draw, p_away, inputs_hash)
           VALUES (?,?,?,?,?,?,?)""",
        (match_id, model_version, frozen_at, p_home, p_draw, p_away, inputs_hash),
    )
    con.commit()
    return True


if __name__ == "__main__":
    con = init_db()
    n = con.execute("SELECT count(*) FROM matches").fetchone()[0]
    print(f"odds.sqlite ready at {DB_PATH} — {n} matches seeded.")
