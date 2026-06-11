"""Turning bookmaker odds into probabilities — and stripping the margin.

A book's decimal odds imply probabilities that sum to more than one; the excess is the
*overround* (the bookmaker's margin). To compare a book to a model you must remove it. Two
standard methods are implemented, and they are NOT equivalent:

* **proportional** — divide each raw implied probability by the booksum. Simple, and the
  implicit default everywhere, but it assumes the margin is spread evenly across outcomes.
* **Shin** — models the margin as protection against insider traders, which concentrates it
  on longshots. It solves for the insider proportion ``z`` such that the de-vigged
  probabilities sum to one. At ``z = 0`` it collapses exactly to proportional.

They agree on near-coin-flips and **diverge on longshots** — Shin pulls long-odds outcomes
toward shorter implied probabilities. That divergence is a write-up section, not a footnote,
which is why ``compare`` returns both side by side. Closing Sportsbet de-vigged with Shin is
the benchmark the model is scored against.
"""
from __future__ import annotations

from scipy.optimize import brentq


def overround(odds: list[float]) -> float:
    """Booksum minus one, from decimal odds."""
    return sum(1.0 / o for o in odds) - 1.0


def proportional(odds: list[float]) -> list[float]:
    """De-vig by normalising raw implied probabilities to sum to 1."""
    imp = [1.0 / o for o in odds]
    s = sum(imp)
    return [p / s for p in imp]


def _shin_probs(odds: list[float], z: float) -> list[float]:
    imp = [1.0 / o for o in odds]
    booksum = sum(imp)
    return [(((z * z + 4 * (1 - z) * pi * pi / booksum) ** 0.5) - z) / (2 * (1 - z))
            for pi in imp]


def shin(odds: list[float]) -> tuple[list[float], float]:
    """De-vig with Shin's method. Returns (probabilities, z). z is the implied insider
    fraction; z→0 means the margin looks evenly spread (≈ proportional)."""
    if overround(odds) <= 1e-9:
        p = proportional(odds)
        return p, 0.0
    f = lambda z: sum(_shin_probs(odds, z)) - 1.0
    # f(0) = booksum-normalised sum > 1 with the raw scaling; bracket z in (0, ~0.5)
    lo, hi = 1e-6, 0.5
    while f(hi) > 0 and hi < 0.999:
        hi += 0.1
    z = brentq(f, lo, min(hi, 0.999), xtol=1e-10)
    p = _shin_probs(odds, z)
    s = sum(p)
    return [x / s for x in p], z  # tiny renormalise for numerical safety


def devig(odds: list[float], method: str = "shin") -> list[float]:
    """Convenience: de-vigged 1X2 probabilities by the named method."""
    if method == "proportional":
        return proportional(odds)
    if method == "shin":
        return shin(odds)[0]
    raise ValueError(f"unknown devig method {method!r}")


def compare(odds: list[float], labels=("home", "draw", "away")) -> dict:
    """Both methods side by side, plus the per-outcome gap — for the methods note."""
    prop = proportional(odds)
    sh, z = shin(odds)
    return {
        "odds": odds,
        "overround": overround(odds),
        "shin_z": z,
        "by_outcome": [
            {"outcome": labels[i], "proportional": prop[i], "shin": sh[i],
             "gap": sh[i] - prop[i]}
            for i in range(len(odds))
        ],
    }


if __name__ == "__main__":
    # A lopsided market (heavy favourite + longshot) shows the divergence; a coin-flip doesn't.
    for tag, odds in [("favourite/longshot", [1.25, 6.0, 12.0]),
                      ("near coin-flip", [2.6, 3.3, 2.7])]:
        c = compare(odds)
        print(f"\n{tag}: odds={odds}  overround={c['overround']:.1%}  z={c['shin_z']:.3f}")
        for r in c["by_outcome"]:
            print(f"  {r['outcome']:<5} prop={r['proportional']:.3f}  "
                  f"shin={r['shin']:.3f}  gap={r['gap']:+.3f}")
