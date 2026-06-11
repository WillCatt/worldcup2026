import React, { useEffect, useMemo, useRef, useState } from "react";
import Scatter from "./Scatter.jsx";
import Panel from "./Panel.jsx";
import { fuzzy } from "./util.js";

const GROUPS = [
  ["FW", "Forwards"], ["MF", "Midfielders"], ["DF", "Defenders"], ["GK", "Goalkeepers"],
];

// tiny static UMAP-vs-PCA thumbnail for the methods aside
function Mini({ ex, layout }) {
  const ref = useRef(null);
  useEffect(() => {
    const cv = ref.current, W = 150, H = 120, dpr = window.devicePixelRatio || 1;
    cv.width = W * dpr; cv.height = H * dpr; cv.getContext("2d").setTransform(dpr, 0, 0, dpr, 0, 0);
    const ctx = cv.getContext("2d");
    ctx.clearRect(0, 0, W, H);
    const col = Object.fromEntries(ex.clusters.map((c) => [c.id, c.color]));
    for (const p of ex.players) {
      const [x, y] = layout === "pca" ? p.pca : p.umap;
      ctx.beginPath();
      ctx.arc(8 + (x / 100) * (W - 16), 8 + ((100 - y) / 100) * (H - 16), 2.1, 0, 6.2832);
      ctx.fillStyle = (col[p.cluster] || "#999") + "cc";
      ctx.fill();
    }
  }, [ex, layout]);
  return <canvas ref={ref} style={{ width: 150, height: 120 }} />;
}

