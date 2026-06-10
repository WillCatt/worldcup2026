// Confederation-level charts for the international football network.
// Reads the small site/data/network.json aggregate (a 6x6 flow matrix + a few arrays) and
// renders four legible-by-construction views: a chord of cross-confederation flow, a flow
// matrix, an insularity ranking, and the bridge teams. No 217-node hairball in sight.

const CONF = {
  UEFA:     { color: "#b06a16", name: "UEFA (Europe)" },
  CONMEBOL: { color: "#2a8f8f", name: "CONMEBOL (S. America)" },
  CONCACAF: { color: "#4a6d8c", name: "CONCACAF (N./C. America)" },
  CAF:      { color: "#3a8f57", name: "CAF (Africa)" },
  AFC:      { color: "#c0533b", name: "AFC (Asia)" },
  OFC:      { color: "#7d5ba6", name: "OFC (Oceania)" },
};
const INK = "#1a1714";

const tip = d3.select("body").append("div").attr("class", "tooltip");
const showTip = html => tip.html(html).style("opacity", 1);
const moveTip = e => tip.style("left", e.pageX + "px").style("top", e.pageY + "px");
const hideTip = () => tip.style("opacity", 0);
const pct = x => Math.round(x * 100) + "%";

Promise.all([
  d3.json("../data/network.json"),
  d3.json("../data/graph_adjacency.json"),
]).then(([G, A]) => {
  const drawAll = () => {
    fillStats(G);
    chordChart(G);
    matrixChart(G);
    insularityChart(G);
    temporalChart(G);
    smallWorldChart(G);
    centralityChart(G);
    sunburstChart(G);
    robustnessChart(G);
  };
  drawAll();
  fillFindings(G);
  buildConnector(A);                 // one-time: populates selects + binds
  window.addEventListener("resize", debounce(drawAll, 200));
});

// ── header cards + findings ──────────────────────────────────────────
function fillStats(G) {
  const m = G.metrics;
  d3.select("#stats").html(`
    <div class="stat"><div class="num">${pct(m.within_share)}</div>
      <div class="lbl">of all games stay within a team's own confederation</div></div>
    <div class="stat"><div class="num">${m.nmi.toFixed(2)}</div>
      <div class="lbl">NMI — how cleanly the continents emerge from match patterns alone</div></div>
    <div class="stat"><div class="num">${m.n_communities}<small> / 6</small></div>
      <div class="lbl">communities the algorithm finds — the two Americas merge into one</div></div>`);
}

function fillFindings(G) {
  const m = G.metrics, names = G.bridges.slice(0, 5).map(b => b.team).join(", ");
  d3.select("#findings").html(`
    <article><h3>1 · Teams almost never leave home</h3>
      <p><strong>${pct(m.within_share)}</strong> of games are played within a team's own
      confederation — barely one match in seven crosses continents, so the evidence linking
      blocs is desperately thin.</p></article>
    <article><h3>2 · The continents draw themselves</h3>
      <p>An algorithm blind to geography recovers the confederations from match patterns alone
      (NMI <strong>${m.nmi.toFixed(2)}</strong>) — but finds <strong>five blocs, not six</strong>:
      CONMEBOL and CONCACAF fuse into one Americas super-bloc.</p></article>
    <article><h3>3 · Held up by a few bridges</h3>
      <p>The whole cross-continental picture leans on a handful of <strong>bridge</strong> teams —
      ${names} — the only sides that regularly venture beyond their own continent.</p></article>`);
}

