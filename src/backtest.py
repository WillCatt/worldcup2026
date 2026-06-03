"""Validate the goals model out-of-sample on the 2018 & 2022 World Cups.

For each tournament we fit strengths using only matches *before* the opening day, then
predict every actual World Cup match (group + knockout). We score the model's
home/draw/away probabilities against outcomes with log-loss, Brier score and accuracy,
and compare to a climatology baseline (the historical base rates of W/D/L in World Cup
matches). A calibration curve shows whether stated probabilities match observed
frequencies. This is the "honest results" layer: trust the forecast only if it earns it.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import data, ratings

FIG_DIR = Path(__file__).resolve().parent.parent / "figures"

# Portfolio palette (matches the site's warm-ivory house style).
INK = "#1a1714"
ACCENT = "#b5651d"
GRID = "#d9d2c7"
BG = "#faf8f4"

WORLD_CUPS = {2018: ("2018-06-14", "2018-07-15"), 2022: ("2022-11-20", "2022-12-18")}


def _result_probs_outcome(row, strengths) -> tuple[np.ndarray, int]:
    """Return (p[home,draw,away], actual_outcome_index) for a played match."""
    h, a = row.home_team, row.away_team
    p = strengths.outcome_probs(h, a, neutral=bool(row.neutral))
    probs = np.array([p["home"], p["draw"], p["away"]])
    if row.home_score > row.away_score:
        y = 0
    elif row.home_score == row.away_score:
        y = 1
    else:
        y = 2
    return probs / probs.sum(), y


def backtest_year(df: pd.DataFrame, year: int) -> dict:
    start, end = WORLD_CUPS[year]
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    strengths = ratings.fit(df, asof=start - pd.Timedelta(days=1))
    wc = df[(df.tournament == "FIFA World Cup") & (df.date >= start) & (df.date <= end)]
    rated = strengths.attack
    rows = [r for r in wc.itertuples() if r.home_team in rated and r.away_team in rated]

    P, Y = [], []
    for r in rows:
        p, y = _result_probs_outcome(r, strengths)
        P.append(p); Y.append(y)
    P, Y = np.array(P), np.array(Y)

    onehot = np.eye(3)[Y]
    eps = 1e-12
    logloss = float(-np.mean(np.sum(onehot * np.log(P + eps), axis=1)))
    brier = float(np.mean(np.sum((P - onehot) ** 2, axis=1)))
    acc = float(np.mean(P.argmax(1) == Y))

    # Climatology baseline: predict the base rates of W/D/L every match.
    base = onehot.mean(0)
    base_ll = float(-np.mean(np.sum(onehot * np.log(np.tile(base, (len(Y), 1)) + eps), axis=1)))

    return {"year": year, "n": len(Y), "log_loss": logloss, "brier": brier,
            "accuracy": acc, "baseline_log_loss": base_ll, "P": P, "Y": Y}


def calibration_plot(results: list[dict], path: Path) -> None:
    """Reliability curve: binned predicted prob vs observed frequency, all outcomes pooled."""
    P = np.vstack([r["P"] for r in results]).ravel()
    Y = np.vstack([np.eye(3)[r["Y"]] for r in results]).ravel()
    bins = np.linspace(0, 1, 11)
    idx = np.clip(np.digitize(P, bins) - 1, 0, 9)
    xs, ys, ns = [], [], []
    for b in range(10):
        m = idx == b
        if m.sum() > 0:
            xs.append(P[m].mean()); ys.append(Y[m].mean()); ns.append(m.sum())

    fig, ax = plt.subplots(figsize=(6, 6), dpi=130)
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    ax.plot([0, 1], [0, 1], "--", color=GRID, lw=1.5, zorder=1, label="perfect calibration")
    sizes = 40 + 600 * np.array(ns) / max(ns)
    ax.scatter(xs, ys, s=sizes, color=ACCENT, alpha=0.85, edgecolor=INK, lw=0.8, zorder=3)
    ax.plot(xs, ys, color=ACCENT, lw=1.5, alpha=0.5, zorder=2)
    ax.set_xlabel("Predicted probability", color=INK)
    ax.set_ylabel("Observed frequency", color=INK)
    ax.set_title("Model calibration — 2018 & 2022 World Cups\n(marker size ∝ matches in bin)",
                 color=INK, fontsize=12)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.tick_params(colors=INK)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.legend(frameon=False, labelcolor=INK)
    fig.tight_layout()
    FIG_DIR.mkdir(exist_ok=True)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def run() -> None:
    df = data.load()
    results = [backtest_year(df, y) for y in WORLD_CUPS]
    print("Out-of-sample World Cup backtest:\n")
    print(f"{'Cup':>6} {'matches':>8} {'log-loss':>9} {'baseline':>9} {'Brier':>7} {'acc':>6}")
    for r in results:
        print(f"{r['year']:>6} {r['n']:>8} {r['log_loss']:>9.3f} "
              f"{r['baseline_log_loss']:>9.3f} {r['brier']:>7.3f} {r['accuracy']*100:>5.0f}%")
    pooled_ll = np.mean([r["log_loss"] for r in results])
    pooled_base = np.mean([r["baseline_log_loss"] for r in results])
    print(f"\nModel log-loss {pooled_ll:.3f} vs climatology {pooled_base:.3f} "
          f"({'better' if pooled_ll < pooled_base else 'worse'} by {abs(pooled_ll-pooled_base):.3f}).")
    calibration_plot(results, FIG_DIR / "calibration.png")
    print(f"Calibration figure → figures/calibration.png")


if __name__ == "__main__":
    run()
