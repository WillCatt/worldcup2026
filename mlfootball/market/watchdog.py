"""Dead-man alerting.

A scraper that dies silently in week 2 kills the whole piece, so this runs on its *own*
launchd schedule, independent of the capture job. If the most recent successful capture is
older than the cadence allows (with a tolerance multiplier for transient misses), it alerts.

Alerting is zero-cost and best-effort, in descending reliability:
1. email-to-self via Gmail SMTP, if ``MVM_SMTP_USER`` / ``MVM_SMTP_PASS`` (app password) are
   set — the only channel that reaches William off-machine;
2. a macOS notification via ``osascript``;
3. always: a ``data/watchdog_status.json`` heartbeat the page's freshness indicator reads.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from mlfootball.market import db, schedule

STATUS_PATH = Path(__file__).resolve().parents[2] / "data" / "watchdog_status.json"
TOLERANCE = 2.5  # allow up to 2.5 missed intervals before crying wolf


def assess(con=None) -> dict:
    own = con is None
    con = con or db.init_db()
    interval = schedule.required_interval_minutes(con)
    since_primary = schedule.minutes_since_last_ok(con, "sportsbet")
    since_backstop = schedule.minutes_since_last_ok(con, "backstop:tab")
    healthy = interval is None or since_primary <= interval * TOLERANCE
    # the backstop covers a primary outage; both stale = real alert
    both_stale = (interval is not None
                  and since_primary > interval * TOLERANCE
                  and since_backstop > interval * TOLERANCE)
    state = {
        "checked_at": db.utcnow(),
        "interval_min": interval,
        "since_primary_min": round(since_primary, 1) if since_primary != float("inf") else None,
        "since_backstop_min": round(since_backstop, 1) if since_backstop != float("inf") else None,
        "healthy": bool(healthy),
        "both_stale": bool(both_stale),
        "level": "ok" if healthy else ("critical" if both_stale else "degraded"),
    }
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(state, indent=2))
    if own:
        con.close()
    return state


def _email(subject: str, body: str) -> bool:
    user, pw = os.environ.get("MVM_SMTP_USER"), os.environ.get("MVM_SMTP_PASS")
    to = os.environ.get("MVM_ALERT_TO", user)
    if not (user and pw):
        return False
    import smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = user, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(user, pw)
            s.send_message(msg)
        return True
    except Exception:
        return False


def _notify_mac(text: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{text}" with title "Model vs Market — scraper"'],
            check=False, timeout=10)
    except Exception:
        pass


def run(con=None) -> dict:
    state = assess(con)
    if state["level"] != "ok":
        msg = (f"Capture {state['level'].upper()}: Sportsbet last ok "
               f"{state['since_primary_min']}m ago, backstop {state['since_backstop_min']}m ago "
               f"(cadence {state['interval_min']}m). Check data/scrape_log.")
        sent = _email("⚠️ WC odds scraper degraded", msg)
        if not sent:
            _notify_mac(msg)
    return state


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
