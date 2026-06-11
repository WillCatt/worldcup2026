import { useEffect, useMemo, useState } from "react";
import Sankey, { colorFor } from "./Sankey.jsx";

export default function App() {
  const [data, setData] = useState(null);
  const [mode, setMode] = useState("league");      // 'league' | 'club'
  const [selected, setSelected] = useState(null);
  const [hover, setHover] = useState(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("domestic");    // 'domestic' | 'spread'

  useEffect(() => {
    fetch("./squads.json").then((r) => r.json()).then((d) => {
      setData(d);
      setSelected(d.nations.find((n) => n.nation === "Senegal")?.nation || d.nations[0].nation);
    });
  }, []);

  const active = hover || selected;

  // top-15 leagues kept as their own nodes; the rest fold into "Other leagues"
  const keep = useMemo(
    () => (data ? new Set(data.league_leaderboard.slice(0, 15).map((l) => l.league)) : new Set()),
    [data]
  );

  // league-level Sankey: all 48 nations → leagues
  const leagueSankey = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    const linkMap = new Map();
    data.nations.forEach((nat) => {
      nat.leagues.forEach((lg) => {
        const name = keep.has(lg.league) ? lg.league : "Other leagues";
        const k = nat.nation + "→" + name;
        linkMap.set(k, (linkMap.get(k) || 0) + lg.count);
      });
    });
    const leagueNames = [...data.league_leaderboard.slice(0, 15).map((l) => l.league)];
    if ([...linkMap.keys()].some((k) => k.endsWith("Other leagues"))) leagueNames.push("Other leagues");
    const nodes = [
      ...data.nations.map((n) => ({ id: "N:" + n.nation, name: n.nation, side: "nation" })),
      ...leagueNames.map((l) => ({ id: "L:" + l, name: l, side: "league" })),
    ];
    const links = [...linkMap.entries()].map(([k, v]) => {
      const [s, t] = k.split("→");
      return { source: "N:" + s, target: "L:" + t, value: v };
    });
    return { nodes, links };
  }, [data, keep]);

  // club-level Sankey: the selected nation → its clubs
  const clubSankey = useMemo(() => {
    if (!data || !selected) return { nodes: [], links: [] };
    const nat = data.nations.find((n) => n.nation === selected);
    const nodes = [{ id: "N:" + nat.nation, name: nat.nation, side: "nation" },
      ...nat.clubs.map((c) => ({ id: "C:" + c.club, name: c.club, side: "club", country: c.country }))];
    const links = nat.clubs.map((c) => ({ source: "N:" + nat.nation, target: "C:" + c.club, value: c.count }));
    return { nodes, links };
  }, [data, selected]);

  if (!data) return <div className="app"><p style={{ paddingTop: 80 }}>Loading…</p></div>;

  const rows = [...data.nations].sort((a, b) =>
    sort === "domestic" ? b.domestic_pct - a.domestic_pct : b.n_leagues - a.n_leagues);
  const shown = query ? rows.filter((r) => r.nation.toLowerCase().includes(query.toLowerCase())) : rows;
  const sel = data.nations.find((n) => n.nation === selected);
  const sankey = mode === "league" ? leagueSankey : clubSankey;
  const sankeyHeight = mode === "league"
    ? Math.max(620, data.nations.length * 19)
    : Math.max(300, clubSankey.nodes.length * 26);

  return (
    <div className="app">
      <a className="back-link" href="../../index.html">← All explorations</a>

      <header className="hero">
        <p className="eyebrow">Machine Learning in Football · 04</p>
        <h1>Club &amp; Country</h1>
        <p className="lede">Where do the 2026 World Cup's {data.n_players} players actually earn their
          living? Every squad mapped to the leagues that employ it — <em>England pools into the
          Premier League; Senegal fans out across a dozen countries.</em> Hover a nation to isolate
          its flows.</p>
      </header>

      <div className="grid">
        {/* leaderboard */}
        <section className="board">
          <div className="board-head">
            <h2>Domestic dependency</h2>
            <div className="sort-toggle">
              <button className={sort === "domestic" ? "on" : ""} onClick={() => setSort("domestic")}>% home</button>
              <button className={sort === "spread" ? "on" : ""} onClick={() => setSort("spread")}>spread</button>
            </div>
          </div>
          <div className="board-search">
            <input type="search" placeholder="Search a nation…" value={query}
                   onChange={(e) => setQuery(e.target.value)} />
          </div>
          <div className="board-list">
            {shown.map((r) => (
              <div key={r.nation}
                   className={"row" + (r.nation === selected ? " sel" : "") + (r.nation === hover ? " hov" : "")}
                   onClick={() => setSelected(r.nation)}
                   onMouseEnter={() => setHover(r.nation)} onMouseLeave={() => setHover(null)}>
                <span className="nm">{r.nation}</span>
                <span className="bar-wrap">
                  <span className="bar" style={{ width: Math.max(3, r.domestic_pct * 0.9) + "px" }} />
                  <span className="bval">{sort === "domestic" ? r.domestic_pct + "%" : r.n_leagues + " lg"}</span>
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* sankey + detail */}
        <section className="detail">
          <div className="controls">
            <div className="mode-toggle">
              <button className={mode === "league" ? "on" : ""} onClick={() => setMode("league")}>Leagues</button>
              <button className={mode === "club" ? "on" : ""} onClick={() => setMode("club")}>Clubs</button>
            </div>
            <p className="mode-hint">
              {mode === "league"
                ? "All 48 squads → the leagues that employ them. Hover to isolate a nation."
                : <>Club-level flows for <b>{selected}</b> — pick another nation on the left.</>}
            </p>
          </div>

          <div className="sankey-wrap">
            <Sankey {...sankey} height={sankeyHeight} active={mode === "league" ? active : null}
                    onHover={mode === "league" ? setHover : () => {}}
                    showSourceLabels={mode === "club"} />
          </div>

          {sel && (
            <div className="nat-detail">
              <div className="nd-head">
                <h3>{sel.nation}</h3>
                <div className="nd-stats">
                  <span><b>{sel.domestic_pct}%</b> play at home</span>
                  <span><b>{sel.n_leagues}</b> leagues</span>
                  <span><b>{sel.n_players}</b> players</span>
                </div>
              </div>
              <div className="nd-bars">
                {sel.leagues.map((lg, i) => (
                  <div className="nd-bar" key={lg.league}>
                    <span className="ndl">{lg.league}{lg.domestic && <em> · home</em>}</span>
                    <span className="ndt">
                      <span style={{ width: (lg.count / sel.n_players) * 100 + "%",
                                     background: colorFor(lg.league, i) }} />
                    </span>
                    <span className="ndv">{lg.count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>

      <section className="method">
        <h2>The unglamorous bit: reconciling messy entities</h2>
        <p>The same club arrives as <code>Manchester City F.C.</code>, <code>FC Bayern Munich</code>,
          <code>Al Hilal SFC</code> — inconsistent prefixes, suffixes, piped wiki-links and accents.
          Before a single number is trustworthy, all {data.n_players} players are parsed from the raw
          Wikipedia squad tables (no scraping), club strings normalised to clean labels, and 71
          club-country codes mapped onto named leagues. The "<b>league</b>" is the destination
          country's top competition — a player at a Championship club still counts under England, a
          caveat worth naming. Aggregation, not modelling, is the work here — and it's the work most
          data jobs actually need.</p>
      </section>

      <footer>
        Source: Wikipedia 2026 World Cup squad lists · entity resolution + aggregation in{" "}
        <code>mlfootball/squads.py</code> · flows rendered with <code>d3-sankey</code>. No live API.
      </footer>
    </div>
  );
}
