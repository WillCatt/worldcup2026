"""Load the international-results history.

Source: martj42/international_results on GitHub (no auth, raw CSV).
Columns: date, home_team, away_team, home_score, away_score, tournament, city, country, neutral
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_CSV = DATA_DIR / "results.csv"


def download(force: bool = False) -> Path:
    """Fetch results.csv to data/ (cached unless force=True)."""
    DATA_DIR.mkdir(exist_ok=True)
    if RESULTS_CSV.exists() and not force:
        return RESULTS_CSV
    resp = requests.get(RESULTS_URL, timeout=60)
    resp.raise_for_status()
    RESULTS_CSV.write_bytes(resp.content)
    return RESULTS_CSV


def load(force_download: bool = False) -> pd.DataFrame:
    """Return the results history as a typed, date-sorted DataFrame (played games only)."""
    if force_download or not RESULTS_CSV.exists():
        download(force=force_download)
    df = pd.read_csv(RESULTS_CSV, parse_dates=["date"])
    df = df.dropna(subset=["home_score", "away_score"]).copy()
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    df["neutral"] = df["neutral"].astype(bool)
    return df.sort_values("date").reset_index(drop=True)
