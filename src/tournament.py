"""2026 World Cup structure: groups, third-place rules, and the exact knockout bracket.

The R32 pairings and knockout flow are the official 2026 bracket (FIFA / Wikipedia).
Group winners and runners-up have fixed slots. The eight best third-placed teams fill
eight slots, each constrained to a set of eligible groups; we assign them with a
constraint-respecting matching (faithful to the eligibility structure -- the exact
permutation among valid assignments has negligible effect on title odds).
"""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# groups.json team names -> results.csv / ratings team names.
NAME_ALIASES = {
    "Curacao": "Curaçao",
}

# R32 bracket (match no. -> two sides). Side encodings:
#   ("W", "A")  winner of group A
#   ("R", "A")  runner-up of group A
#   ("3", frozenset({...}))  a third-placed team from one of the listed groups
R32 = {
    73: (("R", "A"), ("R", "B")),
    74: (("W", "E"), ("3", frozenset("ABCDF"))),
    75: (("W", "F"), ("R", "C")),
    76: (("W", "C"), ("R", "F")),
    77: (("W", "I"), ("3", frozenset("CDFGH"))),
    78: (("R", "E"), ("R", "I")),
    79: (("W", "A"), ("3", frozenset("CEFHI"))),
    80: (("W", "L"), ("3", frozenset("EHIJK"))),
    81: (("W", "D"), ("3", frozenset("BEFIJ"))),
    82: (("W", "G"), ("3", frozenset("AEHIJ"))),
    83: (("R", "K"), ("R", "L")),
    84: (("W", "H"), ("R", "J")),
    85: (("W", "B"), ("3", frozenset("EFGIJ"))),
    86: (("W", "J"), ("R", "H")),
    87: (("W", "K"), ("3", frozenset("DEIJL"))),
    88: (("R", "D"), ("R", "G")),
}

# Knockout flow: match no. -> (winner-of, winner-of).
KO = {
    89: (74, 77), 90: (73, 75), 91: (76, 78), 92: (79, 80),
    93: (83, 84), 94: (81, 82), 95: (86, 88), 96: (85, 87),
    97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96),
    101: (97, 98), 102: (99, 100),
    104: (101, 102),
}

# Round labels for reporting how far each team goes.
ROUND_OF = {**{m: "R32" for m in R32}, **{m: r for m, r in zip(
    list(range(89, 97)) + list(range(97, 101)) + [101, 102] + [104],
    ["R16"] * 8 + ["QF"] * 4 + ["SF", "SF", "F"])}}

THIRD_SLOTS = [m for m, (a, b) in R32.items() if b[0] == "3"]  # 74,77,79,80,81,82,85,87


def load_groups() -> dict[str, list[str]]:
    """Return {group_letter: [team, ...]} with names mapped to ratings conventions."""
    raw = json.loads((DATA_DIR / "groups.json").read_text())["groups"]
    return {g: [NAME_ALIASES.get(t, t) for t in teams] for g, teams in raw.items()}


def all_teams() -> list[str]:
    return [t for teams in load_groups().values() for t in teams]


def assign_thirds(qualified_groups: list[str], rng) -> dict[int, str] | None:
    """Assign the groups whose thirds qualified to the 8 third-slots, respecting
    each slot's eligible-group set. Returns {match_no: group_letter} or None if no
    valid assignment exists (shuffle order to vary among valid matchings)."""
    slots = list(THIRD_SLOTS)
    rng.shuffle(slots)
    elig = {m: R32[m][1][1] for m in slots}
    assignment: dict[int, str] = {}
    used: set[str] = set()

    def backtrack(i: int) -> bool:
        if i == len(slots):
            return True
        m = slots[i]
        cands = [g for g in qualified_groups if g not in used and g in elig[m]]
        rng.shuffle(cands)
        for g in cands:
            assignment[m], _ = g, used.add(g)
            if backtrack(i + 1):
                return True
            del assignment[m]
            used.discard(g)
        return False

    return assignment if backtrack(0) else None
