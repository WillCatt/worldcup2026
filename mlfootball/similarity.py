"""Player Similarity Engine: who plays like whom at the 2026 World Cup.

For every World Cup squad player we can cover, this builds a per-90 statistical
fingerprint from FBref, then asks a simple question: *who else plays like this?*

The honest-engineering decisions are the point of the piece:

1. **Coverage gap, surfaced not hidden.** Our only free, reproducible feature
   source is FBref's Big-5 European leagues (Premier League, La Liga, Serie A,
   Bundesliga, Ligue 1), mirrored season-by-season by `worldfootballR_data`.
   The most recent season complete across *all* stat tables (incl. the
   defensive/possession ones the archetypes need) is **2024-25**. A WC player who
   played 2024-25 outside the Big-5 (Saudi Pro League, MLS, Liga MX, Eredivisie,
   the Championship, Liga Portugal, …) simply has no vector — they are *flagged*,
   never silently dropped.

2. **Positions first.** Keepers, defenders, midfielders and forwards live in
   separate embedding spaces. A goalkeeper must never sit next to a winger.

3. **The map is for navigation; the maths lives in full dimensionality.** We
   z-score features *within* each position group, run UMAP to 2D purely for
   layout, but compute every similarity score as **cosine similarity in the
   original standardised feature space** — not distance on the 2D map.

Source: `worldfootballR_data` release `fb_big5_advanced_season_stats`
(FBref via Sports Reference), cached locally under data/fbref_cache/*.rds.
Squad list: the parsed Wikipedia 2026 WC squad tables (see squads.py).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from mlfootball import squads

CACHE = Path(__file__).resolve().parent.parent / "data" / "fbref_cache"

SEASON = 2025                 # Season_End_Year -> the 2024-25 campaign
SEASON_LABEL = "2024-25"
BIG5 = ["Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1"]

EMBED_FLOOR = 270            # min minutes to enter the embedding/neighbour pool (3 full matches)
DEFAULT_MIN = 450            # front-end minutes-slider default

POS_ORDER = ["GK", "DF", "MF", "FW"]


# ── load & merge the Big-5 stat tables ────────────────────────────────────────
def _load(name: str) -> pd.DataFrame:
    df = pd.read_pickle(CACHE / f"_{name}.pkl") if (CACHE / f"_{name}.pkl").exists() else None
    if df is None:
        import pyreadr
        df = pyreadr.read_r(str(CACHE / f"big5_player_{name}.rds"))[None]
        df.to_pickle(CACHE / f"_{name}.pkl")  # speeds up re-runs
    df = df[df["Season_End_Year"] == SEASON].copy()
    return df


def _dedupe(df: pd.DataFrame, min_col: str) -> pd.DataFrame:
    """A player transferred mid-season has two rows; keep the one with more
    minutes (their primary club for the campaign)."""
    return df.sort_values(min_col, ascending=False).drop_duplicates("Player")


def build_feature_frame() -> pd.DataFrame:
    """One row per Big-5 2024-25 player, carrying meta + raw per-90 features."""
    std = _dedupe(_load("standard"), "Min_Playing")
    sho = _dedupe(_load("shooting"), "Mins_Per_90")
    pas = _dedupe(_load("passing"), "Mins_Per_90")
    pos = _dedupe(_load("possession"), "Mins_Per_90")
    dfn = _dedupe(_load("defense"), "Mins_Per_90")
    msc = _dedupe(_load("misc"), "Mins_Per_90")

    base = std[["Player", "Squad", "Comp", "Nation", "Pos", "Age", "Min_Playing",
                "Gls", "Ast", "npxG_Expected", "xAG_Expected",
                "PrgC_Progression", "PrgP_Progression", "PrgR_Progression"]].copy()
    base = base.rename(columns={"Min_Playing": "Min"})
    base["nineties"] = base["Min"] / 90.0
    base = base[base["nineties"] > 0]

    def col(df, name, key):
        return df.set_index("Player")[name].reindex(base["Player"]).to_numpy() if key else None

    P = base.set_index("Player")
    def g(df, name):
        return df.set_index("Player")[name].reindex(base["Player"]).to_numpy(dtype=float)

    n90 = base["nineties"].to_numpy(dtype=float)

    # raw per-90 features (counting stats / 90s played); rates kept as-is
    feat = pd.DataFrame({"Player": base["Player"].to_numpy()})
    feat["npxg90"]   = base["npxG_Expected"].to_numpy(float) / n90
    feat["xag90"]    = base["xAG_Expected"].to_numpy(float) / n90
    feat["sh90"]     = g(sho, "Sh_Standard") / n90
    feat["sot90"]    = g(sho, "SoT_Standard") / n90
    feat["shotdist"] = g(sho, "Dist_Standard")
    feat["touches90"] = g(pos, "Touches_Touches") / n90
    feat["attpen_touch90"] = g(pos, "Att Pen_Touches") / n90
    feat["carries90"] = g(pos, "Carries_Carries") / n90
    feat["prgc90"]   = g(pos, "PrgC_Carries") / n90
    feat["takeon90"] = g(pos, "Att_Take") / n90
    feat["takeon_pct"] = g(pos, "Succ_percent_Take")
    feat["prgr90"]   = g(pos, "PrgR_Receiving") / n90
    touches = g(pos, "Touches_Touches")
    feat["def3rd_share"] = np.where(touches > 0, g(pos, "Def 3rd_Touches") / touches, np.nan) * 100
    feat["att3rd_share"] = np.where(touches > 0, g(pos, "Att 3rd_Touches") / touches, np.nan) * 100
    feat["passatt90"] = g(pas, "Att_Total") / n90
    feat["pass_pct"]  = g(pas, "Cmp_percent_Total")
    att_total = g(pas, "Att_Total")
    feat["long_pct"]  = np.where(att_total > 0, g(pas, "Att_Long") / att_total, np.nan) * 100
    feat["prgp90"]    = g(pas, "PrgP") / n90
    feat["kp90"]      = g(pas, "KP") / n90
    feat["ppa90"]     = g(pas, "PPA") / n90
    feat["xa90"]      = g(pas, "xA_Expected") / n90
    feat["tkl90"]     = g(dfn, "Tkl_Tackles") / n90
    feat["int90"]     = g(dfn, "Int") / n90
    feat["tklint90"]  = g(dfn, "Tkl+Int") / n90
    feat["blocks90"]  = g(dfn, "Blocks_Blocks") / n90
    feat["clr90"]     = g(dfn, "Clr") / n90
    feat["aerial90"]  = g(msc, "Won_Aerial") / n90
    feat["aerial_pct"] = g(msc, "Won_percent_Aerial")
    feat["recov90"]   = g(msc, "Recov") / n90

    out = base[["Player", "Squad", "Comp", "Nation", "Pos", "Age", "Min", "nineties"]].merge(
        feat, on="Player", how="left")
    out["pos_group"] = out["Pos"].str.split(",").str[0].str.strip()
    return out


# ── feature sets per position group ───────────────────────────────────────────
# Same broad set standardises *within* a group so sub-archetypes separate; the
# radar uses a curated 8 (percentile-scaled) for legibility.
OUTFIELD_FEATURES = [
    "npxg90", "xag90", "sh90", "sot90", "attpen_touch90", "touches90", "carries90",
    "prgc90", "takeon90", "takeon_pct", "prgr90", "def3rd_share", "att3rd_share",
    "passatt90", "pass_pct", "long_pct", "prgp90", "kp90", "ppa90", "xa90",
    "tkl90", "int90", "tklint90", "blocks90", "clr90", "aerial90", "aerial_pct", "recov90",
]
GK_FEATURES = ["save_pct", "ga90", "saves90", "cs_pct", "passatt90", "long_pct"]

RADAR = {
    "FW": ["npxg90", "sh90", "xa90", "attpen_touch90", "takeon90", "prgr90", "aerial_pct", "carries90"],
    "MF": ["prgp90", "pass_pct", "kp90", "xa90", "tkl90", "int90", "prgc90", "touches90"],
    "DF": ["tkl90", "int90", "clr90", "blocks90", "aerial_pct", "prgp90", "pass_pct", "prgc90"],
    "GK": ["save_pct", "ga90", "saves90", "cs_pct", "passatt90", "long_pct"],
}

FEATURE_LABELS = {
    "npxg90": "Non-penalty xG", "xag90": "Expected assists (xAG)", "sh90": "Shots",
    "sot90": "Shots on target", "shotdist": "Avg shot distance", "attpen_touch90": "Touches in box",
    "touches90": "Touches", "carries90": "Carries", "prgc90": "Progressive carries",
    "takeon90": "Take-ons attempted", "takeon_pct": "Take-on success %", "prgr90": "Progressive passes received",
    "def3rd_share": "Touch share: def third", "att3rd_share": "Touch share: att third",
    "passatt90": "Passes attempted", "pass_pct": "Pass completion %", "long_pct": "Long-pass share",
    "prgp90": "Progressive passes", "kp90": "Key passes", "ppa90": "Passes into box",
    "xa90": "Expected assists (xA)", "tkl90": "Tackles", "int90": "Interceptions",
    "tklint90": "Tackles + interceptions", "blocks90": "Blocks", "clr90": "Clearances",
    "aerial90": "Aerials won", "aerial_pct": "Aerial win %", "recov90": "Ball recoveries",
    "save_pct": "Save %", "ga90": "Goals against /90", "saves90": "Saves",
    "cs_pct": "Clean-sheet %", "launch_pct": "Launch %",
}


# ── name join: WC squad -> FBref row ──────────────────────────────────────────
def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def join_squads(feat: pd.DataFrame, players: list[dict] | None = None):
    """Match each WC squad player to a Big-5 2024-25 FBref row by folded name
    (exact, then token-set, then last-name+initial). Returns (matched_df, flagged)."""
    feat = feat.copy()
    feat["fold"] = feat["Player"].map(_fold)
    by_full: dict[str, int] = {}
    by_last: dict[str, list[int]] = {}
    for i, f in zip(feat.index, feat["fold"]):
        by_full.setdefault(f, i)
        toks = f.split()
        if toks:
            by_last.setdefault(toks[-1], []).append(i)

    players = players if players is not None else squads.load_players()
    rows, flagged = [], []
    used = set()
    for p in players:
        f = _fold(p["name"])
        toks = f.split()
        idx = None
        if f in by_full:
            idx = by_full[f]
        else:
            # token-set: WC name tokens are a subset/superset of an FBref name
            cands = set()
            for t in toks:
                for j in by_last.get(t, []):
                    cands.add(j)
            # match last token + first initial, unique
            lc = [j for j in by_last.get(toks[-1], []) if toks and feat.at[j, "fold"].split()[0][:1] == toks[0][:1]] if toks else []
            if len(set(lc)) == 1:
                idx = lc[0]
            else:
                # full token-subset either direction, unique
                sub = [j for j in cands
                       if set(toks) <= set(feat.at[j, "fold"].split()) or set(feat.at[j, "fold"].split()) <= set(toks)]
                if len(set(sub)) == 1:
                    idx = sub[0]
        code = squads.NATION_CODE.get(p["nation"], "")
        if idx is None:
            flagged.append({"name": p["name"], "nation": p["nation"], "flag": squads.flag(code),
                            "pos": p["pos"], "posGroup3": _grp(p["pos"]), "club": p["club"],
                            "league": squads.league(p["code"]), "reason": "outside Big-5 in 2024-25"})
            continue
        r = feat.loc[idx]
        rows.append({**{k: r[k] for k in feat.columns if k != "fold"},
                     "wc_name": p["name"], "nation": p["nation"], "nat_flag": squads.flag(code),
                     "wc_pos": p["pos"], "caps": p["caps"]})
        used.add(idx)
    matched = pd.DataFrame(rows)
    return matched, flagged


def _grp(pos: str) -> str:
    p = pos.split(",")[0].strip()
    return p if p in POS_ORDER else "MF"


# ── goalkeeper feature frame (separate tables) ────────────────────────────────
def build_gk_frame() -> pd.DataFrame:
    kp = _dedupe(_load("keepers"), "Min_Playing")
    pas = _dedupe(_load("passing"), "Mins_Per_90")
    base = kp[["Player", "Squad", "Comp", "Nation", "Pos", "Age", "Min_Playing",
               "GA90", "Save_percent", "Saves", "CS_percent"]].copy()
    base = base.rename(columns={"Min_Playing": "Min"})
    base["nineties"] = base["Min"] / 90.0
    base = base[base["nineties"] > 0]
    n90 = base["nineties"].to_numpy(float)
    pmap = pas.set_index("Player")
    att = pmap["Att_Total"].reindex(base["Player"]).to_numpy(float)
    lng = pmap["Att_Long"].reindex(base["Player"]).to_numpy(float)
    base["save_pct"] = base["Save_percent"].to_numpy(float)
    base["ga90"] = base["GA90"].to_numpy(float)
    base["saves90"] = base["Saves"].to_numpy(float) / n90
    base["cs_pct"] = base["CS_percent"].to_numpy(float)
    base["passatt90"] = att / n90
    base["long_pct"] = np.where(att > 0, lng / att, np.nan) * 100
    base["launch_pct"] = base["long_pct"]   # proxy: share of long passes
    base["pos_group"] = "GK"
    return base


# ── archetype signatures (auto-labelled from cluster centroids in z-space) ─────
# Each signature is the handful of features that define the archetype; we score a
# cluster centroid (in standardised space) against every signature and assign the
# best, greedily, so labels stay unique within a position group.
SIGNATURES = {
    "FW": {
        "Box poachers": {"npxg90": 2, "attpen_touch90": 2, "sot90": 1, "takeon90": -1, "passatt90": -1},
        "Wide dribblers": {"takeon90": 2, "prgc90": 2, "prgr90": 1, "xa90": 1, "aerial_pct": -1},
        "Creative forwards": {"xa90": 2, "kp90": 2, "ppa90": 1, "passatt90": 1, "touches90": 1},
        "Target men": {"aerial90": 2, "aerial_pct": 2, "takeon90": -1, "prgc90": -1},
        "Pressing forwards": {"recov90": 2, "tkl90": 1, "def3rd_share": 1, "npxg90": -1},
    },
    "MF": {
        "Deep-lying progressors": {"prgp90": 2, "passatt90": 2, "pass_pct": 1, "long_pct": 1, "attpen_touch90": -1},
        "Ball-winners": {"tkl90": 2, "int90": 2, "tklint90": 2, "recov90": 1, "xa90": -1},
        "Box-to-box engines": {"carries90": 2, "prgc90": 1, "tkl90": 1, "npxg90": 1, "recov90": 1},
        "Advanced creators": {"kp90": 2, "xa90": 2, "ppa90": 2, "attpen_touch90": 1},
        "Wide midfielders": {"takeon90": 2, "prgr90": 2, "att3rd_share": 1, "kp90": 1},
    },
    "DF": {
        "Ball-playing CBs": {"prgp90": 2, "passatt90": 2, "pass_pct": 2, "prgc90": 1, "att3rd_share": -1},
        "Stoppers": {"clr90": 2, "aerial90": 2, "aerial_pct": 2, "blocks90": 1, "prgp90": -1},
        "Overlapping full-backs": {"prgc90": 2, "takeon90": 2, "prgr90": 2, "att3rd_share": 2, "kp90": 1},
        "Defensive full-backs": {"tkl90": 2, "int90": 2, "blocks90": 1, "att3rd_share": -1, "kp90": -1},
    },
    "GK": {
        "Shot-stoppers": {"save_pct": 2, "saves90": 2, "passatt90": -1},
        "Sweeper-keepers": {"passatt90": 2, "long_pct": -2, "save_pct": -1},
    },
}
N_CLUSTERS = {"FW": 5, "MF": 5, "DF": 4, "GK": 2}

# muted, archetype-tinted palette on an off-white ground (one saturated accent is
# reserved by the front end for the selection state)
CLUSTER_COLORS = ["#7C9CB0", "#C18A5E", "#8FA88B", "#B07C9E", "#A89A6B", "#6E8E8E"]


def _label_clusters(centroids_z: np.ndarray, features: list[str], group: str):
    sigs = SIGNATURES[group]
    fidx = {f: i for i, f in enumerate(features)}
    score = {}  # (cluster, signame) -> dot
    for c in range(len(centroids_z)):
        for name, sig in sigs.items():
            score[(c, name)] = sum(w * centroids_z[c, fidx[f]] for f, w in sig.items() if f in fidx)
    # greedy unique assignment, best dot first
    assigned, used_names, used_c = {}, set(), set()
    for (c, name), v in sorted(score.items(), key=lambda kv: -kv[1]):
        if c in used_c or name in used_names:
            continue
        assigned[c] = name
        used_c.add(c); used_names.add(name)
    # any cluster left (more clusters than signatures) -> best remaining sig name
    for c in range(len(centroids_z)):
        if c not in assigned:
            best = max(sigs, key=lambda n: score[(c, n)])
            assigned[c] = best
    return assigned


def _blurb(centroid_z, features):
    order = np.argsort(centroid_z)
    hi = [FEATURE_LABELS[features[i]] for i in order[::-1][:2]]
    lo = [FEATURE_LABELS[features[i]] for i in order[:1]]
    return f"High {hi[0].lower()} & {hi[1].lower()}; low {lo[0].lower()}."


def _slugs(names, codes):
    out, seen = [], {}
    for nm, cd in zip(names, codes):
        s = re.sub(r"-+", "-", _fold(nm).replace(" ", "-")) + "-" + (cd or "x").lower()
        if s in seen:
            seen[s] += 1; s = f"{s}-{seen[s]}"
        else:
            seen[s] = 0
        out.append(s)
    return out


def embed_group(df: pd.DataFrame, features: list[str], group: str) -> dict:
    """Standardise within group, UMAP to 2D for layout, cosine-similarity in the
    standardised space for neighbours, KMeans + archetype labels, percentiles."""
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
    from sklearn.metrics.pairwise import cosine_similarity
    import umap

    df = df[df["Min"] >= EMBED_FLOOR].copy().reset_index(drop=True)
    X = df[features].to_numpy(dtype=float, copy=True)
    # impute remaining NaN with column median (rate stats undefined for 0-denominator)
    med = np.nanmedian(X, axis=0)
    inds = np.where(np.isnan(X))
    X[inds] = np.take(med, inds[1])

    scaler = StandardScaler()
    Z = scaler.fit_transform(X)

    from sklearn.decomposition import PCA

    def _box(c):  # normalise a 2D layout to a tidy [0,100] box (axes are meaningless)
        c = c - c.min(0)
        return 100 * c / np.maximum(c.max(0), 1e-9)

    coords = _box(umap.UMAP(n_neighbors=min(15, len(df) - 1), min_dist=0.25,
                            metric="euclidean", random_state=42).fit_transform(Z))
    # PCA layout too — the methods aside contrasts it with UMAP (linear vs manifold)
    pca = _box(PCA(n_components=2, random_state=42).fit_transform(Z))

    sim = cosine_similarity(Z)
    np.fill_diagonal(sim, -1)

    k = min(N_CLUSTERS[group], max(2, len(df) // 6))
    km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(Z)
    labels_idx = km.labels_
    arche = _label_clusters(km.cluster_centers_, features, group)
    if group == "GK":
        # robust 2-way GK label: the keeper who passes more & launches less builds
        # play from the back (sweeper-keeper); the other is a traditional shot-stopper
        pj, lj = features.index("passatt90"), features.index("long_pct")
        sweep = np.argmax(km.cluster_centers_[:, pj] - km.cluster_centers_[:, lj])
        arche = {c: ("Sweeper-keepers" if c == sweep else "Shot-stoppers") for c in range(k)}

    # percentiles within group for every feature (0-100)
    pct = {f: (pd.Series(X[:, j]).rank(pct=True) * 100).round().astype(int).to_numpy()
           for j, f in enumerate(features)}

    slugs = _slugs(df["wc_name"], [squads.NATION_CODE.get(n, "") for n in df["nation"]])

    players = []
    for i in range(len(df)):
        order = np.argsort(sim[i])[::-1][:10]
        neighbours = [{"id": slugs[j], "score": round(float(sim[i, j]) * 100, 1)} for j in order]
        players.append({
            "id": slugs[i], "name": df.at[i, "wc_name"], "nation": df.at[i, "nation"],
            "flag": df.at[i, "nat_flag"], "club": df.at[i, "Squad"], "comp": df.at[i, "Comp"],
            "pos": df.at[i, "wc_pos"], "posGroup": group, "age": _age(df.at[i, "Age"]),
            "minutes": int(df.at[i, "Min"]), "caps": int(df.at[i, "caps"]),
            "umap": [round(float(coords[i, 0]), 2), round(float(coords[i, 1]), 2)],
            "pca": [round(float(pca[i, 0]), 2), round(float(pca[i, 1]), 2)],
            "cluster": int(labels_idx[i]),
            "pct": {f: int(pct[f][i]) for f in features},
            "raw": {f: round(float(X[i, j]), 2) for j, f in enumerate(features)},
            "neighbours": neighbours,
        })

    # convex hulls per cluster for the archetype landscape annotation
    from scipy.spatial import ConvexHull
    clusters = []
    for c in range(k):
        mask = labels_idx == c
        pts = coords[mask]
        hull = []
        if mask.sum() >= 3:
            try:
                h = ConvexHull(pts)
                hull = [[round(float(pts[v, 0]), 2), round(float(pts[v, 1]), 2)] for v in h.vertices]
            except Exception:
                hull = []
        clusters.append({
            "id": c, "label": arche[c], "color": CLUSTER_COLORS[c % len(CLUSTER_COLORS)],
            "n": int(mask.sum()), "blurb": _blurb(km.cluster_centers_[c], features),
            "centroid": [round(float(coords[mask, 0].mean()), 2), round(float(coords[mask, 1].mean()), 2)],
            "hull": hull,
        })

    return {
        "features": [{"key": f, "label": FEATURE_LABELS[f]} for f in features],
        "radar": RADAR[group],
        "clusters": clusters,
        "players": players,
    }


def _age(a):
    try:
        return int(float(a))
    except Exception:
        return None


# ── default heroes + editorial tours (resolved against who actually matched) ───
# Each group opens on a recognisable star with interesting neighbours so the page
# is never a blank dot cloud. Tours are curated comparisons that fly to a hero.
PREFERRED = {
    "MF": ["Rodri", "Jude Bellingham", "Pedri", "Declan Rice", "Vitinha", "Florian Wirtz"],
    "FW": ["Erling Haaland", "Kylian Mbappé", "Lautaro Martínez", "Ousmane Dembélé", "Harry Kane"],
    "DF": ["Virgil van Dijk", "William Saliba", "Achraf Hakimi", "Alessandro Bastoni", "Antonio Rüdiger"],
    "GK": ["Gianluigi Donnarumma", "Thibaut Courtois", "Unai Simón", "Jan Oblak"],
}


def _find_id(group_export, *names):
    by_fold = {_fold(p["name"]): p for p in group_export["players"]}
    for n in names:                       # honour preference order
        p = by_fold.get(_fold(n))
        if p:
            return p["id"], p["name"]
    return None, None


def _best_in_cluster(group_export, label, prefer=()):
    """A recognisable (or, failing that, highest-minutes) player in the named
    archetype cluster — guarantees the tour's hero actually fits its blurb."""
    cid = next((c["id"] for c in group_export["clusters"] if c["label"] == label), None)
    pool = [p for p in group_export["players"] if p["cluster"] == cid]
    if not pool:
        return None, None
    pref = {_fold(n) for n in prefer}
    starred = [p for p in pool if _fold(p["name"]) in pref]
    p = max(starred or pool, key=lambda x: x["minutes"])
    return p["id"], p["name"]


