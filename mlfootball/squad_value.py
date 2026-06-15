"""Squad value — what each World Cup 2026 squad is worth, and a fixtures hub.

`squads.py` already knows *who* is in every squad (name / club / position / caps, parsed
from Wikipedia). The only thing missing for a strength view is the price tag. This module
adds it: it scrapes each nation's current Transfermarkt market values, matches them to the
squad by name, and turns the result into (a) a per-nation squad/XI valuation and (b) the
72 group-stage fixtures annotated with each side's worth — so the page can open on the
schedule and drill into any match's two squads side by side.

Transfermarkt is the de-facto standard for football market values. We scrape politely
(cached to `data/tm_cache/`, retries with backoff) and only the ~26 players per nation we
already have. National-team Transfermarkt ids are resolved once into
`data/tm_cache/nation_ids.json`. Coverage is reported honestly: any squad member we can't
price is shown as unvalued rather than guessed.
"""

from __future__ import annotations

import gzip
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from mlfootball import squads, travel

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "tm_cache"
IDS_FILE = CACHE / "nation_ids.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# schedule spellings -> the squad/player nation spelling
SCHEDULE_ALIAS = {
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
}


# ── fetch (gzip, retries, on-disk cache) ──────────────────────────────────────
def fetch(url: str, tries: int = 5, ttl_days: int = 7) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^a-z0-9]+", "_", url.lower())[-120:]
    fp = CACHE / f"{key}.html"
    if fp.exists() and (time.time() - fp.stat().st_mtime) < ttl_days * 86400:
        return fp.read_text("utf-8", "ignore")
    last = ""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept-Language": "en-US,en", "Accept-Encoding": "gzip"})
            r = urllib.request.urlopen(req, timeout=25)
            data = r.read()
            if r.info().get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            html = data.decode("utf-8", "ignore")
            fp.write_text(html)
            return html
        except Exception as e:  # noqa: BLE001 — transient 5xx/timeouts are expected
            last = str(e)
            if i < tries - 1:
                time.sleep(2.5 * (i + 1))
    print(f"  ! fetch failed {url}: {last}")
    return ""


# ── parse a national-team squad page ──────────────────────────────────────────
def parse_value_eur(s: str) -> int | None:
    s = s.replace("€", "").replace(",", "").strip()
    m = re.match(r"([\d.]+)\s*(bn|m|k)?", s)
    if not m or not m.group(1):
        return None
    n = float(m.group(1))
    return int(n * {"bn": 1e9, "m": 1e6, "k": 1e3, None: 1.0}[m.group(2)])


def parse_squad(html: str) -> dict[int, dict]:
    """{tm_id: {name, value_eur}} from a Transfermarkt squad page."""
    values: dict[int, int | None] = {}
    for pid, val in re.findall(r"/marktwertverlauf/spieler/(\d+)\"[^>]*>(€[^<]+)", html):
        values[int(pid)] = parse_value_eur(val)
    names: dict[int, str] = {}

    def offer(pid: int, cand: str) -> None:
        cand = (cand or "").strip()
        if cand and len(cand) >= len(names.get(pid, "")):
            names[pid] = cand

    # the name cell: profile link carrying the player's name as anchor text or title.
    # Capture the first text node after the tag (not up to </a>) so an inserted
    # <span title="Team captain"> can't hide a captain's name (this dropped Mbappé).
    for pid, attrs, text in re.findall(r"/profil/spieler/(\d+)\"([^>]*)>\s*([^<]*)", html):
        title = re.search(r'title="([^"]+)"', attrs)
        offer(int(pid), text or (title.group(1) if title else ""))
    # fallback: the portrait <img title="Name"> (some rows, e.g. captains, carry the
    # name only on the photo, not as anchor text — this is how Mbappé went missing)
    for pid, name in re.findall(
            r'/profil/spieler/(\d+)"[^>]*>\s*<img[^>]*title="([^"]+)"', html):
        offer(int(pid), name)
    return {pid: {"name": names.get(pid, ""), "value_eur": values[pid]}
            for pid in values if names.get(pid)}


