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


def flow_matrix(G: nx.Graph, order: list[str] = CONF_ORDER) -> np.ndarray:
    """Symmetric confederation x confederation match-flow matrix (endpoint-incidence).

    M[i][j] = recency-weighted volume of games whose two endpoints sit in confederations
    i and j. Within-confederation games (both endpoints in i) land on the diagonal counted
    *twice* (once per endpoint), so each row sums to that confederation's total match
    incidence and M[i][i] / rowsum reproduces ``connectivity_report`` insularity exactly --
    one consistent definition feeds the chord ribbons, the heatmap, and the insularity bars.
    """
    idx = {c: i for i, c in enumerate(order)}
    conf = nx.get_node_attributes(G, "confederation")
    M = np.zeros((len(order), len(order)))
    for u, v, wt in G.edges(data="weight"):
        cu, cv = conf[u], conf[v]
        if cu not in idx or cv not in idx:
            continue
        i, j = idx[cu], idx[cv]
        if i == j:
            M[i, i] += 2 * wt           # both endpoints home -> diagonal, counted twice
        else:
            M[i, j] += wt
            M[j, i] += wt
    return M


def to_aggregate_export(Gu: nx.Graph) -> dict:
    """Small confederation-level payload for the redesigned charts.

    Ships ~6x6 numbers, not 217 nodes: the flow matrix (chord + heatmap), per-confederation
    insularity (bars), the bridge teams with their cross-share (bars), and the headline
    structure/community metrics. A few KB instead of ~290 KB -- legible by construction.
    """
    rep = connectivity_report(Gu)
    com = communities(Gu)
    conf = nx.get_node_attributes(Gu, "confederation")
    cs = cross_share(Gu)
    M = flow_matrix(Gu)

    # Which detected community each confederation predominantly falls into (the Americas merge).
    from collections import Counter
    comm_of = com["node_comm"]
    conf_community: dict[str, int] = {}
    for c in CONF_ORDER:
        members = [comm_of[n] for n in Gu if conf[n] == c]
        if members:
            conf_community[c] = Counter(members).most_common(1)[0][0]

    deg_games = {n: sum(Gu[n][m]["games"] for m in Gu[n]) for n in Gu}
    bridges = [{
        "team": t,
        "conf": conf[t],
        "cross": round(cs[t], 3),
        "games": deg_games[t],
    } for t in bridge_teams(Gu)]

    return {
        "conf_order": CONF_ORDER,
        "matrix": [[round(x, 2) for x in row] for row in M.tolist()],
        "insularity": {k: round(v, 4) for k, v in rep["insularity"].items()},
        "bridges": bridges,
        "conf_community": conf_community,
        "metrics": {
            "within_share": round(rep["within_share"], 4),
            "cross_share": round(rep["cross_share"], 4),
            "n_teams": rep["n_teams"],
            "n_edges": rep["n_edges"],
            "n_communities": com["n_communities"],
            "nmi": round(com["nmi"], 4),
            "modularity_confed": round(com["modularity_confed"], 4),
            "modularity_louvain": round(com["modularity_louvain"], 4),
        },
        "smallworld": smallworld_stats(Gu),
        "centrality": centrality_table(Gu),
        "resolution_sweep": resolution_sweep(Gu),
        "nested": nested_partition(Gu),
        "robustness": robustness(Gu),
    }


def smallworld_stats(G: nx.Graph) -> dict:
    """Is the match graph a 'small world'? Path lengths + clustering vs a random baseline.

    Works on the largest connected component. The headline: any two national teams are a
    handful of matches apart (short paths) yet teams cluster tightly (high clustering) --
    the signature of a small-world network.
    """
    H = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    n, m = H.number_of_nodes(), H.number_of_edges()
    avg_path = nx.average_shortest_path_length(H)
    diameter = nx.diameter(H)
    clustering = nx.average_clustering(H)
    p = 2 * m / (n * (n - 1))                       # Erdos-Renyi baseline density

    dist: dict[int, int] = {}
    for _, lengths in nx.all_pairs_shortest_path_length(H):
        for t, ln in lengths.items():
            if ln > 0:
                dist[ln] = dist.get(ln, 0) + 1
    total = sum(dist.values())
    distribution = [{"hops": k, "share": round(v / total, 4)}
                    for k, v in sorted(dist.items())]
    return {
        "n": n, "m": m,
        "avg_path": round(avg_path, 3),
        "diameter": diameter,
        "clustering": round(clustering, 3),
        "rand_avg_path": round(np.log(n) / np.log(n * p), 3),
        "rand_clustering": round(p, 3),
        "distribution": distribution,
    }


