"""Club-to-Country: where the 2026 World Cup earns its living.

For every one of the 48 qualified nations, this maps each squad player to the
club — and country/league — where they actually play, then turns that into flows
(nation → league) and a "domestic dependency" stat (what share of a squad plays
in its own country's league). England pools almost entirely into the Premier
League; Senegal fans out across a dozen countries.

The ML here is light; the *data engineering* is the point. Real-world entities
are messy: the same club shows up as "Manchester City F.C.", "FC Bayern Munich",
"Paris Saint-Germain FC", "Al Hilal SFC" — inconsistent prefixes, suffixes,
piped wiki-links and accents. Reconciling them into clean nodes, and mapping 71
club-country codes onto named leagues, is the unglamorous work every data job
actually needs. Source: the Wikipedia 2026 squad tables (raw wikitext, parsed
here — no scraping-fragility), cross-checked at 1,246 players / 48 squads.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "squads_wikitext.txt"

# ── club-country code → (country name, league name) ───────────────────────────
# Named leagues for the destinations players actually flock to; country-name
# fallback for the long tail (handled in country()/league() below).
CODE_COUNTRY = {
    "ENG": "England", "GER": "Germany", "ESP": "Spain", "FRA": "France", "ITA": "Italy",
    "KSA": "Saudi Arabia", "TUR": "Turkey", "USA": "United States", "NED": "Netherlands",
    "POR": "Portugal", "BRA": "Brazil", "BEL": "Belgium", "QAT": "Qatar", "MEX": "Mexico",
    "IRN": "Iran", "CZE": "Czech Republic", "SCO": "Scotland", "EGY": "Egypt", "RSA": "South Africa",
    "ARG": "Argentina", "UZB": "Uzbekistan", "UAE": "United Arab Emirates", "IRQ": "Iraq",
    "DEN": "Denmark", "GRE": "Greece", "RUS": "Russia", "SUI": "Switzerland", "JOR": "Jordan",
    "CYP": "Cyprus", "KOR": "South Korea", "NZL": "New Zealand", "NOR": "Norway", "JPN": "Japan",
    "AUT": "Austria", "AUS": "Australia", "TUN": "Tunisia", "CRO": "Croatia", "CAN": "Canada",
    "WAL": "Wales", "POL": "Poland", "ECU": "Ecuador", "ISR": "Israel", "SWE": "Sweden",
    "HUN": "Hungary", "MAR": "Morocco", "PAR": "Paraguay", "MAS": "Malaysia", "ALG": "Algeria",
    "SRB": "Serbia", "ROU": "Romania", "SVK": "Slovakia", "SVN": "Slovenia", "IRL": "Ireland",
    "BUL": "Bulgaria", "CRC": "Costa Rica", "VEN": "Venezuela", "PAN": "Panama", "CHI": "Chile",
    "CHN": "China", "BIH": "Bosnia and Herzegovina", "KAZ": "Kazakhstan", "HAI": "Haiti",
    "FIN": "Finland", "THA": "Thailand", "IDN": "Indonesia", "COL": "Colombia", "ARM": "Armenia",
    "GHA": "Ghana", "URU": "Uruguay", "HON": "Honduras", "AZE": "Azerbaijan",
}
CODE_LEAGUE = {
    "ENG": "Premier League", "GER": "Bundesliga", "ESP": "La Liga", "FRA": "Ligue 1",
    "ITA": "Serie A", "KSA": "Saudi Pro League", "TUR": "Süper Lig", "USA": "MLS",
    "NED": "Eredivisie", "POR": "Primeira Liga", "BRA": "Brasileirão", "BEL": "Belgian Pro League",
    "QAT": "Qatar Stars League", "MEX": "Liga MX", "IRN": "Persian Gulf Pro League",
    "CZE": "Czech First League", "SCO": "Scottish Premiership", "EGY": "Egyptian Premier League",
    "RSA": "PSL (South Africa)", "ARG": "Liga Profesional", "UZB": "Uzbekistan Super League",
    "UAE": "UAE Pro League", "IRQ": "Iraq Stars League", "DEN": "Danish Superliga",
    "GRE": "Super League Greece", "RUS": "Russian Premier League", "SUI": "Swiss Super League",
    "JOR": "Jordanian Pro League", "CYP": "Cypriot First Division", "KOR": "K League 1",
    "NOR": "Eliteserien", "JPN": "J1 League", "AUT": "Austrian Bundesliga", "AUS": "A-League",
    "TUN": "Tunisian Ligue 1", "CRO": "Croatian HNL", "POL": "Ekstraklasa", "ECU": "Ecuadorian Serie A",
    "ISR": "Israeli Premier League", "SWE": "Allsvenskan", "MAR": "Botola",
}

# ── position grouping (GK/DF/MF/FW → the four sankey lanes) ────────────────────
POS_GROUP = {"GK": "Goalkeepers", "DF": "Defenders", "MF": "Midfielders", "FW": "Forwards"}
POS_ORDER = ["Goalkeepers", "Defenders", "Midfielders", "Forwards"]

# ── club-country code → ISO-3166 alpha-2 (for flag emoji on the front end) ─────
# England/Scotland/Wales have no alpha-2; they get subdivision tag-sequence flags
# built in flag() below. Everything else maps to a normal regional-indicator pair.
CODE_ISO2 = {
    "GER": "de", "ESP": "es", "FRA": "fr", "ITA": "it", "KSA": "sa", "TUR": "tr",
    "USA": "us", "NED": "nl", "POR": "pt", "BRA": "br", "BEL": "be", "QAT": "qa",
    "MEX": "mx", "IRN": "ir", "CZE": "cz", "EGY": "eg", "RSA": "za", "ARG": "ar",
    "UZB": "uz", "UAE": "ae", "IRQ": "iq", "DEN": "dk", "GRE": "gr", "RUS": "ru",
    "SUI": "ch", "JOR": "jo", "CYP": "cy", "KOR": "kr", "NZL": "nz", "NOR": "no",
    "JPN": "jp", "AUT": "at", "AUS": "au", "TUN": "tn", "CRO": "hr", "CAN": "ca",
    "POL": "pl", "ECU": "ec", "ISR": "il", "SWE": "se", "HUN": "hu", "MAR": "ma",
    "PAR": "py", "MAS": "my", "ALG": "dz", "SRB": "rs", "ROU": "ro", "SVK": "sk",
    "SVN": "si", "IRL": "ie", "BUL": "bg", "CRC": "cr", "VEN": "ve", "PAN": "pa",
    "CHI": "cl", "CHN": "cn", "BIH": "ba", "KAZ": "kz", "HAI": "ht", "FIN": "fi",
    "THA": "th", "IDN": "id", "COL": "co", "ARM": "am", "GHA": "gh", "URU": "uy",
    "HON": "hn", "AZE": "az", "CPV": "cv", "COD": "cd", "CUW": "cw", "CIV": "ci",
    "SEN": "sn",
}
_SUBDIV_FLAG = {  # 🏴 + tag-sequence for the home nations
    "ENG": "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F",
    "SCO": "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F",
    "WAL": "\U0001F3F4\U000E0067\U000E0062\U000E0077\U000E006C\U000E0073\U000E007F",
}


def flag(code: str) -> str:
    """Emoji flag for a football country code (🏴 tag-sequences for ENG/SCO/WAL)."""
    if code in _SUBDIV_FLAG:
        return _SUBDIV_FLAG[code]
    iso = CODE_ISO2.get(code)
    if not iso or len(iso) != 2:
        return "🏳️"
    return "".join(chr(0x1F1E6 + ord(c) - ord("a")) for c in iso.lower())


# ── federation / kit colours — the accent palette each nation's page adopts ───
# (primary, secondary). Primaries are chosen saturated-but-legible on an off-white
# ground; near-black is used where a nation's identity is genuinely monochrome.
FED_COLORS = {
    "Algeria": ("#0B7A3B", "#C8102E"), "Argentina": ("#3D7DB8", "#F2C84B"),
    "Australia": ("#00843D", "#FFCD00"), "Austria": ("#C8102E", "#1B1B1F"),
    "Belgium": ("#C8102E", "#F2C84B"), "Bosnia and Herzegovina": ("#1B4DA0", "#FECB00"),
    "Brazil": ("#009739", "#FFDF00"), "Canada": ("#D52B1E", "#1B1B1F"),
    "Cape Verde": ("#1B3A8F", "#CF2027"), "Colombia": ("#CC9A06", "#003893"),
    "Croatia": ("#C8102E", "#1B3A8F"), "Curaçao": ("#00339A", "#F2C84B"),
    "Czech Republic": ("#11457E", "#D7141A"), "DR Congo": ("#1071C6", "#F7D618"),
    "Ecuador": ("#CC9A06", "#034EA2"), "Egypt": ("#C8102E", "#1B1B1F"),
    "England": ("#19295C", "#C8102E"), "France": ("#002F87", "#C8102E"),
    "Germany": ("#1B1B1F", "#E1A700"), "Ghana": ("#0B7A3B", "#E1A700"),
    "Haiti": ("#00209F", "#C8102E"), "Iran": ("#0B7A3B", "#C8102E"),
    "Iraq": ("#0B7A3B", "#1B1B1F"), "Ivory Coast": ("#E36C00", "#0B7A3B"),
    "Japan": ("#14225C", "#BC002D"), "Jordan": ("#C8102E", "#0B7A3B"),
    "Mexico": ("#006847", "#C8102E"), "Morocco": ("#C1272D", "#0B7A3B"),
    "Netherlands": ("#E1670B", "#1B3A8F"), "New Zealand": ("#1B1B1F", "#C8102E"),
    "Norway": ("#BA0C2F", "#19295C"), "Panama": ("#C8102E", "#1B3A8F"),
    "Paraguay": ("#C8102E", "#1B3A8F"), "Portugal": ("#0B6E4F", "#C8102E"),
    "Qatar": ("#7A1530", "#1B1B1F"), "Saudi Arabia": ("#006C35", "#1B1B1F"),
    "Scotland": ("#15397F", "#F2C84B"), "Senegal": ("#00853F", "#E1A700"),
    "South Africa": ("#007749", "#E1A700"), "South Korea": ("#CD2E3A", "#14225C"),
    "Spain": ("#C60B1E", "#E1A700"), "Sweden": ("#006AA7", "#FECC02"),
    "Switzerland": ("#D52B1E", "#1B1B1F"), "Tunisia": ("#E70013", "#1B1B1F"),
    "Turkey": ("#E30A17", "#1B1B1F"), "United States": ("#0A3161", "#B31942"),
    "Uruguay": ("#3E7CB1", "#1B1B1F"), "Uzbekistan": ("#1B75BB", "#0B7A3B"),
}


# ── nation → its own club-country code (for the domestic-dependency stat) ──────
NATION_CODE = {
    "Algeria": "ALG", "Argentina": "ARG", "Australia": "AUS", "Austria": "AUT", "Belgium": "BEL",
    "Bosnia and Herzegovina": "BIH", "Brazil": "BRA", "Canada": "CAN", "Cape Verde": "CPV",
    "Colombia": "COL", "Croatia": "CRO", "Curaçao": "CUW", "Czech Republic": "CZE", "DR Congo": "COD",
    "Ecuador": "ECU", "Egypt": "EGY", "England": "ENG", "France": "FRA", "Germany": "GER",
    "Ghana": "GHA", "Haiti": "HAI", "Iran": "IRN", "Iraq": "IRQ", "Ivory Coast": "CIV",
    "Japan": "JPN", "Jordan": "JOR", "Mexico": "MEX", "Morocco": "MAR", "Netherlands": "NED",
    "New Zealand": "NZL", "Norway": "NOR", "Panama": "PAN", "Paraguay": "PAR", "Portugal": "POR",
    "Qatar": "QAT", "Saudi Arabia": "KSA", "Scotland": "SCO", "Senegal": "SEN", "South Africa": "RSA",
    "South Korea": "KOR", "Spain": "ESP", "Sweden": "SWE", "Switzerland": "SUI", "Tunisia": "TUN",
    "Turkey": "TUR", "United States": "USA", "Uruguay": "URU", "Uzbekistan": "UZB",
}


def country(code: str) -> str:
    return CODE_COUNTRY.get(code, code)


def league(code: str) -> str:
    """Named league for the big destinations; '<Country> (domestic)' for the tail."""
    if code in CODE_LEAGUE:
        return CODE_LEAGUE[code]
    return f"{country(code)} (domestic)"


# ── club-name normalisation — the entity-resolution layer ─────────────────────
# Strip the club-form noise (F.C./FC/AFC/SC/CF/AS/SSC/1. FC …) that makes the
# same club look like several. Order matters; we peel known affixes off the ends.
_SUFFIXES = [" F.C.", " FC", " A.F.C.", " AFC", " S.F.C.", " SFC", " B.C.", " CF",
             " S.C.", " SC", " A.C.", " AC", " SK", " SAD", " SC.", " S.A.D."]
_PREFIXES = ["FC ", "AFC ", "AS ", "SS ", "SSC ", "SC ", "CF ", "AC ", "SV ", "VfB ",
             "VfL ", "TSG ", "1. FC ", "1.FC ", "FK ", "BK ", "CD ", "RC ", "US "]


def normalize_club(name: str) -> str:
    n = name.strip()
    changed = True
    while changed:
        changed = False
        for suf in _SUFFIXES:
            if n.endswith(suf):
                n, changed = n[: -len(suf)].strip(), True
    for pre in _PREFIXES:
        if n.startswith(pre):
            n = n[len(pre):].strip()
            break
    return n or name.strip()


# ── parse the raw wikitext → players ──────────────────────────────────────────
def load_players() -> list[dict]:
    t = RAW.read_text(encoding="utf-8")
    heads = [(m.start(), m.group(1).strip())
             for m in re.finditer(r"\n===\s*([^=\n][^=]*?)\s*===\n", t)]
    nations = [(p, n) for p, n in heads if not n.lower().startswith(("group", "note"))]
    bounds = [p for p, _ in nations] + [len(t)]
    out = []
    for i, (p, nat) in enumerate(nations):
        for line in t[p:bounds[i + 1]].splitlines():
            if "nat fs g player" not in line:
                continue
            club_m = re.search(r"\|club=(.*?)\|clubnat=", line)
            cn_m = re.search(r"\|clubnat=([A-Za-z]+)", line)
            raw_club = re.search(r"\[\[([^\]|]+)", club_m.group(1)).group(1).strip() if club_m else "?"
            pos_m = re.search(r"\|pos=([A-Z]+)", line)
            caps_m = re.search(r"\|caps=(\d+)", line)
            goals_m = re.search(r"\|goals=(\d+)", line)
            name_m = re.search(r"\|name=\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", line)
            pos = pos_m.group(1) if pos_m else "MF"
            out.append({
                "nation": nat,
                "name": name_m.group(1).strip() if name_m else "?",
                "pos": pos,
                "pos_group": POS_GROUP.get(pos, "Midfielders"),
                "caps": int(caps_m.group(1)) if caps_m else 0,
                "goals": int(goals_m.group(1)) if goals_m else 0,
                "club": normalize_club(raw_club),
                "club_raw": raw_club,
                "code": cn_m.group(1) if cn_m else "?",
            })
    return out


# ── aggregations ──────────────────────────────────────────────────────────────
def nation_breakdowns(players: list[dict] | None = None) -> list[dict]:
    players = players or load_players()
    by_nation: dict[str, list[dict]] = {}
    for pl in players:
        by_nation.setdefault(pl["nation"], []).append(pl)
    rows = []
    for nat, squad in by_nation.items():
        code = NATION_CODE.get(nat, "")
        n = len(squad)
        domestic = sum(1 for p in squad if p["code"] == code)
        leagues = Counter((league(p["code"]), p["code"]) for p in squad)
        clubs = Counter((p["club"], p["code"]) for p in squad)
        rows.append({
            "nation": nat, "code": code, "n_players": n,
            "domestic": domestic, "domestic_pct": round(100 * domestic / n, 1),
            "n_leagues": len(set(p["code"] for p in squad)),
            "leagues": [{"league": lg, "code": c, "country": country(c), "count": v,
                         "domestic": c == code}
                        for (lg, c), v in sorted(leagues.items(), key=lambda x: -x[1])],
            "clubs": [{"club": cl, "code": c, "country": country(c), "count": v}
                      for (cl, c), v in sorted(clubs.items(), key=lambda x: -x[1])],
        })
    rows.sort(key=lambda r: r["domestic_pct"], reverse=True)
    return rows


def sankey_league(players: list[dict] | None = None, top: int = 15) -> dict:
    """Nation → league flows. Leagues beyond the top-N by volume fold into 'Other'."""
    players = players or load_players()
    league_totals = Counter(league(p["code"]) for p in players)
    keep = {lg for lg, _ in league_totals.most_common(top)}
    links = Counter()
    for p in players:
        lg = league(p["code"]) if league(p["code"]) in keep else "Other leagues"
        links[(p["nation"], lg)] += 1
    nations = sorted(set(p["nation"] for p in players))
    leagues = [lg for lg, _ in league_totals.most_common(top)]
    if any(league(p["code"]) not in keep for p in players):
        leagues.append("Other leagues")
    nodes = [{"id": f"N:{n}", "name": n, "side": "nation"} for n in nations] + \
            [{"id": f"L:{lg}", "name": lg, "side": "league",
              "total": league_totals.get(lg, sum(v for (n, l), v in links.items() if l == lg))}
             for lg in leagues]
    link_list = [{"source": f"N:{n}", "target": f"L:{lg}", "value": v}
                 for (n, lg), v in links.items()]
    return {"nodes": nodes, "links": link_list, "leagues": leagues, "nations": nations}


def sankey_club(players: list[dict] | None = None, min_players: int = 3) -> dict:
    """Nation → club flows. Clubs with fewer than `min_players` internationals fold
    into one 'Other clubs' node so the diagram stays legible (451 clubs would not)."""
    players = players or load_players()
    club_totals = Counter(p["club"] for p in players)
    keep = {c for c, v in club_totals.items() if v >= min_players}
    links = Counter()
    club_code = {}
    for p in players:
        cl = p["club"] if p["club"] in keep else "Other clubs"
        links[(p["nation"], cl)] += 1
        club_code.setdefault(cl, p["code"])
    nations = sorted(set(p["nation"] for p in players))
    clubs = [c for c, _ in club_totals.most_common() if c in keep]
    if any(p["club"] not in keep for p in players):
        clubs.append("Other clubs")
    nodes = [{"id": f"N:{n}", "name": n, "side": "nation"} for n in nations] + \
            [{"id": f"C:{c}", "name": c, "side": "club",
              "country": country(club_code.get(c, "")),
              "total": club_totals.get(c, sum(v for (n, cc), v in links.items() if cc == c))}
             for c in clubs]
    link_list = [{"source": f"N:{n}", "target": f"C:{c}", "value": v}
                 for (n, c), v in links.items()]
    return {"nodes": nodes, "links": link_list, "clubs": clubs, "nations": nations}


def league_leaderboard(players: list[dict] | None = None) -> list[dict]:
    players = players or load_players()
    tot = Counter(league(p["code"]) for p in players)
    return [{"league": lg, "country": country(_code_for_league(lg)), "count": v}
            for lg, v in tot.most_common()]


def _code_for_league(lg: str) -> str:
    for c, name in CODE_LEAGUE.items():
        if name == lg:
            return c
    return ""


# ── nation-first editorial export (player-level, for the redesigned Sankey) ───
def nation_player_export(players: list[dict] | None = None) -> dict:
    """One record per nation carrying the full player list (name, position, club,
    league, caps, domestic flag) plus identity (flag, federation colours) and a
    domestic-dependency rank. The front end builds the squad→position→league
    Sankey, league/club grouping and the auto-verdict from this directly."""
    players = players or load_players()
    by_nation: dict[str, list[dict]] = {}
    for pl in players:
        by_nation.setdefault(pl["nation"], []).append(pl)

    rows = []
    for nat, squad in by_nation.items():
        code = NATION_CODE.get(nat, "")
        n = len(squad)
        domestic = sum(1 for p in squad if p["code"] == code)
        primary, secondary = FED_COLORS.get(nat, ("#5B5751", "#8A857C"))
        plist = []
        for p in sorted(squad, key=lambda x: (POS_ORDER.index(x["pos_group"]), -x["caps"])):
            plist.append({
                "name": p["name"], "pos": p["pos"], "posGroup": p["pos_group"],
                "club": p["club"], "league": league(p["code"]), "code": p["code"],
                "country": country(p["code"]), "flag": flag(p["code"]),
                "caps": p["caps"], "goals": p["goals"], "domestic": p["code"] == code,
            })
        rows.append({
            "nation": nat, "code": code, "flag": flag(code),
            "colors": {"primary": primary, "secondary": secondary},
            "n_players": n, "domestic": domestic,
            "domestic_pct": round(100 * domestic / n, 1),
            "n_leagues": len(set(p["code"] for p in squad)),
            "players": plist,
        })

    # rank 1 = most insular (highest domestic share); ties broken by squad size
    rows.sort(key=lambda r: (-r["domestic_pct"], -r["n_players"], r["nation"]))
    for i, r in enumerate(rows):
        r["domestic_rank"] = i + 1

    chips = [{"nation": r["nation"], "code": r["code"], "flag": r["flag"],
              "domestic_pct": r["domestic_pct"], "rank": r["domestic_rank"]}
             for r in rows]
    return {
        "n_players": len(players), "n_nations": len(rows),
        "generated_note": "squad→position→league flows; rank 1 = most domestic-dependent",
        "chips": chips,                       # all 48, ordered most→least insular
        "nations": sorted(rows, key=lambda r: r["nation"]),
    }