// ── Chart 1 · chord of cross-confederation flow ──────────────────────
function chordChart(G) {
  const order = G.conf_order;
  const svg = setup("#chord");
  const { w, h } = svg;
  const outer = Math.min(w, h) / 2 - 56, inner = outer - 14;

  // Cross-flow only: zero the diagonal so the thin links between blocs are the whole picture.
  const M = G.matrix.map((row, i) => row.map((v, j) => (i === j ? 0 : v)));

  const chords = d3.chord().padAngle(0.05).sortSubgroups(d3.descending)(M);
  const g = svg.sel.append("g").attr("transform", `translate(${w / 2},${h / 2})`);
  const arc = d3.arc().innerRadius(inner).outerRadius(outer);
  const ribbon = d3.ribbon().radius(inner);

  const group = g.append("g").selectAll("g").data(chords.groups).join("g");
  group.append("path").attr("class", "chord-arc")
    .attr("d", arc)
    .attr("fill", d => CONF[order[d.index]].color)
    .attr("stroke", d => d3.color(CONF[order[d.index]].color).darker(0.6))
    .on("mouseenter", (e, d) => focusBloc(d.index))
    .on("mouseleave", clearFocus);

  group.append("text").each(d => { d.mid = (d.startAngle + d.endAngle) / 2; })
    .attr("class", "chord-arc-label")
    .attr("dy", ".35em")
    .attr("transform", d => `rotate(${d.mid * 180 / Math.PI - 90})`
      + `translate(${outer + 8})` + (d.mid > Math.PI ? "rotate(180)" : ""))
    .attr("text-anchor", d => d.mid > Math.PI ? "end" : null)
    .text(d => order[d.index]);

  const ribbons = g.append("g").selectAll("path").data(chords).join("path")
    .attr("class", "chord-ribbon")
    .attr("d", ribbon)
    .attr("fill", d => CONF[order[d.source.index]].color)
    .attr("stroke", d => d3.color(CONF[order[d.source.index]].color).darker(0.4))
    .attr("opacity", 0.62)
    .on("mouseenter", function (e, d) {
      const a = order[d.source.index], b = order[d.target.index];
      const shareA = G.matrix[d.source.index][d.target.index]
        / G.matrix[d.source.index].reduce((s, x) => s + x, 0);
      showTip(`<b>${a} ↔ ${b}</b>
        <div class="t-row"><span>${a}'s games vs ${b}</span><span>${pct(shareA)}</span></div>`);
    })
    .on("mousemove", moveTip).on("mouseleave", hideTip);

  function focusBloc(i) {
    ribbons.classed("dim", d => d.source.index !== i && d.target.index !== i);
    group.classed("dim", d => {
      if (d.index === i) return false;
      return !chords.some(c => (c.source.index === i && c.target.index === d.index)
        || (c.target.index === i && c.source.index === d.index));
    });
  }
  function clearFocus() { ribbons.classed("dim", false); group.classed("dim", false); }
}

// ── Chart 2 · flow matrix heatmap ────────────────────────────────────
function matrixChart(G) {
  const order = G.conf_order, n = order.length;
  const svg = setup("#matrix");
  const m = { top: 30, right: 20, bottom: 16, left: 92 };
  const size = Math.min(svg.h - m.top - m.bottom, svg.w - m.left - m.right);
  const cell = size / n;
  const g = svg.sel.append("g").attr("transform", `translate(${m.left},${m.top})`);

  const share = G.matrix.map(row => {
    const s = row.reduce((a, b) => a + b, 0);
    return row.map(v => v / s);
  });
  const color = d3.scaleSequential(d3.interpolate("#fbf3e6", "#b06a16")).domain([0, 1]);

  // column headers
  g.append("g").selectAll("text").data(order).join("text")
    .attr("class", "axis-label").attr("text-anchor", "middle")
    .attr("x", (d, i) => i * cell + cell / 2).attr("y", -10).text(d => d);
  // row headers
  g.append("g").selectAll("text").data(order).join("text")
    .attr("class", "axis-label").attr("text-anchor", "end")
    .attr("x", -10).attr("y", (d, i) => i * cell + cell / 2 + 4).text(d => d);

  const rows = g.selectAll("g.row").data(share).join("g")
    .attr("transform", (d, i) => `translate(0,${i * cell})`);
  rows.selectAll("rect").data((row, i) => row.map((v, j) => ({ v, i, j }))).join("rect")
    .attr("x", d => d.j * cell).attr("width", cell - 2).attr("height", cell - 2)
    .attr("rx", 3)
    .attr("fill", d => color(d.v))
    .attr("class", d => d.i === d.j ? "matrix-diag" : null)
    .on("mouseenter", (e, d) => showTip(
      `<b>${order[d.i]} → ${order[d.j]}</b>
       <div class="t-row"><span>share of ${order[d.i]}'s games</span><span>${pct(d.v)}</span></div>`))
    .on("mousemove", moveTip).on("mouseleave", hideTip);
  rows.selectAll("text").data((row, i) => row.map((v, j) => ({ v, i, j }))).join("text")
    .attr("class", "cell-label")
    .attr("x", d => d.j * cell + (cell - 2) / 2).attr("y", d => (cell - 2) / 2 + 4)
    .attr("text-anchor", "middle")
    .attr("fill", d => d.v > 0.5 ? "#fff" : "#9a8c79")
    .text(d => d.v >= 0.005 ? Math.round(d.v * 100) : "");
}