def shortest_chain(G: nx.Graph, a: str, b: str) -> list[str]:
    """The shortest chain of matches linking two nations (unweighted hops)."""
    return nx.shortest_path(G, a, b)


def centrality_table(G: nx.Graph, top_n: int = 12) -> dict:
    """Betweenness + eigenvector centrality -- who *structurally* holds the world together.

    Betweenness (with strong ties = short distances) finds the teams sitting on the most
    shortest paths between blocs: the true brokers, which are *not* the same as the teams
    that simply travel most (cross-share). Eigenvector finds the densely-embedded core.
    """
    H = G.copy()
    for _, _, dd in H.edges(data=True):
        dd["dist"] = 1.0 / dd["weight"]
    btw = nx.betweenness_centrality(H, weight="dist", normalized=True)
    eig = nx.eigenvector_centrality(H, weight="weight", max_iter=1000)
    cs = cross_share(G)
    conf = nx.get_node_attributes(G, "confederation")

    def rows(score):
        return [{"team": t, "conf": conf[t], "score": round(score[t], 4),
                 "cross": round(cs[t], 3)}
                for t in sorted(score, key=lambda n: -score[n])[:top_n]]

    btw_rank = {t: i for i, t in enumerate(sorted(btw, key=lambda n: -btw[n]))}
    cs_rank = {t: i for i, t in enumerate(sorted(cs, key=lambda n: -cs[n]))}
    common = list(btw)
    rho = float(np.corrcoef(
        [btw_rank[t] for t in common], [cs_rank[t] for t in common])[0, 1])
    return {
        "betweenness": rows(btw),
        "eigenvector": rows(eig),
        "spearman_btw_cross": round(rho, 3),
    }


def resolution_sweep(G: nx.Graph, gammas=(0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0, 5.0),
                     seed: int = 42) -> list[dict]:
    """How many communities at each resolution -- the world is structured at every scale."""
    out = []
    for g in gammas:
        c = nx.community.louvain_communities(G, weight="weight", resolution=g, seed=seed)
        out.append({"gamma": g, "n_communities": len(c)})
    return out


# Signature members that name a fine-grained sub-community when present.
_SUBREGION_SIGNATURES = [
    ("Western Europe", {"England", "Germany", "Spain", "France", "Italy"}),
    ("Eastern Europe", {"Croatia", "Serbia", "Bulgaria", "Czech Republic"}),
    ("Nordics & Central Europe", {"Sweden", "Norway", "Denmark"}),
    ("South America", {"Argentina", "Brazil", "Uruguay"}),
    ("North & Central America", {"Mexico", "United States", "Costa Rica"}),
    ("The Caribbean", {"Jamaica", "Barbados", "Bahamas"}),
    ("Asian powers & the Gulf", {"Japan", "Iran", "Australia", "Saudi Arabia"}),
    ("South & Southeast Asia", {"India", "Nepal", "Bangladesh"}),
    ("West & Central Africa", {"Nigeria", "Ghana", "Senegal"}),
    ("Southern & East Africa", {"South Africa", "Zambia", "Zimbabwe"}),
    ("Oceania", {"Fiji", "Vanuatu", "New Zealand"}),
]


def _label_subregion(members: set[str], dominant_conf: str) -> str:
    best, best_hits = None, 0
    for name, sig in _SUBREGION_SIGNATURES:
        hits = len(sig & members)
        if hits > best_hits:
            best, best_hits = name, hits
    return best if best_hits >= 2 else f"{dominant_conf} group"


