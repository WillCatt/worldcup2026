"""Dixon-Coles bivariate-Poisson goals model with exponential time-decay.

Each team has an attack and defence strength. Expected goals for home team i vs away team j:

    log mu_home = attack_i - defence_j + home_adv      (home_adv = 0 at neutral venues)
    log mu_away = attack_j - defence_i

Goals are Poisson(mu), with the Dixon-Coles low-score correction (rho) coupling the
0-0 / 1-0 / 0-1 / 1-1 cells. Matches are weighted by exp(-xi * age_in_days) so recent
form dominates -- this is the time-series core: strengths reflect the present, not 1950.

Fit by maximum likelihood (L-BFGS-B). Strengths are identifiable up to a constant, so we
pin mean(attack) = 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import factorial

import numpy as np
import pandas as pd
from scipy.optimize import minimize

_FACT = np.array([factorial(k) for k in range(64)], dtype=float)

# Half-life of ~2 years: a match 730 days old counts half as much as today's.
DEFAULT_XI = np.log(2) / 730.0
MAX_GOALS = 10  # truncate the scoreline grid for simulation


def _dc_tau(hg: np.ndarray, ag: np.ndarray, mh: np.ndarray, ma: np.ndarray, rho: float) -> np.ndarray:
    """Dixon-Coles low-score dependency correction."""
    tau = np.ones_like(mh, dtype=float)
    tau = np.where((hg == 0) & (ag == 0), 1.0 - mh * ma * rho, tau)
    tau = np.where((hg == 0) & (ag == 1), 1.0 + mh * rho, tau)
    tau = np.where((hg == 1) & (ag == 0), 1.0 + ma * rho, tau)
    tau = np.where((hg == 1) & (ag == 1), 1.0 - rho, tau)
    return tau


@dataclass
class TeamStrengths:
    attack: dict[str, float]
    defence: dict[str, float]
    home_adv: float
    rho: float
    teams: list[str]

    def expected_goals(self, home: str, away: str, neutral: bool = True) -> tuple[float, float]:
        ha = 0.0 if neutral else self.home_adv
        mu_h = np.exp(self.attack[home] - self.defence[away] + ha)
        mu_a = np.exp(self.attack[away] - self.defence[home])
        return float(mu_h), float(mu_a)

    def score_matrix(self, home: str, away: str, neutral: bool = True) -> np.ndarray:
        """P(home goals = i, away goals = j) over the truncated grid."""
        mu_h, mu_a = self.expected_goals(home, away, neutral)
        i = np.arange(MAX_GOALS + 1)
        ph = np.exp(-mu_h) * mu_h**i / _FACT[: MAX_GOALS + 1]
        pa = np.exp(-mu_a) * mu_a**i / _FACT[: MAX_GOALS + 1]
        grid = np.outer(ph, pa)
        # Dixon-Coles correction on the four low-score cells.
        for (hg, ag) in [(0, 0), (0, 1), (1, 0), (1, 1)]:
            grid[hg, ag] *= _dc_tau(np.array(hg), np.array(ag),
                                    np.array(mu_h), np.array(mu_a), self.rho)
        return grid / grid.sum()

    def outcome_probs(self, home: str, away: str, neutral: bool = True) -> dict[str, float]:
        """P(home win), P(draw), P(away win)."""
        g = self.score_matrix(home, away, neutral)
        return {
            "home": float(np.tril(g, -1).sum()),
            "draw": float(np.trace(g)),
            "away": float(np.triu(g, 1).sum()),
        }


def fit(df: pd.DataFrame, xi: float = DEFAULT_XI, asof: pd.Timestamp | None = None,
        min_matches: int = 30, reg: float = 0.05) -> TeamStrengths:
    """Fit strengths from a results DataFrame, using only matches before `asof`.

    min_matches: drop teams with fewer than this many games in-window (removes the
        non-FIFA / CONIFA micro-teams whose sparse records produce nonsense ratings).
    reg: ridge penalty pulling attack/defence toward 0, for stability on thin samples.
    """
    asof = asof or df["date"].max()
    d = df[df["date"] <= asof].copy()
    # Keep only teams with a real track record; iterate since dropping a team can
    # push its rare opponents below the threshold too.
    while True:
        counts = pd.concat([d.home_team, d.away_team]).value_counts()
        keep = set(counts[counts >= min_matches].index)
        mask = d.home_team.isin(keep) & d.away_team.isin(keep)
        if mask.all():
            break
        d = d[mask]
    teams = sorted(pd.concat([d.home_team, d.away_team]).unique())
    idx = {t: k for k, t in enumerate(teams)}
    n = len(teams)

    age_days = (asof - d["date"]).dt.days.to_numpy()
    w = np.exp(-xi * age_days)
    hi = d.home_team.map(idx).to_numpy()
    ai = d.away_team.map(idx).to_numpy()
    hg = d.home_score.to_numpy()
    ag = d.away_score.to_numpy()
    neutral = d.neutral.to_numpy()

    # params: [attack(n), defence(n), home_adv, rho]; attack pinned via softmax-free centering.
    def unpack(p):
        att = p[:n]
        deff = p[n:2 * n]
        return att - att.mean(), deff, p[2 * n], p[2 * n + 1]

    def negloglik(p):
        att, deff, ha, rho = unpack(p)
        log_mh = att[hi] - deff[ai] + np.where(neutral, 0.0, ha)
        log_ma = att[ai] - deff[hi]
        mh, ma = np.exp(log_mh), np.exp(log_ma)
        # Poisson log-pmf (drop constant log(g!) -- irrelevant to argmax).
        ll = hg * log_mh - mh + ag * log_ma - ma
        tau = _dc_tau(hg, ag, mh, ma, rho)
        ll = ll + np.log(np.clip(tau, 1e-9, None))
        penalty = reg * (np.sum(att**2) + np.sum(deff**2))
        return -np.sum(w * ll) + penalty

    x0 = np.concatenate([np.zeros(2 * n), [0.25, -0.05]])
    bounds = [(-3, 3)] * (2 * n) + [(0.0, 1.0), (-0.2, 0.2)]
    res = minimize(negloglik, x0, method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": 400, "maxfun": 50000})
    att, deff, ha, rho = unpack(res.x)
    return TeamStrengths(
        attack=dict(zip(teams, att)),
        defence=dict(zip(teams, deff)),
        home_adv=float(ha),
        rho=float(rho),
        teams=teams,
    )


if __name__ == "__main__":
    from src import data

    df = data.load()
    # Fit on the modern era for speed/relevance.
    df = df[df.date >= "2006-01-01"]
    s = fit(df)
    print(f"Fit on {len(df):,} matches, {s.teams.__len__()} teams. "
          f"home_adv={s.home_adv:.3f}, rho={s.rho:.3f}\n")
    # Overall strength = attack + defence (higher defence => concedes fewer).
    top = sorted(s.attack, key=lambda t: s.attack[t] + s.defence[t], reverse=True)[:15]
    print("Top 15 by overall strength (attack + defence):")
    for t in top:
        print(f"  {t:<18} att={s.attack[t]:+.2f}  def={s.defence[t]:+.2f}  "
              f"sum={s.attack[t] + s.defence[t]:+.2f}")
    print("\nSpain vs Argentina (neutral):", s.outcome_probs("Spain", "Argentina"))
