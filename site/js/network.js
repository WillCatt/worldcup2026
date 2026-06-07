// Interactive force-directed graph of the international football match network.
// Reads site/data/network.json (exported by notebooks/01_network.py) and force-directs
// it in the browser — drag, hover, recolour, filter. The layout is live, not baked.

const CONF_COLORS = {
  UEFA: "#b06a16", CONMEBOL: "#2a8f8f", CONCACAF: "#4a6d8c",
  CAF: "#3a8f57", AFC: "#c0533b", OFC: "#7d5ba6", "??": "#bcae9c",
};
const COMMUNITY_COLORS = ["#b06a16", "#2a8f8f", "#4a6d8c", "#3a8f57", "#c0533b", "#7d5ba6", "#9c6b4e"];

const INK = "#1a1714", AMBER = "#b06a16", FAINT = "#d8cdbb";

d3.json("data/network.json").then(draw);

function draw(graph) {
  fillCopy(graph);

  const svg = d3.select("#graph");
  const { width, height } = svg.node().getBoundingClientRect();
  svg.attr("viewBox", [0, 0, width, height]);

  const maxPR = d3.max(graph.nodes, d => d.pagerank);
  const rOf = d => 3 + 22 * Math.sqrt(d.pagerank / maxPR);
  const maxW = d3.max(graph.links, d => d.weight);
  const bridges = new Set(graph.metrics.bridges);

  // Gentle per-confederation grouping so the blocs separate visibly.
  const order = graph.conf_order;
  const R = Math.min(width, height) * 0.34;
  const target = {};
  order.forEach((c, i) => {
    const a = (i / order.length) * 2 * Math.PI - Math.PI / 2;
    target[c] = [width / 2 + R * Math.cos(a), height / 2 + R * Math.sin(a)];
  });
  const tx = d => (target[d.conf] || [width / 2, height / 2])[0];
  const ty = d => (target[d.conf] || [width / 2, height / 2])[1];

  const sim = d3.forceSimulation(graph.nodes)
    .force("link", d3.forceLink(graph.links).id(d => d.id)
      .distance(26).strength(d => 0.04 + 0.5 * (d.weight / maxW)))
    .force("charge", d3.forceManyBody().strength(-26))
    .force("x", d3.forceX(tx).strength(0.10))
    .force("y", d3.forceY(ty).strength(0.10))
    .force("collide", d3.forceCollide(d => rOf(d) + 1.5));

  const g = svg.append("g");

  const link = g.append("g").attr("fill", "none")
    .selectAll("line").data(graph.links).join("line")
    .attr("class", d => "link" + (d.cross ? " cross" : " within"))
    .attr("stroke", d => d.cross ? AMBER : FAINT)
    .attr("stroke-width", d => d.cross ? 0.5 : 0.4)
    .attr("stroke-opacity", d => d.cross ? 0.30 : 0.45);

  const node = g.append("g").attr("stroke", INK).attr("stroke-width", 0.5)
    .selectAll("circle").data(graph.nodes).join("circle")
    .attr("class", "node").attr("r", rOf)
    .attr("fill", d => CONF_COLORS[d.conf])
    .call(drag(sim))
    .on("pointerenter", hover).on("pointermove", move).on("pointerleave", leave);

  // Label the strongest + the bridge teams (graph.nodes is sorted by PageRank).
  const labelled = new Set([...graph.nodes.slice(0, 14).map(d => d.id), ...bridges]);
  const label = g.append("g").selectAll("text")
    .data(graph.nodes.filter(d => labelled.has(d.id))).join("text")
    .attr("class", "label").attr("dx", d => rOf(d) + 2).attr("dy", 3)
    .text(d => d.id);

  sim.on("tick", () => {
    link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    node.attr("cx", d => d.x).attr("cy", d => d.y);
    label.attr("x", d => d.x).attr("y", d => d.y);
  });

  // ── interactions ───────────────────────────────────────────────
  let mode = "conf", spotlight = false;
  const rank = new Map(graph.nodes.map((d, i) => [d.id, i + 1]));

  function recolour() {
    node.attr("fill", d => mode === "conf"
      ? CONF_COLORS[d.conf]
      : COMMUNITY_COLORS[d.community % COMMUNITY_COLORS.length]);
    buildLegend(mode, graph, COMMUNITY_COLORS);
  }

  d3.select("#colour-by").selectAll("button").on("click", function () {
    d3.select("#colour-by").selectAll("button").classed("active", false);
    d3.select(this).classed("active", true);
    mode = this.dataset.mode;
    recolour();
  });

  d3.select("#cross-only").on("change", function () {
    link.filter(d => !d.cross).attr("display", this.checked ? "none" : null);
  });

  d3.select("#bridges-btn").on("click", function () {
    spotlight = !spotlight;
    d3.select(this).classed("active", spotlight);
    node.classed("faded", d => spotlight && !bridges.has(d.id));
    label.classed("faded", d => spotlight && !bridges.has(d.id));
    link.classed("faded", d => spotlight &&
      !(bridges.has(d.source.id) || bridges.has(d.target.id)));
  });

  const tip = d3.select("#tooltip");
  function hover(event, d) {
    node.classed("faded", n => n !== d && !connected(d, n, graph));
    link.classed("faded", l => l.source !== d && l.target !== d);
    label.classed("faded", n => n !== d && !connected(d, n, graph));
    tip.attr("hidden", null).html(
      `<b>${d.id}</b> <span class="t-conf">${d.conf}</span>
       <div class="t-row"><span>PageRank</span><span>#${rank.get(d.id)}</span></div>
       <div class="t-row"><span>Cross-continental games</span><span>${Math.round(d.cross * 100)}%</span></div>
       <div class="t-row"><span>Opponents</span><span>${d.degree}</span></div>`);
  }
  function move(event) {
    const [x, y] = d3.pointer(event, svg.node());
    tip.style("left", x + "px").style("top", y + "px");
  }
  function leave() {
    if (!spotlight) { node.classed("faded", false); label.classed("faded", false); }
    link.classed("faded", l => spotlight &&
      !(bridges.has(l.source.id) || bridges.has(l.target.id)));
    tip.attr("hidden", true);
  }

  buildLegend(mode, graph, COMMUNITY_COLORS);
}