def nested_partition(G: nx.Graph, gamma: float = 3.0, min_size: int = 4,
                     seed: int = 42) -> list[dict]:
    """Fine-grained sub-communities (confederation -> region), each given a readable name."""
    from collections import Counter
    comms = nx.community.louvain_communities(G, weight="weight", resolution=gamma, seed=seed)
    conf = nx.get_node_attributes(G, "confederation")
    out = []
    for com in sorted(comms, key=len, reverse=True):
        if len(com) < min_size:
            continue
        dom = Counter(conf[n] for n in com).most_common(1)[0][0]
        out.append({
            "label": _label_subregion(set(com), dom),
            "conf": dom,
            "size": len(com),
            "members": sorted(com),
        })
    return out


def _cross_efficiency(G: nx.Graph, conf: dict[str, str]) -> float:
    """Mean 1/distance over team-pairs in *different* confederations (0 if unreachable)."""
    sp = dict(nx.all_pairs_shortest_path_length(G))
    ns = list(G.nodes())
    tot = cnt = 0
    for i, u in enumerate(ns):
        for v in ns[i + 1:]:
            if conf[u] != conf[v]:
                cnt += 1
                d = sp[u].get(v)
                if d:
                    tot += 1.0 / d
    return tot / cnt if cnt else 0.0


def robustness(G: nx.Graph, kmax: int = 40, n_random: int = 8, seed: int = 1) -> dict:
    """Targeted vs random bridge removal -- how fragile is world connectivity?

    Removes teams worst-first by betweenness and tracks what's left. The honest two-sided
    finding: the brokers carry a hugely disproportionate share of cross-continental *links*
    (targeted removal strips them ~2x faster than random), yet the graph never disconnects --
    every confederation stays reachable -- so connectivity itself is robust, not fragile.
    """
    import random as _random
    conf = nx.get_node_attributes(G, "confederation")
    n = G.number_of_nodes()
    cross0 = sum(1 for u, v in G.edges() if conf[u] != conf[v])

    H = G.copy()
    for _, _, dd in H.edges(data=True):
        dd["dist"] = 1.0 / dd["weight"]
    btw = nx.betweenness_centrality(H, weight="dist", normalized=True)
    order = sorted(btw, key=lambda t: -btw[t])

    def cross_curve(remove_order):
        A = G.copy()
        frac, lcc = [], []
        for k in range(kmax + 1):
            if k > 0:
                A.remove_node(remove_order[k - 1])
            frac.append(round(sum(1 for u, v in A.edges() if conf[u] != conf[v]) / cross0, 4))
            comps = list(nx.connected_components(A))
            surviving = A.number_of_nodes()
            # largest component as a share of *surviving* teams: 1.0 == still one graph
            lcc.append(max(len(c) for c in comps) / surviving if surviving else 1.0)
        return frac, lcc

    targeted, lcc_t = cross_curve(order)
    rng = _random.Random(seed)
    rnd = np.zeros(kmax + 1)
    for _ in range(n_random):
        ro = list(G.nodes()); rng.shuffle(ro)
        rnd += np.array(cross_curve(ro)[0])
    rnd = (rnd / n_random).round(4)

    eff0 = _cross_efficiency(G, conf)
    A = G.copy()
    for t in order[:kmax]:
        A.remove_node(t)
    eff_kmax = _cross_efficiency(A, conf)

    return {
        "kmax": kmax,
        "targeted": targeted,                      # cross-edges remaining (fraction)
        "random": rnd.tolist(),
        "order": order[:12],
        "top10_link_loss": round(1 - targeted[10], 4),
        "lcc_min": round(min(lcc_t), 4),           # ~1 -> never disconnects
        "reach_retained_kmax": round(eff_kmax / eff0, 4),
    }


def adjacency_export(G: nx.Graph, min_games: int = 2) -> dict:
    """Compact adjacency for the in-browser 'connect any two nations' BFS widget."""
    conf = nx.get_node_attributes(G, "confederation")
    adj = {n: sorted(m for m in G[n] if G[n][m]["games"] >= min_games) for n in G}
    adj = {n: nbrs for n, nbrs in adj.items() if nbrs}
    return {
        "conf": {n: conf[n] for n in adj},
        "adjacency": adj,
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
