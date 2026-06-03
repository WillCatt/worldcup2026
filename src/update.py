"""Live refresh: pull completed 2026 results, condition the sim on them, re-forecast.

Run daily by a GitHub Action. Before kickoff (11 Jun 2026) the feed has fixtures but no
scores, so this reproduces the pre-tournament forecast. Once matches are played it fixes
those results and re-simulates only the remaining unknowns -- the forecast moves as the
real tournament unfolds, with no scoreboard to maintain.

Feed: openfootball/worldcup.json (public domain, no API key).
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

from src import simulate, tournament

FEED_URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# openfootball uses some long-form / variant names; map them to our conventions.
FEED_ALIASES = {
    "United States of America": "United States",
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
    "Côte d'Ivoire": "Ivory Coast",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Curaçao": "Curaçao",
}


def _canon(name: str) -> str:
    return FEED_ALIASES.get(name, name)


def fetch_results() -> dict[frozenset, dict[str, int]]:
    """Return {frozenset({teamA,teamB}): {team: goals}} for matches with a final score."""
    try:
        resp = requests.get(FEED_URL, timeout=60)
        resp.raise_for_status()
        feed = resp.json()
    except Exception as e:  # noqa: BLE001 -- never let a feed hiccup break the cron
        print(f"[update] feed unavailable ({e}); forecasting with no results conditioned.")
        return {}

    known: dict[frozenset, dict[str, int]] = {}
    valid = set(tournament.all_teams())
    for m in feed.get("matches", []):
        # openfootball marks a played match with score1/score2 (full-time, incl. ET).
        # team1/team2 are plain strings; knockout fixtures hold placeholders until set.
        s1, s2 = m.get("score1"), m.get("score2")
        if s1 is None or s2 is None:
            score = m.get("score") or {}
            ft = score.get("ft")
            if not ft:
                continue
            s1, s2 = ft[0], ft[1]
        home, away = _canon(str(m["team1"])), _canon(str(m["team2"]))
        if home in valid and away in valid:
            known[frozenset((home, away))] = {home: int(s1), away: int(s2)}
    return known


def main(n: int = 50000) -> None:
    known = fetch_results()
    print(f"[update] {len(known)} completed matches conditioned.")
    out = simulate.run(n=n, known=known or None)
    print(f"[update] wrote output/forecast.json — {out['matches_played']} played, "
          f"leader: {next(iter(out['teams']))} {next(iter(out['teams'].values()))['win']*100:.1f}%")


if __name__ == "__main__":
    import sys
    main(n=int(sys.argv[1]) if len(sys.argv) > 1 else 50000)