# ── name matching squad <-> Transfermarkt ─────────────────────────────────────
def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def _tokset(name: str) -> frozenset[str]:
    """Order-independent token set, splitting on spaces AND hyphens — so Wikipedia's
    Korean order 'Son Heung-min' matches Transfermarkt's 'Heung-min Son'."""
    return frozenset(t for t in re.split(r"[ -]+", fold(name)) if t)


def _match(players: list[dict], tm: dict[int, dict]) -> list[dict]:
    """Attach value_eur to each squad player by name (exact fold -> token-set -> last)."""
    by_fold = {fold(v["name"]): v for v in tm.values()}
    by_set: dict[frozenset, list] = {}
    by_last: dict[str, list] = {}
    for v in tm.values():
        by_set.setdefault(_tokset(v["name"]), []).append(v)
        toks = fold(v["name"]).split()
        if toks:
            by_last.setdefault(toks[-1], []).append(v)
    out = []
    for p in players:
        f = fold(p["name"])
        hit = by_fold.get(f)
        if not hit:
            sset = by_set.get(_tokset(p["name"]))
            hit = sset[0] if sset and len(sset) == 1 else None
        if not hit:
            toks = f.split()
            cands = by_last.get(toks[-1], []) if toks else []
            hit = next((c for c in cands if fold(c["name"])[:1] == f[:1]), None) \
                or (cands[0] if len(cands) == 1 else None)
        out.append({**p, "value_eur": hit["value_eur"] if hit else None})
    return out


# ── resolve national-team Transfermarkt ids (once, cached) ────────────────────
# TM's English squad names differ from our Wikipedia spellings for a few nations.
TM_RANK_ALIAS = {
    "Turkey": "Türkiye",
    "Czech Republic": "Czechia",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "DR Congo": "Democratic Republic of the Congo",
}


def discover_ids(pages: int = 9) -> dict[str, tuple[str, str]]:
    """Harvest every national team's (slug, id) from Transfermarkt's FIFA world-ranking
    pages and resolve our 48 World Cup nations by name. Writes `nation_ids.json`.

    The ranking page is the one reliable aggregation endpoint (search/competition pages
    502 from this IP); each national-team anchor is `title="England" href="/england/.../
    verein/3299"`, so we match on the English display name."""
    name_to_team: dict[str, tuple[str, str]] = {}
    for page in range(1, pages + 1):
        html = fetch(f"https://www.transfermarkt.com/statistik/weltrangliste?page={page}",
                     ttl_days=30)
        for name, slug, vid in re.findall(
                r'title="([^"]+)" href="/([a-z0-9-]+)/startseite/verein/(\d+)"', html):
            name_to_team.setdefault(fold(name), (slug, vid))
        time.sleep(1.0)
    wc_nations = sorted({p["nation"] for p in squads.load_players()})
    resolved, missing = {}, []
    for nat in wc_nations:
        hit = name_to_team.get(fold(TM_RANK_ALIAS.get(nat, nat)))
        (resolved.__setitem__(nat, hit) if hit else missing.append(nat))
    if missing:
        print(f"  ! unresolved nations: {missing}")
    IDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    IDS_FILE.write_text(json.dumps(resolved, indent=1, ensure_ascii=False))
    return resolved


# ── per-nation valuation ──────────────────────────────────────────────────────
def nation_ids() -> dict[str, tuple[str, str]]:
    if not IDS_FILE.exists():
        return discover_ids()
    raw = json.loads(IDS_FILE.read_text())
    return {nat: tuple(v) for nat, v in raw.items()}


def squad_url(slug: str, vid: str) -> str:
    return f"https://www.transfermarkt.com/{slug}/kader/verein/{vid}"


