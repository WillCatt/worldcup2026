import { useEffect, useMemo, useState } from "react";
import MapView from "./MapView.jsx";

const COMPONENTS = [
  { key: "distance", label: "Distance" },
  { key: "timezone", label: "Time zones" },
  { key: "altitude", label: "Altitude" },
  { key: "recovery", label: "Recovery" },
];

// Kendall's tau between two team->rank maps (echoes the notebook's sensitivity stat).
function kendallTau(a, b) {
  const teams = Object.keys(a);
  let conc = 0, disc = 0;
  for (let i = 0; i < teams.length; i++)
    for (let j = i + 1; j < teams.length; j++) {
      const s = (a[teams[i]] - a[teams[j]]) * (b[teams[i]] - b[teams[j]]);
      if (s > 0) conc++; else if (s < 0) disc++;
    }
  return conc + disc ? (conc - disc) / (conc + disc) : 1;
}

export default function App() {
  const [data, setData] = useState(null);
  const [weights, setWeights] = useState(null);
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    fetch("./travel.json")
      .then((r) => r.json())
      .then((d) => {
        setData(d);
        setWeights({ ...d.weights });
        setSelected(d.teams[0].team); // worst-burden team under default weights
      });
  }, []);

  // default-weight ranking, fixed — the baseline the live ranking is compared against
  const defaultRank = useMemo(() => {
    if (!data) return {};
    const m = {};
    data.teams.forEach((t) => (m[t.team] = t.rank));
    return m;
  }, [data]);

  // live ranking: recompute burden = Σ wᵢ·zᵢ as the sliders move
  const ranked = useMemo(() => {
    if (!data || !weights) return [];
    const sum = Object.values(weights).reduce((a, b) => a + b, 0) || 1;
    const w = Object.fromEntries(Object.entries(weights).map(([k, v]) => [k, v / sum]));
    const rows = data.teams.map((t) => ({
      ...t,
      live: w.distance * t.z.distance + w.timezone * t.z.timezone +
            w.altitude * t.z.altitude + w.recovery * t.z.recovery,
    }));
    rows.sort((a, b) => b.live - a.live);
    rows.forEach((r, i) => (r.liveRank = i + 1));
    return rows;
  }, [data, weights]);

  const liveRankMap = useMemo(() => {
    const m = {};
    ranked.forEach((r) => (m[r.team] = r.liveRank));
    return m;
  }, [ranked]);

  const tau = useMemo(
    () => (ranked.length ? kendallTau(defaultRank, liveRankMap) : 1),
    [ranked, defaultRank, liveRankMap]
  );

  // field medians — a comparison point for the selected team's metrics
  const med = useMemo(() => {
    if (!data) return {};
    const m = (key) => {
      const s = data.teams.map((t) => t[key]).sort((a, b) => a - b);
      const mid = Math.floor(s.length / 2);
      return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
    };
    return { total_km: m("total_km"), tz_changes: m("tz_changes"),
             alt_matches: m("alt_matches"), min_rest: m("min_rest") };
  }, [data]);

  if (!data) return <div className="app"><p style={{ paddingTop: 80 }}>Loading…</p></div>;

  const sel = ranked.find((r) => r.team === selected) || ranked[0];
  const shown = query
    ? ranked.filter((r) => r.team.toLowerCase().includes(query.toLowerCase()))
    : ranked;
  const maxBurden = Math.max(...ranked.map((r) => r.live));
  const minBurden = Math.min(...ranked.map((r) => r.live));
  const isDefault = Object.entries(weights).every(([k, v]) => Math.abs(v - data.weights[k]) < 1e-9);

  return (
    <div className="app">
      <a className="back-link" href="../../index.html">← All explorations</a>

      <header className="hero">
        <p className="eyebrow">Machine Learning in Football · 03</p>
        <h1>The 2026 Travel Burden Index</h1>
        <p className="lede">Three host countries, sixteen venues, a continent of distance.
          Every team's group-stage schedule scored on how far they fly, how many time-zones
          they cross, how much altitude they breathe, and how little they rest.
          <em> Drag the weights — the ranking is yours to stress-test.</em></p>
      </header>

      {/* weight sliders → live reweighting (the sensitivity analysis, made interactive) */}
      <section className="weights">
        {COMPONENTS.map((c) => (
          <div key={c.key}>
            <div className="wlabel"><span>{c.label}</span><b>{Math.round(weights[c.key] * 100)}%</b></div>
            <input
              type="range" min="0" max="0.7" step="0.01" value={weights[c.key]}
              onChange={(e) => setWeights({ ...weights, [c.key]: parseFloat(e.target.value) })}
            />
          </div>
        ))}
        <button className="reset" onClick={() => setWeights({ ...data.weights })}>Reset</button>
        <p className={"tau-note" + (tau < 0.85 ? " shifted" : "")}>
          Rank agreement with the default weighting: <b>τ = {tau.toFixed(2)}</b>{" "}
          {isDefault
            ? "— this is the default index."
            : tau >= 0.85
              ? "— the order barely moves. The burden ranking is a property of the schedule, not the weights."
              : "— the order is shifting. You're leaning on a weak ingredient (recovery days barely vary in the group stage)."}
        </p>
      </section>

      <div className="grid">
        {/* leaderboard */}
        <section className="board">
          <div className="board-head">
            <h2>Burden leaderboard</h2><span>48 teams</span>
          </div>
          <div className="board-search">
            <input
              type="search" placeholder="Search a team…" value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="board-list">
            {shown.length === 0 && <div className="board-empty">No team matches “{query}”.</div>}
            {shown.map((r) => {
              const w = ((r.live - minBurden) / (maxBurden - minBurden || 1)) * 100;
              const shift = defaultRank[r.team] - r.liveRank; // + = moved up under current weights
              return (
                <div
                  key={r.team}
                  className={"row" + (r.team === selected ? " sel" : "")}
                  onClick={() => setSelected(r.team)}
                >
                  <span className="rk">{r.liveRank}</span>
                  <span className="nm">
                    {r.team}<small>{r.group}</small>
                    {!isDefault && shift !== 0 && (
                      <span className={"delta " + (shift > 0 ? "up" : "down")}>
                        {shift > 0 ? "▲" : "▼"}{Math.abs(shift)}
                      </span>
                    )}
                  </span>
                  <span className="bar-wrap">
                    <span className="bar" style={{ width: Math.max(4, w * 0.9) + "px" }} />
                    <span className="bval">{r.live.toFixed(2)}</span>
                  </span>
                </div>
              );
            })}
          </div>
        </section>

        {/* map + detail */}
        <section className="detail">
          <MapView venues={data.venues} team={sel} />

          <div className="summary">
            <div className="stat"><div className="n">{sel.total_km.toLocaleString()}<small> km</small></div>
              <div className="l">flown between matches</div>
              <div className="cmp">{cmp(sel.total_km, med.total_km, "km")}</div></div>
            <div className="stat"><div className="n">{sel.tz_changes}<small> hrs</small></div>
              <div className="l">time-zone shift, total</div>
              <div className="cmp">{cmp(sel.tz_changes, med.tz_changes, "hrs")}</div></div>
            <div className="stat"><div className="n">{sel.alt_matches}<small>/3</small></div>
              <div className="l">matches at altitude (≥1,500 m)</div>
              <div className="cmp">{cmp(sel.alt_matches, med.alt_matches, "")}</div></div>
            <div className="stat"><div className="n">{sel.min_rest}<small> d</small></div>
              <div className="l">shortest rest between games</div>
              <div className="cmp">{cmp(sel.min_rest, med.min_rest, "d")}</div></div>
          </div>

          <div className="timeline">
            <h3><b>{sel.team}</b> · Group {sel.group} · burden rank {sel.liveRank} of 48</h3>
            {sel.legs.map((l, i) => (
              <div className="tl-leg" key={i}>
                <div className="tl-date">{fmtDate(l.date)}</div>
                <div className="tl-body">
                  {l.leg_km > 0 && <div className="tl-hop">✈ {l.leg_km.toLocaleString()} km · {l.rest} days rest</div>}
                  <div className="tl-city">
                    {l.city}
                    {l.alt >= 1500 && <span className="alt-badge">▲ {l.alt.toLocaleString()} m</span>}
                  </div>
                  <div className="tl-meta">vs {l.opponent} · {l.country}</div>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* historical reality check */}
      <section className="history">
        <div className="hist-head">
          <h2>Does travel actually hurt?</h2>
          <p>The index measures travel; this tests whether it <em>mattered</em>. Pooled regression of
            group-stage points on pre-tournament Elo and travel, across {data.history.tournaments.join(", ")}
            {" "}({data.history.n} team campaigns).</p>
        </div>
        <div className="hist-stats">
          <div className="stat">
            <div className="n">{data.history.travel.beta.toFixed(2)}<small> pts</small></div>
            <div className="l">per +1 SD of travel, holding strength constant</div>
          </div>
          <div className="stat">
            <div className="n">p ≈ {data.history.travel.p.toFixed(2)}</div>
            <div className="l">marginal significance — real but noisy</div>
          </div>
          <div className="stat">
            <div className="n">+{data.history.elo.beta.toFixed(2)}<small> pts</small></div>
            <div className="l">per +1 SD of Elo — strength still dominates</div>
          </div>
          <div className="stat">
            <div className="n">{data.history.r2.toFixed(2)}<small> R²</small></div>
            <div className="l">variance explained by the two-factor model</div>
          </div>
        </div>
        <p className="hist-verdict">A standard deviation of extra travel cost about a third of a
          group-stage point once you control for how good a team is — <b>directionally real,
          modest, and noisy</b>. Travel is a headwind, not a death sentence — which is exactly how
          much weight this ranking deserves.</p>
      </section>

      <footer>
        Group-stage scope — all 48 teams play three matches in a fixed structure, so they're
        compared on equal footing. Burden = z-scored weighted sum of distance, time-zone change,
        altitude exposure and (inverse) rest. Built from the final-draw schedule + venue
        coordinates; analysis in <code>mlfootball/travel.py</code>. No live API.
      </footer>
    </div>
  );
}

function fmtDate(iso) {
  const [, m, d] = iso.split("-");
  return `${["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+m - 1]} ${+d}`;
}

// the selected team's value against the field median (▲ above / ▼ below / — equal)
function cmp(val, m, unit) {
  const arrow = val > m ? "▲" : val < m ? "▼" : "—";
  const u = unit ? " " + unit : "";
  return `${arrow} median ${(m ?? 0).toLocaleString()}${u}`;
}
