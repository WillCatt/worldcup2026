"""The international football match-graph: structure, communities, and a ranking.

Thesis: national teams overwhelmingly play *within* their own confederation, so the
match graph is clustered by continent with only thin "bridge" games linking the blocs.
That sparse cross-continental connectivity is why ranking teams across confederations
is genuinely hard.

This module provides clean primitives the notebooks narrate over and the web export
consumes. Layout is deliberately *not* computed here -- the D3 page force-directs the
graph in the browser so it's interactive.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import networkx as nx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONF_JSON = DATA_DIR / "confederations.json"

DEFAULT_WINDOW = "2006-01-01"
DEFAULT_HALFLIFE_DAYS = 8 * 365.0
DEFAULT_MIN_MATCHES = 25

CONF_ORDER = ["UEFA", "CONMEBOL", "CONCACAF", "CAF", "AFC", "OFC"]


def load_confederations() -> dict[str, str]:
    """team -> confederation code. {} if the map is absent."""
    if CONF_JSON.exists():
        members = json.loads(CONF_JSON.read_text())
        return {team: conf for conf, teams in members.items() for team in teams}
    return {}


def filter_window(df: pd.DataFrame, window_start: str = DEFAULT_WINDOW,
                  min_matches: int = DEFAULT_MIN_MATCHES) -> pd.DataFrame:
    """Modern window + iterative min-matches filter (drops micro/non-FIFA teams)."""
    d = df[df["date"] >= window_start].copy()
    while True:
        counts = pd.concat([d.home_team, d.away_team]).value_counts()
        keep = set(counts[counts >= min_matches].index)
        mask = d.home_team.isin(keep) & d.away_team.isin(keep)
        if mask.all():
            break
        d = d[mask]
    return d


def _decay_weights(d: pd.DataFrame, half_life: float) -> np.ndarray:
    age = (d["date"].max() - d["date"]).dt.days.to_numpy()
    return np.exp(-np.log(2) / half_life * age)


def build_undirected(df: pd.DataFrame, window_start: str = DEFAULT_WINDOW,
                     half_life: float = DEFAULT_HALFLIFE_DAYS,
                     min_matches: int = DEFAULT_MIN_MATCHES) -> nx.Graph:
    """Recency-weighted 'who-plays-whom' graph; edge weight = how connected today."""
    d = filter_window(df, window_start, min_matches)
    w = _decay_weights(d, half_life)
    G = nx.Graph()
    for h, a, wt in zip(d.home_team, d.away_team, w):
        if G.has_edge(h, a):
            G[h][a]["weight"] += wt
            G[h][a]["games"] += 1
        else:
            G.add_edge(h, a, weight=float(wt), games=1)
    conf = load_confederations()
    nx.set_node_attributes(G, {n: conf.get(n, "??") for n in G}, "confederation")
    return G


def build_directed(df: pd.DataFrame, window_start: str = DEFAULT_WINDOW,
                   half_life: float = DEFAULT_HALFLIFE_DAYS,
                   min_matches: int = DEFAULT_MIN_MATCHES) -> nx.DiGraph:
    """Directed 'beat-graph': edge loser -> winner, weighted by recency * margin."""
    d = filter_window(df, window_start, min_matches)
    decay = _decay_weights(d, half_life)
    G = nx.DiGraph()

    def add(src, dst, wt):
        if G.has_edge(src, dst):
            G[src][dst]["weight"] += wt
        else:
            G.add_edge(src, dst, weight=float(wt))

    for h, a, hs, as_, dec in zip(d.home_team, d.away_team,
                                  d.home_score, d.away_score, decay):
        margin = 1.0 + np.log1p(abs(hs - as_))
        if hs > as_:
            add(a, h, dec * margin)
        elif as_ > hs:
            add(h, a, dec * margin)
        else:
            add(h, a, dec * 0.5)
            add(a, h, dec * 0.5)
    conf = load_confederations()
    nx.set_node_attributes(G, {n: conf.get(n, "??") for n in G}, "confederation")
    return G


def connectivity_report(G: nx.Graph) -> dict:
    """Within- vs cross-confederation edge-weight share + per-confed insularity."""
    conf = nx.get_node_attributes(G, "confederation")
    within = cross = 0.0
    per_within: dict[str, float] = {}
    per_total: dict[str, float] = {}
    for u, v, wt in G.edges(data="weight"):
        cu, cv = conf[u], conf[v]
        per_total[cu] = per_total.get(cu, 0.0) + wt
        per_total[cv] = per_total.get(cv, 0.0) + wt
        if cu == cv and cu != "??":
            within += wt
            per_within[cu] = per_within.get(cu, 0.0) + 2 * wt
        else:
            cross += wt
    total = within + cross
    insularity = {c: per_within.get(c, 0.0) / per_total[c]
                  for c in per_total if c != "??"}
    return {
        "within_share": within / total if total else float("nan"),
        "cross_share": cross / total if total else float("nan"),
        "insularity": insularity,
        "n_teams": G.number_of_nodes(),
        "n_edges": G.number_of_edges(),
    }


def communities(G: nx.Graph, seed: int = 42) -> dict:
    """Louvain communities vs the real confederation partition."""
    comms = nx.community.louvain_communities(G, weight="weight", seed=seed)
    node_comm = {n: i for i, c in enumerate(comms) for n in c}
    conf = nx.get_node_attributes(G, "confederation")
    labelled = [n for n in G if conf[n] != "??"]
    true = np.array([conf[n] for n in labelled])
    pred = np.array([node_comm[n] for n in labelled])
    return {
        "n_communities": len(comms),
        "modularity_confed": nx.community.modularity(
            G, _partition(G, conf), weight="weight"),
        "modularity_louvain": nx.community.modularity(G, comms, weight="weight"),
        "nmi": _nmi(true, pred),
        "node_comm": node_comm,
    }


def pagerank_ranking(G: nx.DiGraph) -> pd.DataFrame:
    """Network power ranking from PageRank on the beat-graph."""
    pr = nx.pagerank(G, weight="weight")
    conf = nx.get_node_attributes(G, "confederation")
    out = pd.DataFrame([{"team": t, "pagerank": s, "confederation": conf[t]}
                        for t, s in pr.items()]).sort_values("pagerank", ascending=False)
    out["rank"] = np.arange(1, len(out) + 1)
    return out.reset_index(drop=True)


def cross_share(G: nx.Graph) -> dict[str, float]:
    """Per-team share of (weighted) games played outside its confederation."""
    conf = nx.get_node_attributes(G, "confederation")
    out = {}
    for n in G:
        tot = sum(G[n][m]["weight"] for m in G[n])
        crs = sum(G[n][m]["weight"] for m in G[n] if conf[m] != conf[n])
        out[n] = crs / tot if tot else 0.0
    return out


def bridge_teams(G: nx.Graph, top_n: int = 10, min_games: int = 40) -> list[str]:
    """Most cross-confederational well-connected teams -- the global graph's bridges."""
    cs = cross_share(G)
    deg = {n: sum(G[n][m]["games"] for m in G[n]) for n in G}
    ranked = sorted((n for n in G if deg[n] >= min_games), key=lambda n: -cs[n])
    return ranked[:top_n]