function connected(a, b, graph) {
  return graph.links.some(l =>
    (l.source === a && l.target === b) || (l.source === b && l.target === a));
}

function drag(sim) {
  return d3.drag()
    .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
    .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
    .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; });
}

function buildLegend(mode, graph, communityColors) {
  const wrap = d3.select("#legend").html("");
  if (mode === "conf") {
    graph.conf_order.forEach(c => {
      const row = wrap.append("div").attr("class", "row");
      row.append("span").attr("class", "dot").style("background", CONF_COLORS[c]);
      row.append("span").text(c);
    });
    const row = wrap.append("div").attr("class", "row");
    row.append("span").attr("class", "dot").style("background", "#b06a16").style("opacity", .5);
    row.append("span").text("cross-continental game");
  } else {
    const n = graph.metrics.n_communities;
    d3.range(n).forEach(i => {
      const row = wrap.append("div").attr("class", "row");
      row.append("span").attr("class", "dot").style("background", communityColors[i % communityColors.length]);
      row.append("span").text("community " + (i + 1));
    });
  }
}

function fillCopy(graph) {
  const m = graph.metrics;
  const pct = x => Math.round(x * 100) + "%";
  d3.select("#stats").html(`
    <div class="stat"><div class="num">${pct(m.within_share)}</div>
      <div class="lbl">of matches stay within a team's own confederation</div></div>
    <div class="stat"><div class="num">${m.nmi.toFixed(2)}</div>
      <div class="lbl">NMI — how well continents emerge from the graph alone</div></div>
    <div class="stat"><div class="num">${m.n_communities} / 6</div>
      <div class="lbl">communities detected vs real confederations (the Americas merge)</div></div>`);
  d3.select("#f-within").text(pct(m.within_share));
  d3.select("#f-nmi").text(m.nmi.toFixed(2));
  d3.select("#f-bridges").text(m.bridges.slice(0, 5).join(", "));
}
