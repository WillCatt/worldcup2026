"""Build portfolio figures + demo JSON for the World Cup 2026 page.

Outputs (palette-matched to williamcatt.dev) into site/assets/worldcup/:
  - title_odds.png        top-16 win probabilities (winner highlighted)
  - model_vs_market.png   model vs de-vigged Australian market
  - calibration.png       reliability curve from the 2018/2022 backtest
  - market.json           de-vigged market implied probabilities (for the demo)
  - forecast.json         (copied from output/ by the caller)

Run from repo root:  python -m figures.build_portfolio_figures
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from src import backtest, data, market

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "assets" / "worldcup"

# Portfolio palette (matches the skill / project.css).
BG = "#faf8f4"; INK = "#1a1714"; MUTED = "#7a6e63"; GRID = "#e6ded2"
AMBER = "#b06a16"; GREY = "#cdbfae"; GREEN = "#3a8f57"; TEAL = "#2a8f8f"

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
    "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": MUTED,
    "axes.edgecolor": GRID, "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True,
    "font.size": 12, "font.family": "DejaVu Sans",
})


def _bare(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def title_odds_fig(forecast: dict, path: Path, n: int = 16) -> None:
    teams = list(forecast["teams"].items())[:n]
    names = [t for t, _ in teams][::-1]
    wins = [r["win"] * 100 for _, r in teams][::-1]
    colors = [AMBER if i == len(names) - 1 else GREY for i in range(len(names))]

    fig, ax = plt.subplots(figsize=(8, 6.5), dpi=200)
    ax.barh(names, wins, color=colors, edgecolor=INK, linewidth=0.5)
    ax.grid(axis="y", visible=False)
    for y, w in enumerate(wins):
        ax.text(w + max(wins) * 0.01, y, f"{w:.1f}%", va="center", ha="left",
                fontsize=10, color=INK)
    ax.set_xlabel("Probability of winning the tournament (%)")
    ax.set_title("Who wins the 2026 World Cup?", loc="left", fontweight="bold")
    ax.set_xlim(0, max(wins) * 1.12)
    _bare(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def market_fig(path: Path) -> None:
    rows = market.compare()
    mkt, overround = market.market_probs()
    fig, ax = plt.subplots(figsize=(7.5, 7.5), dpi=200)
    mx = max(max(r["model"], r["market"]) for r in rows) * 1.08
    ax.plot([0, mx], [0, mx], "--", color=GREY, lw=1.5, zorder=1, label="model = market")
    for r in rows:
        ax.scatter(r["market"], r["model"], s=48,
                   color=AMBER if r["edge"] > 0 else TEAL, alpha=0.85,
                   edgecolor=INK, lw=0.5, zorder=3)
    for r in sorted(rows, key=lambda r: abs(r["edge"]), reverse=True)[:8]:
        ax.annotate(r["team"], (r["market"], r["model"]),
                    xytext=(5, 4), textcoords="offset points", fontsize=9, color=INK)
    ax.set_xlabel("Market implied probability (de-vigged)")
    ax.set_ylabel("Model probability")
    ax.set_title(f"Model vs the Australian betting market\n"
                 f"amber = model rates higher · teal = lower · "
                 f"bookmaker overround {overround*100:.0f}%",
                 loc="left", fontweight="bold", fontsize=12)
    ax.set_xlim(0, mx); ax.set_ylim(0, mx)
    ax.legend(frameon=False, loc="upper left")
    _bare(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def calibration_fig(path: Path) -> None:
    df = data.load()
    results = [backtest.backtest_year(df, y) for y in backtest.WORLD_CUPS]
    P = np.vstack([r["P"] for r in results]).ravel()
    Y = np.vstack([np.eye(3)[r["Y"]] for r in results]).ravel()
    bins = np.linspace(0, 1, 11)
    idx = np.clip(np.digitize(P, bins) - 1, 0, 9)
    xs, ys, ns = [], [], []
    for b in range(10):
        m = idx == b
        if m.sum():
            xs.append(P[m].mean()); ys.append(Y[m].mean()); ns.append(m.sum())

    pooled_ll = np.mean([r["log_loss"] for r in results])
    pooled_base = np.mean([r["baseline_log_loss"] for r in results])

    fig, ax = plt.subplots(figsize=(6.5, 6.5), dpi=200)
    ax.plot([0, 1], [0, 1], "--", color=GREY, lw=1.5, label="perfect calibration")
    ax.plot(xs, ys, color=AMBER, lw=1.5, alpha=0.5, zorder=2)
    ax.scatter(xs, ys, s=40 + 600 * np.array(ns) / max(ns),
               color=AMBER, alpha=0.85, edgecolor=INK, lw=0.7, zorder=3)
    ax.set_xlabel("Predicted probability")
    ax.set_ylabel("Observed frequency")
    ax.set_title("Is the model honest about its uncertainty?", loc="left", fontweight="bold")
    ax.text(0.03, 0.93, f"out-of-sample log-loss {pooled_ll:.2f}\nvs climatology {pooled_base:.2f}",
            transform=ax.transAxes, fontsize=10, color=MUTED, va="top")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.legend(frameon=False, loc="lower right")
    _bare(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def export_market_json(path: Path) -> None:
    mkt, overround = market.market_probs()
    path.write_text(json.dumps(
        {"overround": round(overround, 4), "implied": {t: round(p, 4) for t, p in mkt.items()}},
        indent=2, ensure_ascii=False))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    forecast = json.loads((ROOT / "output" / "forecast.json").read_text())
    title_odds_fig(forecast, OUT / "title_odds.png")
    market_fig(OUT / "model_vs_market.png")
    calibration_fig(OUT / "calibration.png")
    export_market_json(OUT / "market.json")
    # keep the demo's forecast.json in sync
    (OUT / "forecast.json").write_text(json.dumps(forecast, indent=2, ensure_ascii=False))
    print(f"Wrote figures + market.json + forecast.json → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