def to_graph_export(Gu: nx.Graph, Gd: nx.DiGraph, edge_min_games: int = 2) -> dict:
    """Assemble the nodes/links/metrics payload the D3 page force-directs in-browser.

    edge_min_games trims one-off meetings so the browser graph stays legible.
    """
    pr = nx.pagerank(Gd, weight="weight")
    comm = communities(Gu)["node_comm"]
    cs = cross_share(Gu)
    conf = nx.get_node_attributes(Gu, "confederation")
    rep = connectivity_report(Gu)

    nodes = [{
        "id": n,
        "conf": conf[n],
        "pagerank": round(pr.get(n, 0.0), 6),
        "community": comm[n],
        "cross": round(cs[n], 3),
        "degree": Gu.degree(n),
    } for n in Gu.nodes()]

    links = [{
        "source": u, "target": v,
        "weight": round(Gu[u][v]["weight"], 3),
        "cross": conf[u] != conf[v],
    } for u, v in Gu.edges() if Gu[u][v]["games"] >= edge_min_games]

    return {
        "nodes": sorted(nodes, key=lambda d: -d["pagerank"]),
        "links": links,
        "conf_order": CONF_ORDER,
        "metrics": {
            "within_share": round(rep["within_share"], 4),
            "cross_share": round(rep["cross_share"], 4),
            "insularity": {k: round(v, 4) for k, v in rep["insularity"].items()},
            "n_teams": rep["n_teams"],
            "n_edges": rep["n_edges"],
            **{k: communities(Gu)[k] for k in
               ("n_communities", "nmi", "modularity_confed", "modularity_louvain")},
            "bridges": bridge_teams(Gu),
        },
    }


# ---- internal helpers -------------------------------------------------------

def _partition(G: nx.Graph, labels: dict[str, str]) -> list[set]:
    groups: dict[str, set] = {}
    for n in G:
        groups.setdefault(labels[n], set()).add(n)
    return list(groups.values())


def _nmi(true: np.ndarray, pred: np.ndarray) -> float:
    """Normalised mutual information between two labelings (no sklearn dep)."""
    def entropy(x):
        _, c = np.unique(x, return_counts=True)
        p = c / c.sum()
        return -np.sum(p * np.log(p))
    n = len(true)
    tu = {v: i for i, v in enumerate(np.unique(true))}
    pu = {v: i for i, v in enumerate(np.unique(pred))}
    cm = np.zeros((len(tu), len(pu)))
    for t, p in zip(true, pred):
        cm[tu[t], pu[p]] += 1
    pij = cm / n
    pi = pij.sum(1, keepdims=True)
    pj = pij.sum(0, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        mi = np.nansum(pij * np.log(pij / (pi * pj)))
    ht, hp = entropy(true), entropy(pred)
    return float(mi / np.sqrt(ht * hp)) if ht > 0 and hp > 0 else 0.0