def build_tours(positions: dict) -> list[dict]:
    tours = []
    mid, mname = _best_in_cluster(positions["MF"], "Deep-lying progressors", prefer=PREFERRED["MF"])
    if mid:
        tours.append({"title": "Deep-lying engines", "group": "MF", "hero": mid,
                      "blurb": f"The metronomes who set the tempo from the base of midfield — like {mname}."})
    pid, pname = _best_in_cluster(positions["FW"], "Pressing forwards", prefer=PREFERRED["FW"])
    if pid:
        tours.append({"title": "Strikers who press like midfielders", "group": "FW", "hero": pid,
                      "blurb": f"Forwards whose first job is winning the ball back. Meet {pname}."})
    bid, bname = _best_in_cluster(positions["DF"], "Ball-playing CBs", prefer=PREFERRED["DF"])
    if bid:
        tours.append({"title": "Centre-backs who start the attack", "group": "DF", "hero": bid,
                      "blurb": f"Defenders graded on progression, not just clearances — like {bname}."})
    return tours


def featured_ids(positions: dict) -> dict:
    out = {}
    for grp, ex in positions.items():
        fid, _ = _find_id(ex, *PREFERRED.get(grp, []))
        if not fid and ex["players"]:
            fid = max(ex["players"], key=lambda p: p["minutes"])["id"]
        out[grp] = fid
    return out


