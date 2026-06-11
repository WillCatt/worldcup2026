"""Bookmaker adapters.

A *book* knows how to turn a bookmaker's website into a list of ``MarketQuote`` rows
(one per match: decimal home/draw/away). The design separates two concerns deliberately:

* **discovery** (slow, fragile, Selenium): drive a real Chrome to the World Cup page and
  sniff the JSON XHR the page itself calls. This is done rarely.
* **polling** (fast, robust, requests): replay that JSON endpoint with the captured cookies.
  This is what the scheduler runs every few minutes for a month.

Re-discovery is triggered only when polling stops parsing (schema drift), so a normal week
never opens a browser. ``MockBook`` exercises the whole pipeline offline.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass


@dataclass
class MarketQuote:
    """One 1X2 quote for one match, as read off a book."""
    home: str
    away: str
    home_dec: float
    draw_dec: float
    away_dec: float
    book_ts: str | None = None

    def valid(self) -> bool:
        o = (self.home_dec, self.draw_dec, self.away_dec)
        return all(isinstance(x, (int, float)) and x > 1.0 for x in o)


def norm_team(name: str) -> str:
    """Accent/punctuation-folded key for matching a book's team label to our fixtures."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"\b(fc|afc|sc)\b", "", s.lower())
    return re.sub(r"[^a-z0-9]+", "", s)


class SchemaDriftError(RuntimeError):
    """The page/JSON no longer has the shape we know how to parse."""


class Book:
    name: str = "abstract"

    def fetch(self) -> tuple[list[MarketQuote], str]:
        """Return (quotes, raw_payload). Raise SchemaDriftError if the structure is unknown."""
        raise NotImplementedError


# ── Sportsbet AU (primary, showcased) ────────────────────────────────────────
class SportsbetBook(Book):
    """Sportsbet AU. Discovers its sportsbook JSON XHR via Chrome performance logs, then
    polls that endpoint with requests. The exact event/competition URL is discovered at
    runtime (Sportsbet rotates competition IDs), so nothing brittle is hard-coded beyond the
    public competition landing page and the JSON shape we expect to find.
    """
    name = "sportsbet"
    COMP_URL = "https://www.sportsbet.com.au/betting/soccer/international-cups/fifa-world-cup"
    # the JSON we want is the one carrying an event list with 'Head To Head' markets
    API_HINT = re.compile(r"/apigw/.*(competition|event|market)", re.I)

    def __init__(self, endpoint: str | None = None, cookies: dict | None = None,
                 user_agent: str | None = None):
        self.endpoint = endpoint
        self.cookies = cookies or {}
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

    # -- discovery (Selenium) --------------------------------------------------
    def discover(self) -> str:
        """Open Chrome, capture the competition JSON endpoint + cookies. Returns the URL."""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument(f"--user-agent={self.user_agent}")
        opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        driver = webdriver.Chrome(options=opts)
        try:
            driver.get(self.COMP_URL)
            driver.implicitly_wait(8)
            urls: list[str] = []
            for entry in driver.get_log("performance"):
                msg = json.loads(entry["message"])["message"]
                if msg.get("method") == "Network.requestWillBeSent":
                    u = msg["params"]["request"]["url"]
                    if self.API_HINT.search(u):
                        urls.append(u)
            self.cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
            if not urls:
                raise SchemaDriftError("no Sportsbet JSON endpoint matched API_HINT")
            self.endpoint = urls[-1]
            return self.endpoint
        finally:
            driver.quit()

    # -- polling (requests) ----------------------------------------------------
    def fetch(self) -> tuple[list[MarketQuote], str]:
        import requests
        if not self.endpoint:
            self.discover()
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        resp = requests.get(self.endpoint, headers=headers, cookies=self.cookies, timeout=30)
        resp.raise_for_status()
        raw = resp.text
        try:
            return parse_sportsbet(json.loads(raw)), raw
        except SchemaDriftError:
            raise
        except (KeyError, ValueError, TypeError) as e:
            raise SchemaDriftError(f"sportsbet parse failed: {e}") from e