// ── Chart 3 · insularity bars ────────────────────────────────────────
function insularityChart(G) {
  const data = G.conf_order
    .map(c => ({ key: c, value: G.insularity[c], color: CONF[c].color }))
    .sort((a, b) => b.value - a.value);
  hBars("#insularity", data, { label: d => d.key, max: 1, fmt: pct, axisTitle: "share of games played at home" });
}

// shared horizontal-bar renderer
function hBars(sel, data, opt) {
  const svg = setup(sel);
  const m = { top: 8, right: 56, bottom: 30, left: 108 };
  const iw = svg.w - m.left - m.right, ih = svg.h - m.top - m.bottom;
  const g = svg.sel.append("g").attr("transform", `translate(${m.left},${m.top})`);
  const x = d3.scaleLinear().domain([0, opt.max]).range([0, iw]);
  const y = d3.scaleBand().domain(data.map(d => d.key)).range([0, ih]).padding(0.28);

  g.append("g").attr("transform", `translate(0,${ih})`)
    .call(d3.axisBottom(x).ticks(5).tickFormat(d => Math.round(d * 100) + "%").tickSize(-ih));
  g.append("text").attr("class", "axis-label")
    .attr("x", 0).attr("y", ih + 26).text(opt.axisTitle);

  const row = g.selectAll("g.row").data(data).join("g")
    .attr("transform", d => `translate(0,${y(d.key)})`);
  row.append("rect").attr("class", "bar-track")
    .attr("width", iw).attr("height", y.bandwidth()).attr("rx", 4);
  row.append("rect").attr("class", "bar")
    .attr("width", d => x(d.value)).attr("height", y.bandwidth()).attr("rx", 4)
    .attr("fill", d => d.color);
  row.append("text").attr("class", "axis-label").attr("text-anchor", "end")
    .attr("x", -10).attr("y", y.bandwidth() / 2 + 4)
    .style("fill", INK).style("font-family", "Space Grotesk").style("font-weight", 600)
    .text(opt.label);
  row.append("text").attr("class", "val-label")
    .attr("x", d => x(d.value) + 8).attr("y", y.bandwidth() / 2 + 4)
    .text(d => opt.fmt(d.value));
}

