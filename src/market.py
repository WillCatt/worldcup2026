"""Model vs the betting market.

Australian bookmakers price the outright winner with a hefty margin (the "overround":
implied probabilities that sum to well over 100%). We strip that margin by proportional
normalisation to get the market's true implied win probabilities, then line them up
against the model. Where the two disagree is the interesting part -- and the honest test
of whether the model is finding anything the market hasn't, or just kidding itself.

This is the betting-markets through-line shared with the Blackjack project: the market is
a brutally efficient benchmark, and "we mostly agree, here's where we don't" is the result.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
FIG_DIR = ROOT / "figures"
OUTPUT = ROOT / "output"

INK = "#1a1714"
ACCENT = "#b5651d"
COOL = "#3f6f6f"
GRID = "#d9d2c7"
BG = "#faf8f4"


def market_probs() -> tuple[dict[str, float], float]:
    """Return (de-vigged win probs, overround). Overround = raw implied sum - 1."""
    raw = json.loads((DATA_DIR / "market_odds.json").read_text())["odds"]
    implied = {t: 1.0 / o for t, o in raw.items()}
    total = sum(implied.values())
    return {t: p / total for t, p in implied.items()}, total - 1.0


def compare() -> list[dict]:
    """Join model title odds (output/forecast.json) with de-vigged market odds."""
    forecast = json.loads((OUTPUT / "forecast.json").read_text())["teams"]
    mkt, _ = market_probs()
    rows = []
    for team, m in mkt.items():
        model = forecast.get(team, {}).get("win", 0.0)
        rows.append({"team": team, "model": model, "market": m, "edge": model - m})
    rows.sort(key=lambda r: r["market"], reverse=True)
    return rows


def plot(rows: list[dict], overround: float, path: Path) -> None:
    """Scatter model vs market win prob with a y=x line; annotate biggest divergences."""
    fig, ax = plt.subplots(figsize=(7, 7), dpi=130)
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    mx = max(max(r["model"], r["market"]) for r in rows) * 1.08
    ax.plot([0, mx], [0, mx], "--", color=GRID, lw=1.5, zorder=1, label="model = market")

    for r in rows:
        over = r["edge"] > 0
        ax.scatter(r["market"], r["model"], s=46,
                   color=ACCENT if over else COOL, alpha=0.85,
                   edgecolor=INK, lw=0.6, zorder=3)
    # Label the teams the model disagrees with most, plus the clear favourites.
    notable = sorted(rows, key=lambda r: abs(r["edge"]), reverse=True)[:8]
    for r in notable:
        ax.annotate(r["team"], (r["market"], r["model"]),
                    xytext=(5, 4), textcoords="offset points",
                    fontsize=8.5, color=INK)

    ax.set_xlabel("Market implied probability (de-vigged)", color=INK)
    ax.set_ylabel("Model probability", color=INK)
    ax.set_title(f"Model vs the betting market — title odds\n"
                 f"(amber = model higher than market; teal = lower; "
                 f"bookmaker overround {overround*100:.0f}%)",
                 color=INK, fontsize=11.5)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors=INK)
    ax.set_xlim(0, mx); ax.set_ylim(0, mx)
    ax.legend(frameon=False, labelcolor=INK, loc="upper left")
    fig.tight_layout()
    FIG_DIR.mkdir(exist_ok=True)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def run() -> None:
    rows = compare()
    mkt, overround = market_probs()
    print(f"Australian bookmaker overround on the outright market: {overround*100:.1f}%\n")
    print(f"{'Team':<16}{'market':>8}{'model':>8}{'edge':>8}")
    for r in rows[:16]:
        print(f"{r['team']:<16}{r['market']*100:>7.1f}%{r['model']*100:>7.1f}%"
              f"{r['edge']*100:>+7.1f}%")
    print("\nBiggest disagreements (|model - market|):")
    for r in sorted(rows, key=lambda x: abs(x["edge"]), reverse=True)[:6]:
        side = "model higher" if r["edge"] > 0 else "model lower"
        print(f"  {r['team']:<16} {side:<13} ({r['edge']*100:+.1f} pts)")
    plot(rows, overround, FIG_DIR / "model_vs_market.png")
    print("\nFigure → figures/model_vs_market.png")


if __name__ == "__main__":
    run()