def parse_sportsbet(payload) -> list[MarketQuote]:
    """Pull 1X2 quotes out of Sportsbet's competition JSON.

    Sportsbet nests events under a competition; each event has a 'Head To Head' (or
    'Match Result') market with three selections. The shape rotates, so we walk defensively
    and treat anything we can't read as drift rather than guessing.
    """
    events = _find_events(payload)
    if not events:
        raise SchemaDriftError("no events array found in payload")
    quotes: list[MarketQuote] = []
    for ev in events:
        teams = _event_teams(ev)
        market = _h2h_market(ev)
        if not teams or market is None:
            continue
        prices = _three_prices(market, teams)
        if prices is None:
            continue
        home, away = teams
        h, d, a = prices
        q = MarketQuote(home, away, h, d, a)
        if q.valid():
            quotes.append(q)
    if not quotes:
        raise SchemaDriftError("events found but no parseable 1X2 markets")
    return quotes


def _find_events(payload):
    """Sportsbet has used both a top-level list and {'events': [...]} / nested 'competitions'."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("events", "Events", "items"):
            if isinstance(payload.get(k), list):
                return payload[k]
        for comp in payload.get("competitions", []) or []:
            if isinstance(comp, dict) and isinstance(comp.get("events"), list):
                return comp["events"]
    return []


def _event_teams(ev):
    for hk, ak in (("homeTeam", "awayTeam"), ("home", "away"), ("competitor1", "competitor2")):
        if ev.get(hk) and ev.get(ak):
            h, a = ev[hk], ev[ak]
            h = h.get("name") if isinstance(h, dict) else h
            a = a.get("name") if isinstance(a, dict) else a
            if h and a:
                return (str(h), str(a))
    name = ev.get("name") or ev.get("eventName")
    if isinstance(name, str):
        for sep in (" v ", " vs ", " V "):
            if sep in name:
                h, a = name.split(sep, 1)
                return (h.strip(), a.strip())
    return None


def _h2h_market(ev):
    markets = ev.get("markets") or ev.get("Markets") or []
    for m in markets:
        nm = (m.get("name") or m.get("marketName") or "").lower()
        if "head to head" in nm or "match result" in nm or nm in ("1x2", "result"):
            return m
    return None


def _three_prices(market, teams):
    sels = market.get("selections") or market.get("outcomes") or []
    by_name = {}
    draw = None
    for s in sels:
        nm = s.get("name") or s.get("selectionName") or ""
        price = (s.get("price", {}) or {})
        odds = (price.get("winPrice") if isinstance(price, dict) else None) \
            or s.get("odds") or s.get("decimalOdds") or (price if isinstance(price, (int, float)) else None)
        if odds is None:
            continue
        if norm_team(nm) in ("draw", "tie"):
            draw = float(odds)
        else:
            by_name[norm_team(nm)] = float(odds)
    home, away = teams
    h = by_name.get(norm_team(home))
    a = by_name.get(norm_team(away))
    if h is None or a is None or draw is None:
        return None
    return (h, draw, a)


# ── Mock (offline test of the whole pipeline) ────────────────────────────────
class MockBook(Book):
    """Deterministic fake book. Drives a tiny random walk around a fixed 'true' price so the
    scheduler, drift handling, archiving and DB writes can be exercised with no network."""
    name = "mock"

    def __init__(self, fixtures, seed=0, drift=False):
        import random
        self._rng = random.Random(seed)
        self._fixtures = fixtures
        self._drift = drift

    def fetch(self):
        if self._drift:
            raise SchemaDriftError("mock drift")
        quotes, payload = [], {"events": []}
        for home, away in self._fixtures:
            base_h = self._rng.uniform(1.6, 4.0)
            base_a = self._rng.uniform(1.6, 4.0)
            draw = self._rng.uniform(3.0, 4.2)
            quotes.append(MarketQuote(home, away, round(base_h, 2), round(draw, 2), round(base_a, 2)))
            payload["events"].append({"home": home, "away": away})
        return quotes, json.dumps(payload)