def value_nations() -> dict[str, dict]:
    players = squads.load_players()
    ids = nation_ids()
    by_nation: dict[str, list[dict]] = {}
    for p in players:
        by_nation.setdefault(p["nation"], []).append(p)
    result = {}
    for nat, squad in by_nation.items():
        slug_id = ids.get(nat)
        tm = parse_squad(fetch(squad_url(*slug_id))) if slug_id else {}
        matched = _match(squad, tm)
        valued = [m for m in matched if m["value_eur"]]
        gk = [m for m in valued if m["pos_group"] == "Goalkeepers"]
        out = [m for m in valued if m["pos_group"] != "Goalkeepers"]
        gk.sort(key=lambda m: -m["value_eur"])
        out.sort(key=lambda m: -m["value_eur"])
        xi = (gk[:1] + out)[:11]
        xi_ids = {id(m) for m in xi}
        code = squads.NATION_CODE.get(nat, "")
        result[nat] = {
            "code": code, "flag": squads.flag(code) if code else "",
            "n_players": len(squad), "n_valued": len(valued),
            "squad_value": sum(m["value_eur"] for m in valued),
            "xi_value": sum(m["value_eur"] for m in xi),
            "avg_value": round(sum(m["value_eur"] for m in valued) / len(valued)) if valued else 0,
            "players": [{
                "name": m["name"], "pos": m["pos"], "pos_group": m["pos_group"],
                "club": m["club"], "caps": m["caps"], "value_eur": m["value_eur"],
                "in_xi": id(m) in xi_ids,
            } for m in sorted(matched, key=lambda m: -(m["value_eur"] or -1))],
        }
    return result


# ── fixtures hub ──────────────────────────────────────────────────────────────
def fixtures(nations: dict[str, dict]) -> list[dict]:
    def val(team):
        n = SCHEDULE_ALIAS.get(team, team)
        return nations.get(n, {}).get("xi_value", 0)
    out = []
    for date, group, a, b, venue_key in travel.SCHEDULE:
        v = travel.VENUES.get(venue_key, {}) if isinstance(travel.VENUES, dict) else {}
        out.append({
            "date": date, "group": group,
            "home": SCHEDULE_ALIAS.get(a, a), "away": SCHEDULE_ALIAS.get(b, b),
            "venue": v.get("name", venue_key) if isinstance(v, dict) else venue_key,
            "home_xi": val(a), "away_xi": val(b),
        })
    return out


def build_export() -> dict:
    nations = value_nations()
    valued_nations = [n for n in nations.values() if n["n_valued"]]
    total_players = sum(n["n_players"] for n in nations.values())
    total_valued = sum(n["n_valued"] for n in nations.values())
    ranking = sorted(
        [{"nation": k, "code": v["code"], "flag": v["flag"],
          "squad_value": v["squad_value"], "xi_value": v["xi_value"]}
         for k, v in nations.items()],
        key=lambda r: -r["squad_value"])
    return {
        "meta": {
            "n_nations": len(nations), "n_players": total_players,
            "n_valued": total_valued,
            "coverage": round(total_valued / total_players, 4) if total_players else 0,
            "currency": "EUR", "source": "Transfermarkt",
        },
        "ranking": ranking,
        "nations": nations,
        "fixtures": fixtures(nations),
        "sources": [{"label": "Transfermarkt — current player market values",
                     "url": "https://www.transfermarkt.com"}],
    }


def export(path: Path | None = None) -> dict:
    out = build_export()
    path = path or ROOT / "site" / "data" / "squad_value.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return out


if __name__ == "__main__":
    d = export()
    m = d["meta"]
    print(f"squad_value.json: {m['n_valued']}/{m['n_players']} players valued "
          f"({m['coverage']:.1%}) across {m['n_nations']} nations")
    print("richest:", ", ".join(f"{r['nation']} €{r['squad_value']/1e6:.0f}m"
                                 for r in d["ranking"][:5]))
