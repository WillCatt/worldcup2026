/**
 * NationSankey — a nation-first, editorial squad-composition interactive.
 *
 * One featured nation at a time. The page adopts the nation's identity (flag,
 * federation colours, huge serif headline, an auto-written verdict). The hero is
 * a squad → position → league Sankey: four position lanes on the left flow into
 * destination leagues on the right, the domestic league rendered in the nation's
 * own colour so "plays at home" vs "plays abroad" reads in one glance.
 *
 * Self-contained: fetches ./nations.json, injects its own styles, no external CSS.
 * Data shape per nation: { nation, code, flag, colors{primary,secondary},
 *   n_players, domestic, domestic_pct, n_leagues, domestic_rank,
 *   players[ {name,pos,posGroup,club,league,code,country,flag,caps,goals,domestic} ] }
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { sankey as d3sankey } from "d3-sankey";

// ── palette / type ────────────────────────────────────────────────────────────
const OFFWHITE = "#FAF8F4";
const PAPER = "#F3F0E9";
const INK = "#1B1B1F";
const MUTE = "#6B665E";
const HAIR = "#DED9CF";
const NEUTRAL = "#B7B0A4";          // the "abroad" gradient end — a warm grey
const POS_ORDER = ["Goalkeepers", "Defenders", "Midfielders", "Forwards"];

// svg geometry
const W = 980, H = 488;
const EXT = [[166, 18], [W - 322, H - 18]];   // inset leaves room for labels both sides
const NODE_W = 13, NODE_PAD = 20, DUR = 520;

// ── small utilities ───────────────────────────────────────────────────────────
const ord = (n) => {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const lerp = (a, b, t) => a + (b - a) * t;

function useReducedMotion() {
  const [r, setR] = useState(false);
  useEffect(() => {
    const m = window.matchMedia("(prefers-reduced-motion: reduce)");
    const f = () => setR(m.matches);
    f(); m.addEventListener?.("change", f);
    return () => m.removeEventListener?.("change", f);
  }, []);
  return r;
}

// count-up for the big stat numbers
function useCountUp(value, enabled) {
  const [v, setV] = useState(value);
  const ref = useRef(value);
  useEffect(() => {
    if (!enabled) { ref.current = value; setV(value); return; }
    const from = ref.current, to = value, t0 = performance.now(), d = 420;
    let raf;
    const tick = (now) => {
      const p = Math.min(1, (now - t0) / d);
      const cur = lerp(from, to, ease(p));
      setV(cur);
      if (p < 1) raf = requestAnimationFrame(tick);
      else ref.current = to;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, enabled]);
  return v;
}

// ── build the squad → position → league graph for one nation ──────────────────
function buildGraph(nation) {
  const players = nation.players;
  const homeLeague = players.find((p) => p.domestic)?.league;

  // positions present, in canonical order
  const posPresent = POS_ORDER.filter((g) => players.some((p) => p.posGroup === g));

  // aggregate leagues; fold non-domestic singletons into "Other leagues"
  const byLeague = new Map();
  for (const p of players) {
    const m = byLeague.get(p.league) || {
      league: p.league, code: p.code, country: p.country, flag: p.flag,
      domestic: p.domestic, count: 0, players: [], clubs: new Map(),
    };
    m.count++; m.players.push(p);
    m.clubs.set(p.club, (m.clubs.get(p.club) || 0) + 1);
    byLeague.set(p.league, m);
  }
  const kept = [], otherPlayers = [];
  for (const m of byLeague.values()) {
    if (m.domestic || m.count >= 2) kept.push(m);
    else otherPlayers.push(...m.players);
  }
  kept.sort((a, b) => (b.domestic - a.domestic) || (b.count - a.count));
  if (otherPlayers.length) {
    const clubs = new Map();
    for (const p of otherPlayers) clubs.set(`${p.club} · ${p.country}`, (clubs.get(`${p.club} · ${p.country}`) || 0) + 1);
    kept.push({
      league: "Other leagues", code: "", country: "", flag: "🌍", domestic: false,
      count: otherPlayers.length, players: otherPlayers, clubs, isOther: true,
    });
  }
  // ensure the domestic league sits first even if not the largest
  kept.sort((a, b) => (b.domestic - a.domestic) || ((a.isOther ? 1 : 0) - (b.isOther ? 1 : 0)) || (b.count - a.count));

  const posNodes = posPresent.map((g) => ({
    id: "P:" + g, kind: "pos", name: g,
    count: players.filter((p) => p.posGroup === g).length,
  }));
  const leagueNodes = kept.map((m) => ({
    id: "L:" + m.league, kind: "league", name: m.league, count: m.count,
    flag: m.flag, country: m.country, domestic: m.domestic, isOther: m.isOther,
    players: m.players,
    clubs: [...m.clubs.entries()].map(([club, n]) => ({ club, n })).sort((a, b) => b.n - a.n),
  }));

  // links position → league
  const links = [];
  for (const g of posPresent) {
    for (const m of kept) {
      const ps = m.players.filter((p) => p.posGroup === g);
      if (ps.length) links.push({
        id: `${g}→${m.league}`, source: "P:" + g, target: "L:" + m.league,
        value: ps.length, domestic: m.domestic, players: ps,
        league: m.league, flag: m.flag,
      });
    }
  }
  return { nodes: [...posNodes, ...leagueNodes], links, homeLeague };
}

// run d3-sankey → a snapshot keyed by node/link id (geometry + meta)
function snapshot(nation) {
  const g = buildGraph(nation);
  const sk = d3sankey().nodeId((d) => d.id).nodeWidth(NODE_W).nodePadding(NODE_PAD)
    .nodeSort(null).linkSort(null).extent(EXT);
  const lay = sk({ nodes: g.nodes.map((d) => ({ ...d })), links: g.links.map((d) => ({ ...d })) });

  const nodes = new Map();
  for (const n of lay.nodes) nodes.set(n.id, {
    id: n.id, kind: n.kind, name: n.name, count: n.count, flag: n.flag,
    country: n.country, domestic: n.domestic, isOther: n.isOther,
    players: n.players, clubs: n.clubs,
    rect: [n.x0, n.y0, n.x1, n.y1],
  });
  const links = new Map();
  for (const l of lay.links) {
    const sx = l.source.x1, tx = l.target.x0, mx = (sx + tx) / 2;
    links.set(l.id, {
      id: l.id, value: l.value, domestic: l.domestic, players: l.players,
      league: l.league, flag: l.flag,
      vec: [sx, l.y0, mx, l.y0, mx, l.y1, tx, l.y1, Math.max(1, l.width)],
    });
  }
  return { nodes, links, homeLeague: g.homeLeague };
}

const pathOf = (v) => `M${v[0]},${v[1]}C${v[2]},${v[3]} ${v[4]},${v[5]} ${v[6]},${v[7]}`;

// ── headline copy generators ─────────────────────────────────────────────────
function verdict(n, n_nations) {
  const { nation, domestic, n_players, domestic_rank } = n;
  const head = `${domestic} of ${n_players} players play at home`;
  let tail;
  if (domestic === 0) tail = `not one plays in the ${nation} league — the most far-flung squad of the 48`;
  else if (domestic_rank === 1) tail = "the most insular squad in the tournament";
  else if (domestic_rank <= 5) tail = `the ${ord(domestic_rank)} most home-based squad of ${n_nations}`;
  else if (domestic_rank >= n_nations - 4) tail = `among the most well-travelled squads, ${ord(n_nations - domestic_rank + 1)} most dispersed of ${n_nations}`;
  else tail = `${ord(domestic_rank)} most home-based of ${n_nations}`;
  return { head, tail };
}

function annotation(n) {
  const players = n.players;
  const total = players.length;
  const abroad = players.filter((p) => !p.domestic);
  const home = players.filter((p) => p.domestic);
  const countries = new Set(players.map((p) => p.country)).size;

  // top league by headcount
  const byLeague = {};
  for (const p of players) byLeague[p.league] = (byLeague[p.league] || 0) + 1;
  const [topLeague, topN] = Object.entries(byLeague).sort((a, b) => b[1] - a[1])[0];

  const s1 = `${topN === total ? "Every one" : `${topN} of the ${total}`} ${topN === 1 ? "player earns" : "players earn"} their living in the ${topLeague}${topN >= total / 2 ? " alone" : ""}.`;
  const s2 = `The squad draws on ${n.n_leagues} league${n.n_leagues === 1 ? "" : "s"} across ${countries} countr${countries === 1 ? "y" : "ies"}.`;

  let s3 = "";
  if (abroad.length === 1) {
    const p = abroad[0];
    s3 = `${p.name} (${p.club}, ${p.country}) is the sole exception — the only player based overseas.`;
  } else if (home.length === 1) {
    const p = home[0];
    s3 = `Only ${p.name} (${p.club}) still plays at home.`;
  } else if (abroad.length) {
    // heaviest single foreign league
    const foreign = {};
    for (const p of abroad) foreign[p.league] = (foreign[p.league] || 0) + 1;
    const [fl, fn] = Object.entries(foreign).sort((a, b) => b[1] - a[1])[0];
    s3 = `Abroad, the biggest contingent is the ${fn} in the ${fl}.`;
  }
  return [s1, s2, s3].filter(Boolean).join(" ");
}

// ════════════════════════════════════════════════════════════════════════════
export default function NationSankey() {
  const [data, setData] = useState(null);
  const [code, setCode] = useState(null);          // selected nation code
  const [tip, setTip] = useState(null);            // link hover tooltip
  const [expand, setExpand] = useState(null);      // clicked league node (clubs)
  const [frame, setFrame] = useState(null);        // current interpolated layout
  const [query, setQuery] = useState("");
  const [openSwitch, setOpenSwitch] = useState(null); // 'search' | 'grid' | null
  const reduce = useReducedMotion();
  const wrapRef = useRef(null);
  const animRef = useRef({ raf: 0, rendered: null });

  useEffect(() => {
    fetch("./nations.json").then((r) => r.json()).then((d) => {
      setData(d);
      const hash = decodeURIComponent(location.hash.replace(/^#/, "")).trim().toLowerCase();
      const fromHash = d.nations.find(
        (n) => n.code.toLowerCase() === hash || n.nation.toLowerCase() === hash
      );
      setCode(fromHash?.code || d.nations.find((n) => n.nation === "Qatar")?.code || d.nations[0].code);
    });
  }, []);

  // keep the URL hash shareable
  useEffect(() => {
    if (code) history.replaceState(null, "", "#" + code);
  }, [code]);

  const byCode = useMemo(() => {
    const m = new Map();
    data?.nations.forEach((n) => m.set(n.code, n));
    return m;
  }, [data]);
  const nation = code ? byCode.get(code) : null;

  // animate the sankey from the previously rendered snapshot to the new one
  useEffect(() => {
    if (!nation) return;
    setExpand(null); setTip(null);
    const to = snapshot(nation);
    const from = animRef.current.rendered;
    cancelAnimationFrame(animRef.current.raf);

    if (!from || reduce) { animRef.current.rendered = to; setFrame(render(to, to, 1)); return; }

    const t0 = performance.now();
    const step = (now) => {
      const p = Math.min(1, (now - t0) / DUR);
      const e = ease(p);
      setFrame(render(from, to, e));
      if (p < 1) animRef.current.raf = requestAnimationFrame(step);
      else animRef.current.rendered = to;
    };
    animRef.current.raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(animRef.current.raf);
  }, [code, reduce]); // eslint-disable-line

  if (!data || !nation || !frame) {
    return <div className="ns-root ns-loading"><style>{CSS}</style>Loading squads…</div>;
  }

  const prim = nation.colors.primary;
  const sec = nation.colors.secondary;
  const v = verdict(nation, data.n_nations);
  const order = data.chips;                          // most → least insular
  const idx = order.findIndex((c) => c.code === code);
  const go = (delta) => {
    const next = order[(idx + delta + order.length) % order.length];
    setCode(next.code);
  };
  const filtered = data.nations
    .filter((n) => n.nation.toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => a.nation.localeCompare(b.nation));

  return (
    <div className="ns-root" style={{ "--prim": prim, "--sec": sec }}>
      <style>{CSS}</style>

      {/* ── masthead ─────────────────────────────────────────────────────── */}
      <header className="ns-mast">
        <div className="ns-kicker">World Cup 2026 · Club &amp; Country</div>
        <div className="ns-headrow">
          <span className="ns-flag" aria-hidden>{nation.flag}</span>
          <h1 className="ns-title">{nation.nation}</h1>
          <Switcher
            {...{ data, code, setCode, go, openSwitch, setOpenSwitch, query, setQuery, filtered, order }}
          />
        </div>
        <p className="ns-verdict">
          <b>{v.head}</b> — {v.tail}.
        </p>
      </header>

      <hr className="ns-rule" />

      {/* ── three stat callouts ──────────────────────────────────────────── */}
      <section className="ns-stats">
        <Stat value={nation.domestic_pct} suffix="%" label="play in the home league" enabled={!reduce} decimals={1} />
        <Stat value={nation.n_leagues} label="leagues represented" enabled={!reduce} />
        <Stat value={nation.domestic_rank} prefix="#" label={`most home-based of ${data.n_nations}`} enabled={!reduce} />
      </section>

      <hr className="ns-rule" />

      {/* ── hero sankey ──────────────────────────────────────────────────── */}
      <section className="ns-chartwrap" ref={wrapRef}>
        <div className="ns-axislabels">
          <span>The squad, by position</span>
          <span>Where they play their club football</span>
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} className="ns-svg" role="img"
             aria-label={`${nation.nation} squad composition flowing from position to league`}
             onClick={() => setExpand(null)}>
          <defs>
            {frame.links.map((l) => (
              <linearGradient key={l.id} id={`g-${cssId(l.id)}`} x1="0" x2="1" y1="0" y2="0">
                <stop offset="0%" stopColor={prim} />
                <stop offset="100%" stopColor={l.domestic ? prim : NEUTRAL} />
              </linearGradient>
            ))}
          </defs>

          {/* links */}
          <g>
            {frame.links.map((l) => (
              <path key={l.id} d={pathOf(l.vec)} className={"ns-link" + (l.domestic ? " is-home" : "")}
                stroke={`url(#g-${cssId(l.id)})`} strokeWidth={l.vec[8]} fill="none"
                style={{ opacity: l.opacity * (l.domestic ? 0.82 : 0.5) }}
                onMouseMove={(e) => moveTip(e, wrapRef, l, setTip)}
                onMouseLeave={() => setTip(null)} />
            ))}
          </g>

          {/* nodes + labels */}
          <g>
            {frame.nodes.map((n) => {
              const [x0, y0, x1, y1] = n.rect;
              const isPos = n.kind === "pos";
              const fill = isPos ? INK : n.domestic ? prim : "#C9C2B5";
              return (
                <g key={n.id} style={{ opacity: n.opacity }}>
                  <rect x={x0} y={y0} width={Math.max(0.5, x1 - x0)} height={Math.max(0.5, y1 - y0)}
                    rx="2" fill={fill}
                    className={"ns-node" + (n.kind === "league" ? " is-clickable" : "")}
                    stroke={n.domestic ? prim : "none"} strokeWidth={n.domestic ? 1.5 : 0}
                    onClick={(e) => { e.stopPropagation(); if (n.kind === "league") setExpand(expand === n.id ? null : n.id); }} />
                  {isPos ? (
                    <text className="ns-poslabel" x={x0 - 12} y={(y0 + y1) / 2} textAnchor="end">
                      <tspan x={x0 - 12} dy="-0.15em" className="ns-poslabel-name">{n.name}</tspan>
                      <tspan x={x0 - 12} dy="1.15em" className="ns-poslabel-n">{n.count} player{n.count === 1 ? "" : "s"}</tspan>
                    </text>
                  ) : (
                    <text className={"ns-leaguelabel" + (n.domestic ? " is-home" : "")}
                      x={x1 + 12} y={(y0 + y1) / 2}
                      onClick={(e) => { e.stopPropagation(); setExpand(expand === n.id ? null : n.id); }}>
                      <tspan x={x1 + 12} dy="-0.2em" className="ns-lg-name">
                        {n.flag} {n.name}{n.domestic ? "  ·  home" : ""}
                      </tspan>
                      <tspan x={x1 + 12} dy="1.2em" className="ns-lg-n">
                        {n.count} player{n.count === 1 ? "" : "s"} · tap for clubs
                      </tspan>
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>

        {/* link tooltip */}
        {tip && (
          <div className="ns-tip" style={{ left: tip.x, top: tip.y }}>
            <div className="ns-tip-head">
              {tip.flag} {tip.league} <span>· {tip.players.length} {posWord(tip)}</span>
            </div>
            <ul>
              {tip.players.slice(0, 8).map((p) => (
                <li key={p.name}><span className="ns-tip-name">{p.name}</span>
                  <span className="ns-tip-meta">{p.club} · {p.caps} caps</span></li>
              ))}
              {tip.players.length > 8 && <li className="ns-tip-more">+{tip.players.length - 8} more</li>}
            </ul>
          </div>
        )}

        {/* league → clubs expansion card */}
        {expand && <ClubCard node={frame.nodes.find((n) => n.id === expand)} prim={prim} onClose={() => setExpand(null)} />}
      </section>

      {/* ── auto-written annotation ───────────────────────────────────────── */}
      <section className="ns-annot">
        <span className="ns-annot-mark" style={{ background: prim }} />
        <p>{annotation(nation)}</p>
      </section>

      <hr className="ns-rule" />

      {/* ── context strip: all 48, ordered by domestic dependency ─────────── */}
      <section className="ns-strip">
        <div className="ns-strip-cap">
          <span>Domestic dependency, all 48</span>
          <span className="ns-strip-axis">most home-based&nbsp;→&nbsp;most dispersed</span>
        </div>
        <div className="ns-chips">
          {order.map((c) => (
            <button key={c.code}
              className={"ns-chip" + (c.code === code ? " is-active" : "")}
              title={`${c.nation} · ${c.domestic_pct}% home`}
              onClick={() => setCode(c.code)}>
              <span className="ns-chip-flag">{c.flag}</span>
              <span className="ns-chip-bar"><i style={{ width: `${c.domestic_pct}%` }} /></span>
            </button>
          ))}
        </div>
      </section>

      <footer className="ns-foot">
        1,246 players · 48 squads · source: Wikipedia 2026 World Cup squad tables.
        Leagues with a single player fold into “Other leagues”. Domestic league shown in {nation.nation}’s colours.
      </footer>
    </div>
  );
}

// ── render an interpolated frame between two snapshots ────────────────────────
function render(from, to, p) {
  const ids = new Set([...from.nodes.keys(), ...to.nodes.keys()]);
  const nodes = [];
  for (const id of ids) {
    const a = from.nodes.get(id), b = to.nodes.get(id);
    if (a && b) nodes.push({ ...b, rect: a.rect.map((x, i) => lerp(x, b.rect[i], p)), opacity: 1 });
    else if (b) nodes.push({ ...b, opacity: p });          // appearing
    else nodes.push({ ...a, opacity: 1 - p });             // leaving
  }
  const lids = new Set([...from.links.keys(), ...to.links.keys()]);
  const links = [];
  for (const id of lids) {
    const a = from.links.get(id), b = to.links.get(id);
    if (a && b) links.push({ ...b, vec: a.vec.map((x, i) => lerp(x, b.vec[i], p)), opacity: 1 });
    else if (b) links.push({ ...b, opacity: p });
    else links.push({ ...a, opacity: 1 - p });
  }
  // draw thicker/home links last so they read on top
  links.sort((x, y) => (x.domestic - y.domestic) || (x.vec[8] - y.vec[8]));
  return { nodes, links };
}

// ── sub-components ────────────────────────────────────────────────────────────
function Stat({ value, label, prefix = "", suffix = "", decimals = 0, enabled }) {
  const v = useCountUp(value, enabled);
  const shown = decimals ? v.toFixed(decimals) : Math.round(v);
  return (
    <div className="ns-stat">
      <div className="ns-stat-num">{prefix}{shown}{suffix}</div>
      <div className="ns-stat-lab">{label}</div>
    </div>
  );
}

function Switcher({ data, code, setCode, go, openSwitch, setOpenSwitch, query, setQuery, filtered, order }) {
  const ref = useRef(null);
  useEffect(() => {
    const f = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpenSwitch(null); };
    document.addEventListener("mousedown", f);
    return () => document.removeEventListener("mousedown", f);
  }, [setOpenSwitch]);
  return (
    <div className="ns-switch" ref={ref}>
      <button className="ns-arrow" onClick={() => go(-1)} aria-label="Previous nation">‹</button>
      <button className="ns-pick" onClick={() => setOpenSwitch(openSwitch === "search" ? null : "search")}>
        Change nation <span className="ns-caret">▾</span>
      </button>
      <button className="ns-arrow" onClick={() => go(1)} aria-label="Next nation">›</button>
      <button className="ns-grid-toggle" onClick={() => setOpenSwitch(openSwitch === "grid" ? null : "grid")}
        aria-label="Flag grid">⊞</button>

      {openSwitch === "search" && (
        <div className="ns-pop ns-pop-search">
          <input autoFocus placeholder="Search 48 nations…" value={query}
            onChange={(e) => setQuery(e.target.value)} className="ns-search-input" />
          <ul>
            {filtered.map((n) => (
              <li key={n.code}>
                <button className={n.code === code ? "is-active" : ""}
                  onClick={() => { setCode(n.code); setOpenSwitch(null); setQuery(""); }}>
                  <span>{n.flag}</span> {n.nation}
                  <em>{n.domestic_pct}% home</em>
                </button>
              </li>
            ))}
            {!filtered.length && <li className="ns-noresult">No match</li>}
          </ul>
        </div>
      )}
      {openSwitch === "grid" && (
        <div className="ns-pop ns-pop-grid">
          {order.map((c) => (
            <button key={c.code} className={c.code === code ? "is-active" : ""}
              title={c.nation} onClick={() => { setCode(c.code); setOpenSwitch(null); }}>
              <span className="ns-grid-flag">{c.flag}</span>
              <span className="ns-grid-name">{c.nation}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ClubCard({ node, prim, onClose }) {
  if (!node) return null;
  const [, , x1, y0] = node.rect;
  const left = Math.min(x1 / W * 100, 64);
  return (
    <div className="ns-clubcard" style={{ left: `${left}%`, top: `${(y0 / H) * 100}%`, "--prim": prim }}>
      <div className="ns-clubcard-head">
        <b>{node.flag} {node.name}</b>
        <button onClick={onClose} aria-label="Close">×</button>
      </div>
      <ul>
        {node.clubs.map((c) => (
          <li key={c.club}>
            <span className="ns-club-bar" style={{ width: `${(c.n / node.count) * 100}%` }} />
            <span className="ns-club-name">{c.club}</span>
            <span className="ns-club-n">{c.n}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── helpers used in render ────────────────────────────────────────────────────
const cssId = (s) => s.replace(/[^a-zA-Z0-9]/g, "_");
function posWord(l) {
  // the players in a link all share a position group
  const g = l.players[0]?.posGroup;
  return g ? g.toLowerCase() : "players";
}
function moveTip(e, wrapRef, l, setTip) {
  const r = wrapRef.current.getBoundingClientRect();
  setTip({
    x: Math.min(e.clientX - r.left + 14, r.width - 230),
    y: e.clientY - r.top + 14,
    league: l.league, flag: l.flag, players: l.players,
  });
}

// ── styles (injected once; component is self-contained) ───────────────────────
const CSS = `
.ns-root{--prim:#7A1530;--sec:#1B1B1F;background:${OFFWHITE};color:${INK};
  font-family:"Helvetica Neue",-apple-system,system-ui,sans-serif;
  max-width:1080px;margin:0 auto;padding:38px 30px 56px;position:relative;
  -webkit-font-smoothing:antialiased;}
.ns-loading{font-family:"Newsreader",Georgia,serif;font-size:20px;color:${MUTE};padding:80px 30px;}
.ns-rule{border:0;border-top:1px solid ${HAIR};margin:24px 0;}

/* masthead */
.ns-kicker{font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:${MUTE};
  font-weight:600;margin-bottom:14px;}
.ns-headrow{display:flex;align-items:center;gap:18px;flex-wrap:wrap;}
.ns-flag{font-size:54px;line-height:1;filter:drop-shadow(0 1px 1px rgba(0,0,0,.12));}
.ns-title{font-family:"Newsreader","Newsreader",Georgia,serif;font-weight:600;font-size:clamp(40px,7vw,76px);
  line-height:.96;letter-spacing:-.02em;margin:0;color:var(--prim);transition:color .5s ease;}
.ns-verdict{font-family:"Newsreader",Georgia,serif;font-size:clamp(16px,2.2vw,21px);color:${INK};
  margin:16px 0 0;max-width:54ch;line-height:1.45;}
.ns-verdict b{color:var(--prim);font-weight:600;}

/* team switcher */
.ns-switch{display:flex;align-items:center;gap:6px;margin-left:auto;position:relative;}
.ns-arrow,.ns-grid-toggle{width:34px;height:34px;border:1px solid ${HAIR};background:#fff;border-radius:50%;
  font-size:17px;color:${INK};cursor:pointer;display:grid;place-items:center;transition:.15s;}
.ns-arrow:hover,.ns-grid-toggle:hover{border-color:var(--prim);color:var(--prim);}
.ns-grid-toggle{border-radius:9px;font-size:15px;}
.ns-pick{border:1px solid ${INK};background:${INK};color:#fff;border-radius:20px;padding:8px 16px;
  font-size:13px;font-weight:600;cursor:pointer;letter-spacing:.01em;transition:.15s;}
.ns-pick:hover{background:var(--prim);border-color:var(--prim);}
.ns-caret{font-size:9px;opacity:.7;margin-left:3px;}
.ns-pop{position:absolute;top:42px;right:0;background:#fff;border:1px solid ${HAIR};
  border-radius:12px;box-shadow:0 18px 48px rgba(30,25,15,.16);z-index:40;overflow:hidden;}
.ns-pop-search{width:260px;}
.ns-search-input{width:100%;border:0;border-bottom:1px solid ${HAIR};padding:13px 15px;font-size:14px;
  outline:none;font-family:inherit;background:${PAPER};}
.ns-pop-search ul{list-style:none;margin:0;padding:6px;max-height:300px;overflow:auto;}
.ns-pop-search li button{width:100%;display:flex;align-items:center;gap:9px;border:0;background:none;
  padding:8px 10px;border-radius:8px;font-size:13.5px;cursor:pointer;color:${INK};text-align:left;font-family:inherit;}
.ns-pop-search li button em{margin-left:auto;font-style:normal;font-size:11px;color:${MUTE};}
.ns-pop-search li button:hover{background:${PAPER};}
.ns-pop-search li button.is-active{color:var(--prim);font-weight:700;}
.ns-noresult{padding:14px;color:${MUTE};font-size:13px;text-align:center;}
.ns-pop-grid{width:330px;max-height:340px;overflow:auto;display:grid;grid-template-columns:1fr 1fr;gap:2px;padding:8px;}
.ns-pop-grid button{display:flex;align-items:center;gap:7px;border:0;background:none;padding:7px 8px;border-radius:7px;
  cursor:pointer;font-size:12px;color:${INK};text-align:left;font-family:inherit;}
.ns-pop-grid button:hover{background:${PAPER};}
.ns-pop-grid button.is-active{background:var(--prim);color:#fff;}
.ns-grid-flag{font-size:17px;}
.ns-grid-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}

/* stats */
.ns-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;}
.ns-stat-num{font-family:"Newsreader",Georgia,serif;font-size:clamp(40px,6vw,64px);font-weight:600;line-height:1;
  color:var(--prim);letter-spacing:-.02em;font-variant-numeric:tabular-nums;transition:color .5s ease;}
.ns-stat-lab{font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:${MUTE};
  font-weight:600;margin-top:9px;max-width:22ch;}

/* chart */
.ns-chartwrap{position:relative;margin:6px 0 4px;}
.ns-axislabels{display:flex;justify-content:space-between;font-size:11px;letter-spacing:.1em;
  text-transform:uppercase;color:${MUTE};font-weight:600;padding:0 4px 6px;}
.ns-svg{width:100%;height:auto;display:block;overflow:visible;}
.ns-link{transition:opacity .2s;cursor:pointer;}
.ns-link:hover{opacity:.95 !important;}
.ns-node{cursor:default;}
.ns-node.is-clickable{cursor:pointer;}
.ns-poslabel-name{font-family:"Newsreader",Georgia,serif;font-size:15px;font-weight:600;fill:${INK};}
.ns-poslabel-n{font-size:10.5px;fill:${MUTE};letter-spacing:.04em;text-transform:uppercase;}
.ns-leaguelabel{cursor:pointer;}
.ns-lg-name{font-size:13.5px;font-weight:600;fill:${INK};}
.ns-leaguelabel.is-home .ns-lg-name{fill:var(--prim);}
.ns-lg-n{font-size:10px;fill:${MUTE};letter-spacing:.03em;}

/* link tooltip */
.ns-tip{position:absolute;z-index:30;background:${INK};color:#fff;border-radius:10px;padding:11px 13px;
  width:216px;box-shadow:0 14px 36px rgba(0,0,0,.28);pointer-events:none;font-size:12px;}
.ns-tip-head{font-weight:700;margin-bottom:7px;font-size:12.5px;}
.ns-tip-head span{font-weight:400;opacity:.65;}
.ns-tip ul{list-style:none;margin:0;padding:0;}
.ns-tip li{display:flex;flex-direction:column;padding:3px 0;border-top:1px solid rgba(255,255,255,.1);}
.ns-tip-name{font-weight:600;}
.ns-tip-meta{opacity:.62;font-size:10.5px;}
.ns-tip-more{opacity:.6;font-style:italic;padding-top:5px;}

/* club card */
.ns-clubcard{position:absolute;z-index:35;background:#fff;border:1px solid ${HAIR};border-radius:12px;
  padding:12px 14px;width:248px;box-shadow:0 18px 46px rgba(30,25,15,.2);}
.ns-clubcard-head{display:flex;justify-content:space-between;align-items:center;font-size:13.5px;margin-bottom:8px;
  border-bottom:1px solid ${HAIR};padding-bottom:7px;}
.ns-clubcard-head button{border:0;background:none;font-size:18px;line-height:1;color:${MUTE};cursor:pointer;}
.ns-clubcard ul{list-style:none;margin:0;padding:0;}
.ns-clubcard li{position:relative;display:flex;align-items:center;padding:5px 6px;font-size:12.5px;border-radius:5px;overflow:hidden;}
.ns-club-bar{position:absolute;left:0;top:0;bottom:0;background:var(--prim);opacity:.13;border-radius:5px;}
.ns-club-name{position:relative;z-index:1;}
.ns-club-n{position:relative;z-index:1;margin-left:auto;font-weight:700;color:var(--prim);}

/* annotation */
.ns-annot{display:flex;gap:14px;margin:18px 0 6px;max-width:72ch;}
.ns-annot-mark{flex:0 0 4px;border-radius:2px;}
.ns-annot p{font-family:"Newsreader",Georgia,serif;font-size:17px;line-height:1.55;color:${INK};margin:0;}

/* context strip */
.ns-strip-cap{display:flex;justify-content:space-between;font-size:11px;letter-spacing:.13em;
  text-transform:uppercase;color:${MUTE};font-weight:600;margin-bottom:10px;}
.ns-strip-axis{letter-spacing:.04em;opacity:.8;}
.ns-chips{display:flex;flex-wrap:wrap;gap:5px;}
.ns-chip{display:flex;flex-direction:column;align-items:center;gap:3px;border:0;background:none;cursor:pointer;
  padding:3px 2px;border-radius:6px;width:30px;opacity:.55;transition:.18s;}
.ns-chip:hover{opacity:1;background:${PAPER};}
.ns-chip.is-active{opacity:1;background:#fff;box-shadow:0 0 0 2px var(--prim);}
.ns-chip-flag{font-size:17px;line-height:1;}
.ns-chip-bar{width:100%;height:3px;background:${HAIR};border-radius:2px;overflow:hidden;}
.ns-chip-bar i{display:block;height:100%;background:${MUTE};}
.ns-chip.is-active .ns-chip-bar i{background:var(--prim);}

.ns-foot{margin-top:26px;font-size:11.5px;color:${MUTE};line-height:1.6;max-width:70ch;}

@media (max-width:680px){
  .ns-stats{grid-template-columns:1fr;gap:14px;}
  .ns-switch{margin-left:0;width:100%;}
  .ns-axislabels span:last-child{text-align:right;}
}
@media (prefers-reduced-motion:reduce){
  .ns-title,.ns-stat-num,.ns-link,.ns-chip{transition:none !important;}
}
`;