// ── Part II · globalization over time ────────────────────────────────
function temporalChart(G) {
  const t = G.temporal, svg = setup("#temporal");
  const m = { top: 18, right: 24, bottom: 34, left: 46 };
  const iw = svg.w - m.left - m.right, ih = svg.h - m.top - m.bottom;
  const g = svg.sel.append("g").attr("transform", `translate(${m.left},${m.top})`);

  // Scale to the decade trend (the signal); the noisy annual line is clipped to the plot.
  const yMax = d3.max(t.decades, d => d.cross) * 1.35;
  const x = d3.scaleLinear().domain([t.start_year, 2026]).range([0, iw]);
  const y = d3.scaleLinear().domain([0, yMax]).range([ih, 0]);

  svg.sel.append("clipPath").attr("id", "temporal-clip").append("rect")
    .attr("x", 0).attr("y", 0).attr("width", iw).attr("height", ih);

  g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(d => Math.round(d * 100) + "%").tickSize(-iw));
  g.append("g").attr("transform", `translate(0,${ih})`)
    .call(d3.axisBottom(x).tickFormat(d3.format("d")).ticks(7).tickSize(0));

  // faint annual signal (texture), clipped to the plotting area
  g.append("path").datum(t.annual).attr("fill", "none").attr("clip-path", "url(#temporal-clip)")
    .attr("stroke", "#d8cdbb").attr("stroke-width", 1)
    .attr("d", d3.line().x(d => x(d.year)).y(d => y(d.cross)).curve(d3.curveMonotoneX));

  // bold decade trend + area
  const area = d3.area().x(d => x(d.decade + 5)).y0(ih).y1(d => y(d.cross)).curve(d3.curveMonotoneX);
  const line = d3.line().x(d => x(d.decade + 5)).y(d => y(d.cross)).curve(d3.curveMonotoneX);
  g.append("path").datum(t.decades).attr("fill", "#b06a16").attr("opacity", 0.10).attr("d", area);
  g.append("path").datum(t.decades).attr("fill", "none")
    .attr("stroke", "#b06a16").attr("stroke-width", 2.5).attr("d", line);
  g.selectAll("circle.dec").data(t.decades).join("circle").attr("class", "dec")
    .attr("cx", d => x(d.decade + 5)).attr("cy", d => y(d.cross)).attr("r", 3.2)
    .attr("fill", "#b06a16")
    .on("mouseenter", (e, d) => showTip(
      `<b>${d.decade}s</b><div class="t-row"><span>cross-continental</span><span>${pct(d.cross)}</span></div>
       <div class="t-row"><span>games</span><span>${d.n.toLocaleString()}</span></div>`))
    .on("mousemove", moveTip).on("mouseleave", hideTip);

  // annotate peak + latest
  const mark = (d, text, dy) => {
    g.append("text").attr("class", "anno").attr("x", x(d.decade + 5)).attr("y", y(d.cross) + dy)
      .attr("text-anchor", "middle").text(text);
  };
  mark(t.peak, `${pct(t.peak.cross)} · ${t.peak.decade}s peak`, -12);
  mark(t.latest, `${pct(t.latest.cross)} today`, 22);
}

