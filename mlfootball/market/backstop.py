"""The backstop / cross-validation book.

A *second* free Australian book, hit directly over its public JSON endpoint with requests —
no browser. It exists for two honest jobs, and never a third:

1. **Freshness insurance.** If the Sportsbet capture dies, the page still has a live market
   line through the outage, drawn as its own clearly-labelled ``backstop:*`` series.
2. **Cross-validation.** Two independent books that agree to within a point of implied
   probability are evidence the capture is sound — that agreement is a methods-note asset.

It is **never averaged with Sportsbet into "the market."** Different books carry different
overrounds and lines; blending them would manufacture a number no bookmaker ever quoted.
Each book is stored, de-vigged and scored as its own series; closing Sportsbet remains the
benchmark, the backstop is the check.
"""
from __future__ import annotations

import json

from mlfootball.market.book import (Book, SchemaDriftError, parse_sportsbet)

# Default backstop: TAB AU's public sports JSON. Endpoint shapes rotate; the generic walker
# in parse_sportsbet() reads several key conventions, so a structural change surfaces as
# drift (logged, raw archived) rather than silent bad data.
BACKSTOP_ENDPOINTS = {
    "tab": "https://api.beta.tab.com.au/v1/tab-info-service/sports/Soccer/competitions/"
           "FIFA%20World%20Cup",
}


class GenericJSONBook(Book):
    """A book defined entirely by a JSON endpoint + the shared defensive parser."""

    def __init__(self, label: str, endpoint: str, user_agent: str | None = None):
        self.name = f"backstop:{label}"
        self.endpoint = endpoint
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

    def fetch(self):
        import requests
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        resp = requests.get(self.endpoint, headers=headers, timeout=30)
        resp.raise_for_status()
        raw = resp.text
        try:
            return parse_sportsbet(json.loads(raw)), raw
        except SchemaDriftError:
            raise
        except (KeyError, ValueError, TypeError) as e:
            raise SchemaDriftError(f"{self.name} parse failed: {e}") from e


def make_backstop(spec: str) -> GenericJSONBook:
    """spec is 'backstop:<label>' or just '<label>'."""
    label = spec.split(":", 1)[1] if ":" in spec else spec
    if label not in BACKSTOP_ENDPOINTS:
        raise KeyError(f"unknown backstop {label!r}; known: {list(BACKSTOP_ENDPOINTS)}")
    return GenericJSONBook(label, BACKSTOP_ENDPOINTS[label])