export default function App() {
  const [data, setData] = useState(null);
  const [group, setGroup] = useState("MF");
  const [heroId, setHeroId] = useState(null);
  const [nbId, setNbId] = useState(null);
  const [minMin, setMinMin] = useState(450);
  const [query, setQuery] = useState("");
  const [hovered, setHovered] = useState(null);

  // load + hash deep-link
  useEffect(() => {
    fetch("similarity.json").then((r) => r.json()).then((d) => {
      let g = d.default_group, h = d.featured[g];
      const m = (location.hash || "").replace(/^#/, "");
      if (m.includes(":")) {
        const [gg, hh] = m.split(":");
        if (d.positions[gg] && d.positions[gg].players.some((p) => p.id === hh)) { g = gg; h = hh; }
      }
      setData(d); setGroup(g); setHeroId(h);
    });
  }, []);

  const ex = data && data.positions[group];
  const byId = useMemo(() => (ex ? Object.fromEntries(ex.players.map((p) => [p.id, p])) : {}), [ex]);
  const hero = ex && (byId[heroId] || ex.players[0]);

  // neighbours, filtered by the minutes slider
  const filteredNbrs = useMemo(() => {
    if (!hero) return [];
    return hero.neighbours.filter((n) => byId[n.id] && byId[n.id].minutes >= minMin).slice(0, 8);
  }, [hero, byId, minMin]);

  const neighbour = (nbId && byId[nbId]) || (filteredNbrs[0] && byId[filteredNbrs[0].id]) || null;
  const spokeIds = useMemo(() => {
    const s = new Set(filteredNbrs.slice(0, 5).map((n) => n.id));
    if (neighbour) s.add(neighbour.id);
    return s;
  }, [filteredNbrs, neighbour]);

  useEffect(() => {
    if (group && heroId) history.replaceState(null, "", `#${group}:${heroId}`);
  }, [group, heroId]);

  if (!data || !ex || !hero) return <div className="app"><p style={{ padding: 60 }}>Loading…</p></div>;

  const pick = (g, id) => { setGroup(g); setHeroId(id); setNbId(null); setQuery(""); };
  const results = query ? fuzzy(query, data.positions[group].players) : [];

  return (
    <div className="app">
      <a className="back-link" href="../../index.html">← All explorations</a>

      <header className="hero">
        <p className="eyebrow">World Cup 2026 · Player Similarity Engine</p>
        <h1>Who plays like whom?</h1>
        <p className="lede">
          Every World Cup player we can cover gets a per-90 statistical fingerprint, then we
          ask the only question that matters when you can't sign the original: <em>who's the
          closest match?</em> Pick a player to make them the hero — their five nearest
          stylistic neighbours light up. <em>Map position is approximate; similarity is exact.</em>
        </p>
      </header>

      <div className="tours">
        {data.tours.map((t) => (
          <button key={t.title} className="tour" onClick={() => pick(t.group, t.hero)}>
            <div className="tt">{t.title}</div>
            <div className="tb">{t.blurb}</div>
            <div className="tgo">Fly there →</div>
          </button>
        ))}
      </div>

      <div className="controls">
        <span className="ctl-label">Position</span>
        <div className="seg">
          {GROUPS.map(([g, label]) => (
            <button key={g} className={g === group ? "on" : ""}
              onClick={() => pick(g, data.featured[g])}>{label}</button>
          ))}
        </div>
        <div className="minslider">
          <span>min minutes</span>
          <input type="range" min={data.meta.embed_floor_min} max="2500" step="30"
            value={minMin} onChange={(e) => setMinMin(+e.target.value)} />
          <b>{minMin}′</b>
        </div>
        <div className="searchbox">
          <input placeholder={`Search ${ex.players.length} ${group} players…`} value={query}
            onChange={(e) => setQuery(e.target.value)} />
          {results.length > 0 && (
            <div className="suggest">
              {results.map((p) => (
                <button key={p.id} onClick={() => pick(group, p.id)}>
                  <span>{p.flag} {p.name}</span>
                  <span className="sg-meta">{p.club}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid">
        <div className="mapcard">
          <Scatter ex={ex} heroId={hero.id} neighbourIds={spokeIds} minMinutes={minMin}
            layout="umap" onSelect={(id) => { setHeroId(id); setNbId(null); }} onHover={setHovered} />
          <div className="map-caption">
            <span className="cap">
              A UMAP projection — drag to pan, scroll to zoom. The axes carry no units or
              direction; only who-sits-near-whom is meaningful.
            </span>
            <div className="legend">
              {ex.clusters.map((c) => (
                <span className="lk" key={c.id}><span className="dot" style={{ background: c.color }} />{c.label}</span>
              ))}
            </div>
          </div>
        </div>

        <Panel ex={ex} hero={hero} neighbour={neighbour} neighbours={filteredNbrs}
          byId={byId} onPick={(id) => setNbId(id)} />
      </div>

      <details className="aside">
        <summary>How this was built — and what per-90 hides <span className="chev">▶</span></summary>
        <div className="body">
          <div className="coverage">
            <div className="cstat"><b>{data.meta.coverage_pct}%</b><span>squad coverage</span></div>
            <div className="cstat"><b>{data.meta.n_matched}</b><span>players mapped</span></div>
            <div className="cstat"><b>{data.meta.n_flagged}</b><span>flagged, not plotted</span></div>
            <div className="cstat"><b>{data.meta.season}</b><span>FBref season</span></div>
          </div>
          <p style={{ marginTop: 14 }}>{data.meta.coverage_note}</p>
          <p>
            <b>Similarity is computed in the original space, not on the map.</b> We z-score
            ~{ex.features.length} per-90 features <em>within</em> each position group, then score
            every pair by <code>cosine similarity</code> on those standardised vectors. UMAP only
            arranges the dots for navigation — it's a non-linear projection whose distances are
            distorted by design. To see why we don't read similarity off the picture, compare the
            UMAP layout with a linear PCA one of the same players:
          </p>
          <div className="pcarow">
            <div className="pcathumb"><Mini ex={ex} layout="umap" /><div className="pl">UMAP (shown)</div></div>
            <div className="pcathumb"><Mini ex={ex} layout="pca" /><div className="pl">PCA (linear)</div></div>
          </div>
          <p>
            <b>What per-90 normalisation hides:</b> these are <em>{data.meta.season} club</em> rates,
            not international form, and a player below the {data.meta.embed_floor_min}-minute floor is
            a small, noisy sample (shown as a faint outline; the slider hides them from neighbour
            lists). Rates also flatter cameo players and ignore league strength — a 90th-percentile
            tackler in Ligue 1 isn't identical to one in the Premier League. Archetype labels are
            assigned by scoring each k-means cluster centroid against a small signature library.
          </p>
          <p>
            Source: <code>{data.meta.source}</code>. Full pipeline in
            <code> mlfootball/similarity.py</code> + <code>notebooks/04_similarity.py</code>.
          </p>
        </div>
      </details>

      <footer>
        <p>
          Per-90 data: FBref ({data.meta.season}, Big-5 leagues) via <a href="https://github.com/JaseZiv/worldfootballR_data">worldfootballR_data</a>.
          Squads: Wikipedia 2026 World Cup tables. Similarity = cosine in standardised per-90 space; layout = UMAP.
          Part of <a href="../../index.html">The football world, explored</a>.
        </p>
      </footer>
    </div>
  );
}