// ── Part III · small world + distribution ────────────────────────────
function smallWorldChart(G) {
  const sw = G.smallworld;
  d3.select("#sw-stats").html(`
    <div class="swc"><div class="n">${sw.avg_path}</div><div class="l">average matches between any two nations</div></div>
    <div class="swc"><div class="n">${sw.diameter}</div><div class="l">the two most distant teams, at most, apart</div></div>
    <div class="swc"><div class="n">${pct(sw.distribution.filter(d=>d.hops<=2).reduce((s,d)=>s+d.share,0))}</div><div class="l">of all team-pairs are within two matches</div></div>`);
  d3.select("#sw-cc").text(sw.clustering);
  d3.select("#sw-ccr").text(sw.rand_clustering);

  // single stacked horizontal bar of the path-length distribution
  const svg = setup("#smallworld");
  const m = { top: 26, right: 16, bottom: 8, left: 16 };
  const iw = svg.w - m.left - m.right, bh = 46;
  const g = svg.sel.append("g").attr("transform", `translate(${m.left},${m.top})`);
  const x = d3.scaleLinear().domain([0, 1]).range([0, iw]);
  const shades = ["#b06a16", "#c98a3e", "#d8a865", "#e6c79a"];
  let acc = 0;
  const segs = sw.distribution.map((d, i) => {
    const s = { ...d, x0: acc, color: shades[Math.min(i, shades.length - 1)] }; acc += d.share; return s;
  });
  g.selectAll("rect").data(segs).join("rect")
    .attr("x", d => x(d.x0)).attr("width", d => Math.max(0, x(d.share) - 1.5)).attr("height", bh).attr("rx", 3)
    .attr("fill", d => d.color);
  g.selectAll("text.seg").data(segs.filter(d => d.share > 0.04)).join("text").attr("class", "seg-label")
    .attr("x", d => x(d.x0) + (x(d.share)) / 2).attr("y", bh / 2 + 5).attr("text-anchor", "middle")
    .attr("fill", d => d.hops <= 2 ? "#fff" : "#7a6e63").text(d => pct(d.share));
  g.selectAll("text.cap").data(segs.filter(d => d.share > 0.04)).join("text").attr("class", "seg-cap")
    .attr("x", d => x(d.x0) + (x(d.share)) / 2).attr("y", -8).attr("text-anchor", "middle")
    .text(d => d.hops === 1 ? "direct opponents" : `${d.hops} matches apart`);
}

// ── Part III · interactive connector (BFS in-browser) ────────────────
function buildConnector(A) {
  const teams = Object.keys(A.adjacency).sort();
  const from = d3.select("#conn-from"), to = d3.select("#conn-to");
  for (const sel of [from, to]) {
    sel.selectAll("option").data(teams).join("option").attr("value", d => d).text(d => d);
  }
  from.property("value", teams.includes("Vanuatu") ? "Vanuatu" : teams[0]);
  to.property("value", teams.includes("San Marino") ? "San Marino" : teams[teams.length - 1]);

  function bfs(a, b) {
    if (a === b) return [a];
    const prev = { [a]: null }, q = [a];
    while (q.length) {
      const u = q.shift();
      for (const v of A.adjacency[u] || []) {
        if (!(v in prev)) {
          prev[v] = u;
          if (v === b) {
            const path = [v]; let c = u;
            while (c !== null) { path.unshift(c); c = prev[c]; }
            return path;
          }
          q.push(v);
        }
      }
    }
    return null;
  }

  function render() {
    const a = from.property("value"), b = to.property("value");
    const path = bfs(a, b);
    const box = d3.select("#conn-result").html("");
    if (!path) { box.append("p").attr("class", "conn-msg").text("No chain found."); return; }
    const hops = path.length - 1;
    box.append("p").attr("class", "conn-msg")
      .html(hops === 0 ? "Same team." :
        `Connected in <strong>${hops}</strong> ${hops === 1 ? "match" : "matches"}.`);
    const chain = box.append("div").attr("class", "chain");
    path.forEach((t, i) => {
      const c = (CONF[A.conf[t]] || { color: "#bcae9c" }).color;
      chain.append("span").attr("class", "chip").style("border-color", c)
        .style("background", d3.color(c).copy({ opacity: 0.12 }))
        .html(`<span class="chip-dot" style="background:${c}"></span>${t}`);
      if (i < path.length - 1) chain.append("span").attr("class", "chain-link").text("played");
    });
  }
  from.on("change", render); to.on("change", render);
  render();
}