# ── full export ───────────────────────────────────────────────────────────────
def build_export() -> dict:
    feat = build_feature_frame()
    allp = squads.load_players()
    out_players = [p for p in allp if _grp(p["pos"]) != "GK"]
    gk_players = [p for p in allp if _grp(p["pos"]) == "GK"]

    matched_out, flagged_out = join_squads(feat, out_players)
    gkf = build_gk_frame()
    matched_gk, flagged_gk = join_squads(gkf, gk_players)

    positions = {}
    for grp in ["FW", "MF", "DF"]:
        sub = matched_out[matched_out["pos_group"] == grp].reset_index(drop=True)
        positions[grp] = embed_group(sub, OUTFIELD_FEATURES, grp)
    positions["GK"] = embed_group(matched_gk, GK_FEATURES, "GK")

    n_matched = sum(len(positions[g]["players"]) for g in positions)
    flagged = flagged_out + flagged_gk
    # a few low-minute matched players were dropped at the embedding floor; count them honestly
    n_below_floor = (len(matched_out) + len(matched_gk)) - n_matched

    meta = {
        "season": SEASON_LABEL,
        "source": "FBref (Big-5 European leagues) via worldfootballR_data",
        "leagues": BIG5,
        "n_squad_players": len(allp),
        "n_matched": n_matched,
        "n_flagged": len(flagged),
        "n_below_floor": int(n_below_floor),
        "coverage_pct": round(100 * n_matched / len(allp), 1),
        "embed_floor_min": EMBED_FLOOR,
        "default_min": DEFAULT_MIN,
        "feature_note": ("Map position is approximate (UMAP, for navigation only); "
                         "similarity is exact — cosine similarity in the standardised "
                         "per-90 feature space. Axes carry no units."),
        "coverage_note": (f"Per-90 stats are {SEASON_LABEL} club form in the Big-5 leagues. "
                          "World Cup players who played that season elsewhere "
                          "(Saudi Pro League, MLS, Liga MX, Eredivisie, the Championship, …) "
                          "have no vector and are flagged below, not plotted."),
    }
    return {
        "meta": meta,
        "featured": featured_ids(positions),
        "default_group": "MF",
        "tours": build_tours(positions),
        "positions": positions,
        "flagged": sorted(flagged, key=lambda f: (f["nation"], f["name"])),
    }


def write_export(path: Path | None = None) -> dict:
    import json
    data = build_export()
    path = path or (Path(__file__).resolve().parent.parent / "site" / "data" / "similarity.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    return data