// ── Part IV · centrality: brokers vs travelers ───────────────────────
function centralityChart(G) {
  const data = G.centrality.betweenness;
  const svg = setup("#centrality");
  const m = { top: 18, right: 26, bottom: 44, left: 56 };
  const iw = svg.w - m.left - m.right, ih = svg.h - m.top - m.bottom;
  const g = svg.sel.append("g").attr("transform", `translate(${m.left},${m.top})`);

  const x = d3.scaleLinear().domain([0, d3.max(data, d => d.cross) * 1.12]).range([0, iw]);
  const y = d3.scaleLinear().domain([0, d3.max(data, d => d.score) * 1.12]).range([ih, 0]);

  g.append("g").call(d3.axisLeft(y).ticks(5).tickSize(-iw));
  g.append("g").attr("transform", `translate(0,${ih})`)
    .call(d3.axisBottom(x).ticks(6).tickFormat(d => Math.round(d * 100) + "%").tickSize(-ih));
  g.append("text").attr("class", "axis-label").attr("x", iw).attr("y", ih + 34).attr("text-anchor", "end")
    .text("→ travels more (cross-continental share)");
  g.append("text").attr("class", "axis-label").attr("transform", "rotate(-90)")
    .attr("x", 0).attr("y", -42).attr("text-anchor", "end").text("→ brokers more (betweenness)");

  g.selectAll("circle").data(data).join("circle")
    .attr("cx", d => x(d.cross)).attr("cy", d => y(d.score)).attr("r", 6)
    .attr("fill", d => CONF[d.conf].color).attr("stroke", "#fff").attr("stroke-width", 1.2)
    .on("mouseenter", (e, d) => showTip(
      `<b>${d.team}</b> <span class="t-sub">${d.conf}</span>
       <div class="t-row"><span>betweenness</span><span>${d.score}</span></div>
       <div class="t-row"><span>plays abroad</span><span>${pct(d.cross)}</span></div>`))
    .on("mousemove", moveTip).on("mouseleave", hideTip);
  // Label only the spread-out, notable points (top brokers + the travelers); the dense
  // CONCACAF cluster stays hover-only so labels don't collide.
  g.selectAll("text.lab").data(data.filter((d, i) => i < 3 || d.cross > 0.40)).join("text")
    .attr("class", "scatter-label")
    .attr("x", d => x(d.cross) + 9).attr("y", d => y(d.score) + 4).text(d => d.team);
}

// ── Part V · nested structure sunburst ───────────────────────────────
function sunburstChart(G) {
  const svg = setup("#sunburst");
  const R = Math.min(svg.w, svg.h) / 2 - 6;
  const g = svg.sel.append("g").attr("transform", `translate(${svg.w / 2},${svg.h / 2})`);

  const byConf = {};
  G.nested.forEach(s => (byConf[s.conf] ||= []).push(s));
  const root = {
    name: "world",
    children: G.conf_order.filter(c => byConf[c]).map(c => ({
      name: c, conf: c,
      children: byConf[c].map(s => ({ name: s.label, conf: c, value: s.size, members: s.members })),
    })),
  };
  const h = d3.hierarchy(root).sum(d => d.value).sort((a, b) => b.value - a.value);
  d3.partition().size([2 * Math.PI, R])(h);

  const arc = d3.arc().startAngle(d => d.x0).endAngle(d => d.x1)
    .innerRadius(d => d.y0).outerRadius(d => d.y1 - 1.5).padAngle(0.006).padRadius(R / 2);

  g.selectAll("path").data(h.descendants().filter(d => d.depth)).join("path")
    .attr("d", arc)
    .attr("fill", d => {
      const base = d3.color(CONF[d.data.conf].color);
      return d.depth === 1 ? base : base.brighter(0.9);
    })
    .attr("stroke", "#fffdfa").attr("stroke-width", 1)
    .on("mouseenter", (e, d) => showTip(
      d.depth === 1
        ? `<b>${d.data.name}</b><div class="t-row"><span>teams</span><span>${d.value}</span></div>`
        : `<b>${d.data.name}</b> <span class="t-sub">${d.data.conf}</span>
           <div class="t-row"><span>${d.data.members.length} teams</span></div>
           <div class="t-mem">${d.data.members.slice(0, 12).join(", ")}${d.data.members.length > 12 ? "…" : ""}</div>`))
    .on("mousemove", moveTip).on("mouseleave", hideTip);

  const labelTransform = d => {
    const a = (d.x0 + d.x1) / 2, r = (d.y0 + d.y1) / 2;
    return `rotate(${a * 180 / Math.PI - 90}) translate(${r},0) rotate(${a > Math.PI ? 180 : 0})`;
  };
  // outer ring: sub-region names on the wider wedges
  g.selectAll("text.sub").data(h.descendants().filter(d => d.depth === 2 && (d.x1 - d.x0) > 0.16))
    .join("text").attr("class", "sun-label")
    .attr("transform", labelTransform).attr("text-anchor", "middle").attr("dy", "0.32em")
    .text(d => d.data.name);
  // inner ring: confederation codes
  g.selectAll("text.inner").data(h.descendants().filter(d => d.depth === 1 && (d.x1 - d.x0) > 0.12))
    .join("text").attr("class", "sun-label-inner")
    .attr("transform", labelTransform).attr("text-anchor", "middle").attr("dy", "0.32em")
    .text(d => d.data.name);
}

// ── Part VI · robustness (targeted vs random removal) ────────────────
function robustnessChart(G) {
  const r = G.robustness;
  d3.select("#rob-stats").html(`
    <div class="swc"><div class="n">${pct(r.top10_link_loss)}</div><div class="l">of all cross-continental links gone after removing just the top 10 brokers</div></div>
    <div class="swc"><div class="n">${(r.lcc_min * 100).toFixed(0)}%</div><div class="l">of teams stay in one connected graph even after ${r.kmax} removals — it never splits</div></div>
    <div class="swc"><div class="n">${pct(r.reach_retained_kmax)}</div><div class="l">of cross-continental reachability survives all ${r.kmax} removals</div></div>`);

  const svg = setup("#robustness");
  const m = { top: 16, right: 116, bottom: 36, left: 46 };
  const iw = svg.w - m.left - m.right, ih = svg.h - m.top - m.bottom;
  const g = svg.sel.append("g").attr("transform", `translate(${m.left},${m.top})`);
  const x = d3.scaleLinear().domain([0, r.kmax]).range([0, iw]);
  const y = d3.scaleLinear().domain([0.3, 1]).range([ih, 0]);

  g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(d => Math.round(d * 100) + "%").tickSize(-iw));
  g.append("g").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x).ticks(8).tickSize(0));
  g.append("text").attr("class", "axis-label").attr("x", iw).attr("y", ih + 32).attr("text-anchor", "end")
    .text("broker teams removed →");

  const line = key => d3.line().x((d, i) => x(i)).y(d => y(d)).curve(d3.curveMonotoneX);
  const series = [
    { data: r.random, color: "#9a8c79", label: "random removal", dash: "4 3" },
    { data: r.targeted, color: "#b06a16", label: "targeted (brokers first)", dash: null },
  ];
  series.forEach(s => {
    g.append("path").datum(s.data).attr("fill", "none").attr("stroke", s.color)
      .attr("stroke-width", 2.5).attr("stroke-dasharray", s.dash).attr("d", line());
    g.append("text").attr("class", "series-label").attr("x", iw + 8).attr("y", y(s.data[s.data.length - 1]) + 4)
      .attr("fill", s.color).text(s.label);
  });
  // gap shading between the two curves
  g.append("path").datum(r.targeted.map((t, i) => ({ i, t, r: r.random[i] })))
    .attr("fill", "#b06a16").attr("opacity", 0.08)
    .attr("d", d3.area().x(d => x(d.i)).y0(d => y(d.r)).y1(d => y(d.t)).curve(d3.curveMonotoneX));
}

// ── helpers ──────────────────────────────────────────────────────────
function setup(sel) {
  const node = d3.select(sel);
  node.selectAll("*").remove();
  const { width, height } = node.node().getBoundingClientRect();
  node.attr("viewBox", [0, 0, width, height]);
  return { sel: node, w: width, h: height };
}
function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
