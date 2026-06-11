/* Penalty Geometry & Game Theory — hub piece.
   Standalone page: fetch one static penalties.json and hand-draw the cold open,
   four acts and the keeper game in D3, in the hub palette. No build step. */
(function () {
  "use strict";

  var GOAL_W = 7.32, GOAL_H = 2.44, THIRD = GOAL_W / 6;
  var INK = "#1a1714", MUTED = "#7a6e63", LINE = "#e6ded2", AMBER = "#b06a16",
      RED = "#c0533b", TEAL = "#2a8f8f", GREY = "#cdbfae", PANEL = "#fffdfa";
  var HEAT = ["#faf8f4", "#f2dcae", "#e8c98f", "#d39a3f", "#b06a16", "#7a430b", "#5e2f0c"];

  // ── pure game logic (also node-exportable) ──────────────────────────────
  function sideOf(x) { return Math.abs(x) <= THIRD ? "centre" : (x > 0 ? "right" : "left"); }
  function diveTarget(d) { return { left: { x: -1.6, z: 0.8 }, centre: { x: 0, z: 0.9 }, right: { x: 1.6, z: 0.8 } }[d]; }
  function resolveKick(kick, dive, p) {
    if (!kick.on) return { goal: false, saved: false, reason: "off target" };
    var side = sideOf(kick.x);
    if (side !== dive) return { goal: true, saved: false, reason: "wrong way" };
    var t = diveTarget(dive), dist = Math.hypot(kick.x - t.x, kick.z - t.z);
    var base = dive === "centre" ? p.reach_centre : p.reach_side;
    var eff = kick.z > 1.4 ? base * p.reach_high_penalty : base;
    var saved = dist <= eff;
    return { goal: !saved, saved: saved, reason: saved ? "saved" : "beaten in the corner" };
  }
  function pureSaveRate(kicks, dive, p) {
    if (!kicks.length) return 0;
    var s = 0; for (var i = 0; i < kicks.length; i++) if (resolveKick(kicks[i], dive, p).saved) s++;
    return s / kicks.length;
  }
  function optimalSaveRate(kicks, p) {
    return Math.max(pureSaveRate(kicks, "left", p), pureSaveRate(kicks, "centre", p), pureSaveRate(kicks, "right", p));
  }
  if (typeof document === "undefined") {
    module.exports = { sideOf: sideOf, diveTarget: diveTarget, resolveKick: resolveKick, pureSaveRate: pureSaveRate, optimalSaveRate: optimalSaveRate };
    return;
  }

  var pct = function (x, d) { return x == null || isNaN(x) ? "—" : (100 * x).toFixed(d || 0) + "%"; };
  function heatColor(t) {
    t = Math.max(0, Math.min(1, t));
    var n = HEAT.length - 1, i = Math.floor(t * n), f = t * n - i;
    return i >= n ? HEAT[n] : d3.interpolateRgb(HEAT[i], HEAT[i + 1])(f);
  }

  // ── reusable goal mouth at true 7.32×2.44 aspect ────────────────────────
  function buildGoal(svgSel, m) {
    m = m || 58;
    var padX = 0.62, padTop = 0.55, padBot = 0.5;
    var domX = [-GOAL_W / 2 - padX, GOAL_W / 2 + padX], domZ = [0, GOAL_H + padTop];
    var W = (domX[1] - domX[0]) * m, H = (domZ[1] - domZ[0]) * m + padBot * m;
    svgSel.attr("viewBox", "0 0 " + W + " " + H).attr("preserveAspectRatio", "xMidYMid meet").attr("height", H);
    var sx = d3.scaleLinear().domain(domX).range([0, W]);
    var sz = d3.scaleLinear().domain(domZ).range([domZ[1] * m, 0]);
    var groundY = sz(0);
    var heat = svgSel.append("g"), dots = svgSel.append("g"), frame = svgSel.append("g");
    var lx = sx(-GOAL_W / 2), rx = sx(GOAL_W / 2), ty = sz(GOAL_H);
    for (var gx = -GOAL_W / 2; gx <= GOAL_W / 2 + 1e-6; gx += GOAL_W / 14)
      frame.append("line").attr("class", "pen-net").attr("x1", sx(gx)).attr("x2", sx(gx)).attr("y1", ty).attr("y2", groundY);
    for (var gz = 0; gz <= GOAL_H + 1e-6; gz += GOAL_H / 6)
      frame.append("line").attr("class", "pen-net").attr("x1", lx).attr("x2", rx).attr("y1", sz(gz)).attr("y2", sz(gz));
    frame.append("path").attr("class", "pen-post").attr("d", "M" + lx + "," + groundY + " L" + lx + "," + ty + " L" + rx + "," + ty + " L" + rx + "," + groundY);
    frame.append("line").attr("class", "pen-ground").attr("x1", sx(domX[0])).attr("x2", sx(domX[1])).attr("y1", groundY).attr("y2", groundY);
    return { sx: sx, sz: sz, heat: heat, dots: dots, groundY: groundY, W: W, H: H };
  }

  function drawHeat(G, kde, key) {
    var grid = kde.grids[key]; G.heat.selectAll("*").remove();
    if (!grid) return;
    var gx = kde.gx, gz = kde.gz, dx = gx[1] - gx[0], dz = gz[1] - gz[0], cells = [];
    for (var j = 0; j < gz.length; j++) for (var i = 0; i < gx.length; i++) {
      var v = grid[j][i]; if (v > 0.04) cells.push({ x: gx[i], z: gz[j], v: v });
    }
    G.heat.selectAll("rect").data(cells).enter().append("rect")
      .attr("x", function (d) { return G.sx(d.x - dx / 2); })
      .attr("y", function (d) { return G.sz(d.z + dz / 2); })
      .attr("width", Math.abs(G.sx(dx) - G.sx(0)) + 0.6)
      .attr("height", Math.abs(G.sz(dz) - G.sz(0)) + 0.6)
      .attr("fill", function (d) { return heatColor(d.v); })
      .attr("opacity", function (d) { return 0.25 + 0.7 * d.v; });
  }

  // ── number placeholders in captions / footer ────────────────────────────
  function fillPlaceholders(B) {
    var m = B.meta, gt = B.game_theory.all, z = gt.zones;
    function ci(zz) { return "[" + pct(zz.lo) + ", " + pct(zz.hi) + "]"; }
    var vals = {
      n_total: m.n_total, n_shootout: m.n_shootout, n_world_cup: m.n_world_cup,
      n_competitions: m.n_competitions, overall_conv: pct(m.overall_conv), dive_coverage: pct(m.dive_coverage)
    };
    document.querySelectorAll("[data-pen]").forEach(function (el) {
      var k = el.getAttribute("data-pen"); if (vals[k] != null) el.textContent = vals[k];
    });
  }

  function fillStats(B) {
    var m = B.meta, s = d3.select("#stats");
    var cards = [
      { n: m.n_total.toLocaleString(), l: "penalty kicks analysed" },
      { n: m.n_shootout, l: "of them in shootouts" },
      { n: pct(m.dive_coverage), l: "of dives even recoverable" }
    ];
    cards.forEach(function (c) {
      var d = s.append("div").attr("class", "stat");
      d.append("div").attr("class", "num").html(c.n);
      d.append("div").attr("class", "lbl").text(c.l);
    });
  }

  // ── cold open ───────────────────────────────────────────────────────────
  function coldOpen(B) {
    var c = B.cold_open, G = buildGoal(d3.select("#coldopen"), 54);
    G.dots.append("circle").attr("cx", G.sx(c.x_m)).attr("cy", G.sz(c.z_m)).attr("r", 9)
      .attr("fill", c.outcome === "Goal" ? RED : TEAL).attr("stroke", "#fff").attr("stroke-width", 1.5);
    var kx = G.sx(0), ky = G.groundY;
    G.dots.append("rect").attr("x", kx - 9).attr("y", ky - 46).attr("width", 18).attr("height", 40)
      .attr("rx", 7).attr("fill", "none").attr("stroke", MUTED).attr("stroke-width", 2);
    G.dots.append("text").attr("x", kx).attr("y", ky - 52).attr("text-anchor", "middle")
      .attr("class", "pen-axlabel").text(c.keeper_contact ? "keeper got a touch" : "keeper: dive unseen");
    d3.select("#cold-cap").html("<strong>" + (c.player || "A penalty") + "</strong>, " + c.competition + " " +
      c.season + " — placed " + cornerWords(c) + ". The interpretable model gives a kick to that spot a <strong>" +
      pct(c.p_goal_model) + "</strong> chance of scoring. Result: <strong>" + c.outcome + "</strong>. Now zoom out to all " +
      B.meta.n_total.toLocaleString() + " of them.");
  }
  function cornerWords(c) {
    if (Math.abs(c.x_m) <= 1.2) return (c.z_m > 1.4 ? "high" : "low") + " and down the middle";
    return "into the " + (c.z_m > 1.4 ? "top" : "bottom") + " " + (c.x_m > 0 ? "right" : "left") + " corner";
  }

  // ── Act 1: KDE + toggles ────────────────────────────────────────────────
  function act1(B) {
    var G = buildGoal(d3.select("#kde"), 56);
    var note = d3.select("#kde-note"), ctl = d3.select("#kde-controls");
    var state = { foot: "all", phase: "all", layer: "all" };
    function seg(label, key, opts) {
      var g = ctl.append("div").attr("class", "pen-grp");
      g.append("span").attr("class", "glbl").text(label);
      opts.forEach(function (o) {
        g.append("button").attr("class", "pen-seg" + (state[key] === o.v ? " on" : "")).text(o.t)
          .on("click", function () { state[key] = o.v; g.selectAll("button").classed("on", false); d3.select(this).classed("on", true); redraw(); });
      });
    }
    seg("layer", "layer", [{ t: "all", v: "all" }, { t: "scored", v: "scored" }, { t: "saved", v: "saved" }, { t: "missed", v: "missed" }]);
    seg("phase", "phase", [{ t: "all", v: "all" }, { t: "open play", v: "ingame" }, { t: "shootout", v: "shootout" }]);
    seg("foot", "foot", [{ t: "all", v: "all" }, { t: "right", v: "R" }, { t: "left", v: "L" }]);
    function redraw() {
      var key = state.foot + "|" + state.phase + "|" + state.layer;
      drawHeat(G, B.kde, key);
      var n = (B.kde.counts && B.kde.counts[key]) || 0;
      note.html(annot(state, n));
    }
    function annot(st, n) {
      var base = "<b>n = " + n + "</b> kicks in this cut. ";
      if (n < 25) return base + "Thin slice — read the shape, not the detail.";
      if (st.layer === "saved") return base + "Saves cluster low and central: the reachable balls.";
      if (st.layer === "missed") return base + "Misses spray high and wide — the price of aiming for the frame.";
      if (st.layer === "scored") return base + "Goals hug the side-netting where no keeper reaches.";
      return base + "Two warm lobes by the posts, a cold hole in the middle.";
    }
    redraw();
  }

  // ── Act 2: dive bars ────────────────────────────────────────────────────
  function act2(B) {
    var pl = B.game.placements;
    function zoneAll(x) { return Math.abs(x) <= THIRD ? "centre" : (x > 0 ? "right" : "left"); }
    var order = ["left", "centre", "right"], lbl = { left: "keeper left", centre: "centre", right: "keeper right" };
    var shot = { left: 0, centre: 0, right: 0 }, n = 0, dive = { left: 0, centre: 0, right: 0 }, nd = 0;
    pl.forEach(function (k) { if (k.on) { shot[zoneAll(k.x)]++; n++; if (!k.scored) { dive[zoneAll(k.x)]++; nd++; } } });
    var data = order.map(function (z) { return { z: z, lbl: lbl[z], shot: n ? shot[z] / n : 0, dive: nd ? dive[z] / nd : 0 }; });
    var W = 560, H = 230, mL = 70, mB = 30, mT = 26, mR = 10;
    var svg = d3.select("#dive").append("svg").attr("viewBox", "0 0 " + W + " " + H).attr("height", H);
    var x0 = d3.scaleBand().domain(order).range([mL, W - mR]).padding(0.25);
    var x1 = d3.scaleBand().domain(["shot", "dive"]).range([0, x0.bandwidth()]).padding(0.1);
    var y = d3.scaleLinear().domain([0, 0.6]).range([H - mB, mT]);
    [0, 0.2, 0.4, 0.6].forEach(function (t) {
      svg.append("line").attr("x1", mL).attr("x2", W - mR).attr("y1", y(t)).attr("y2", y(t)).attr("stroke", LINE);
      svg.append("text").attr("x", mL - 8).attr("y", y(t) + 3).attr("text-anchor", "end").attr("class", "pen-axlabel").text(pct(t));
    });
    var col = { shot: GREY, dive: AMBER };
    data.forEach(function (d) {
      ["shot", "dive"].forEach(function (k) {
        svg.append("rect").attr("x", x0(d.z) + x1(k)).attr("width", x1.bandwidth())
          .attr("y", y(d[k])).attr("height", y(0) - y(d[k])).attr("fill", col[k]);
      });
      svg.append("text").attr("x", x0(d.z) + x0.bandwidth() / 2).attr("y", H - 10).attr("text-anchor", "middle").attr("class", "pen-axlabel").text(d.lbl);
    });
    svg.append("rect").attr("x", mL).attr("y", mT - 16).attr("width", 10).attr("height", 10).attr("fill", GREY);
    svg.append("text").attr("x", mL + 14).attr("y", mT - 7).attr("class", "pen-axlabel").text("all shots (n=" + n + ")");
    svg.append("rect").attr("x", mL + 150).attr("y", mT - 16).attr("width", 10).attr("height", 10).attr("fill", AMBER);
    svg.append("text").attr("x", mL + 164).attr("y", mT - 7).attr("class", "pen-axlabel").text("observable dives (n=" + nd + ")");
  }

  // ── Act 3: Nash table ───────────────────────────────────────────────────
  function act3(B) {
    var gt = B.game_theory.all, tb = B.game_theory.textbook_2x2, tbody = d3.select("#nash tbody");
    [["natural", "natural side"], ["centre", "dead centre"], ["cross", "across body"]].forEach(function (zz) {
      var z = gt.zones[zz[0]], hi = zz[0] === gt.best_zone;
      tbody.append("tr").attr("class", hi ? "hi" : "").html(
        "<td>" + zz[1] + "</td><td>" + z.n + "</td><td>" + pct(z.conv) + "</td>" +
        "<td class='ci'>[" + pct(z.lo) + ", " + pct(z.hi) + "]</td><td>" + pct(z.usage) + "</td>");
    });
    d3.select("#nash-verdict").html("<b>Verdict.</b> " + nashVerdict(gt));
    d3.select("#nash-cap").html("For the curious — the textbook 2×2 has a mixed equilibrium: the shooter goes natural <strong>" +
      pct(tb.nash_shooter_natural) + "</strong>, the keeper dives natural <strong>" + pct(tb.nash_keeper_natural) +
      "</strong>, for a scoring rate near <strong>" + pct(tb.value) + "</strong>. Building that from this data would need the keeper's dive on every kick — which, per Act II, we don't have.");
    d3.select("#nash-take").text(nashTakeaway(gt));
  }
  function nashVerdict(gt) {
    var p = gt.chisq_equal_success ? gt.chisq_equal_success.p : NaN, gap = gt.exploitability_gap_pp;
    if (isNaN(p)) return "Too few kicks per zone to test equilibrium honestly.";
    if (p >= 0.05) return "Conversion is statistically indistinguishable across the placement zones takers use (chi-square p = " +
      p.toFixed(2) + "). That is exactly what equilibrium play predicts — a null worth printing proudly. With only " +
      gt.n + " kicks, though, this test could also be too weak to catch a real gap.";
    return "Conversion differs across zones (chi-square p = " + p.toFixed(2) + "): the " + gt.best_zone +
      " zone out-converts the " + gt.worst_zone + " by about " + (gap == null ? "—" : gap.toFixed(0)) +
      " percentage points, yet stays under-used — an exploitable gap.";
  }
  function nashTakeaway(gt) {
    var p = gt.chisq_equal_success ? gt.chisq_equal_success.p : NaN;
    if (isNaN(p) || p >= 0.05) return "On the evidence we have, shooters look roughly like equilibrium players — no zone is obviously being left on the table.";
    return "Shooters appear to under-use their best-converting zone — a small edge they're leaving on the table.";
  }

  // ── the game ────────────────────────────────────────────────────────────
  function buildGame(B) {
    var g = B.game, p = { reach_side: g.reach_side, reach_centre: g.reach_centre, reach_high_penalty: g.reach_high_penalty };
    var onTarget = g.placements.filter(function (k) { return k.on; });
    var optimal = optimalSaveRate(onTarget, p), realRate = g.real_keeper_save_rate;
    var box = d3.select("#game"); box.html("");
    var head = box.append("div").attr("class", "pen-game-head");
    head.append("div").html("Kick <span class='kno'>1</span> of 5");
    var pips = head.append("div").attr("class", "pen-pips");
    var savesEl = head.append("div").attr("class", "saves").text("0 saves");
    var goalwrap = box.append("div").attr("class", "pen-goalwrap");
    var G = buildGoal(goalwrap.append("svg"), 52);
    var result = box.append("div").attr("class", "pen-game-result").html("Choose a side to dive.");
    var controls = box.append("div").attr("class", "pen-dives");
    var st = { i: 0, saves: 0, dives: [], deck: [] };
    for (var k = 0; k < 5; k++) st.deck.push(onTarget[Math.floor(Math.random() * onTarget.length)]);
    for (var pi = 0; pi < 5; pi++) pips.append("div").attr("class", "pen-pip");
    [["← Left", "left"], ["Centre", "centre"], ["Right →", "right"]].forEach(function (b) {
      controls.append("button").attr("class", "pen-dive").text(b[0]).on("click", function () { play(b[1]); });
    });
    function play(dive) {
      if (st.i >= 5) return;
      var kick = st.deck[st.i], res = resolveKick(kick, dive, p);
      st.dives.push(dive); if (res.saved) st.saves++;
      G.dots.selectAll("*").remove();
      var t = diveTarget(dive);
      G.dots.append("circle").attr("cx", G.sx(t.x)).attr("cy", G.sz(t.z)).attr("r", 16).attr("fill", "none").attr("stroke", MUTED).attr("stroke-width", 2).attr("opacity", 0.6);
      G.dots.append("circle").attr("cx", G.sx(kick.x)).attr("cy", G.sz(kick.z)).attr("r", 8).attr("fill", res.saved ? TEAL : RED).attr("stroke", "#fff").attr("stroke-width", 1.5);
      pips.selectAll(".pen-pip").filter(function (d, idx) { return idx === st.i; }).classed(res.saved ? "save" : "goal", true);
      result.html(res.saved ? "<b>Saved!</b> You got across to it." : (res.reason === "wrong way" ? "<b>Goal.</b> Wrong way — it went the other side." : "<b>Goal.</b> Right side, but it found the corner."));
      savesEl.text(st.saves + (st.saves === 1 ? " save" : " saves"));
      st.i++; head.select(".kno").text(Math.min(st.i + 1, 5));
      if (st.i >= 5) { controls.selectAll("button").attr("disabled", true); setTimeout(endCard, 650); }
    }
    function endCard() {
      box.html("");
      var rate = st.saves / 5, ec = box.append("div").attr("class", "pen-endcard");
      ec.append("div").attr("class", "big").text(st.saves + " / 5");
      ec.append("div").attr("class", "sub").text("you saved " + pct(rate) + " of five real penalties");
      var vs = ec.append("div").attr("class", "vs");
      vs.append("div").html("<b>" + pct(realRate) + "</b>real keepers");
      vs.append("div").html("<b>" + pct(optimal) + "</b>best possible");
      ec.append("div").attr("class", "fb").html(feedback(st, rate, realRate, optimal));
      ec.append("button").attr("class", "pen-replay").text("↻ Face five more").on("click", function () { buildGame(B); });
    }
    function feedback(st, rate, real, opt) {
      var counts = { left: 0, centre: 0, right: 0 }; st.dives.forEach(function (d) { counts[d]++; });
      var top = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; })[0], share = counts[top] / 5;
      if (share >= 0.8) return "You dived " + top + " " + pct(share) + " of the time — a real shooter would read that in two kicks and roll it into the open corner.";
      if (rate > real + 0.15) return "Better than the real keepers managed (" + pct(real) + "). Small sample, but you read the corners well.";
      if (rate < real - 0.15) return "Below the real-keeper rate of " + pct(real) + " — the corners are brutal when you commit early.";
      return "Right about where real keepers land (" + pct(real) + "). Mixing your dives is what keeps shooters honest.";
    }
  }

  // ── Act 4: survival ─────────────────────────────────────────────────────
  function act4(B) {
    var sv = B.survival, pk = sv.per_kick, W = 560, H = 250, mL = 50, mB = 38, mT = 16, mR = 16;
    var svg = d3.select("#survival").append("svg").attr("viewBox", "0 0 " + W + " " + H).attr("height", H);
    var x = d3.scalePoint().domain(pk.map(function (d) { return d.label; })).range([mL, W - mR]).padding(0.5);
    var y = d3.scaleLinear().domain([0, 1]).range([H - mB, mT]);
    [0, 0.25, 0.5, 0.75, 1].forEach(function (t) {
      svg.append("line").attr("x1", mL).attr("x2", W - mR).attr("y1", y(t)).attr("y2", y(t)).attr("stroke", LINE);
      svg.append("text").attr("x", mL - 8).attr("y", y(t) + 3).attr("text-anchor", "end").attr("class", "pen-axlabel").text(pct(t));
    });
    svg.append("line").attr("x1", mL).attr("x2", W - mR).attr("y1", y(sv.overall_conv)).attr("y2", y(sv.overall_conv)).attr("stroke", MUTED).attr("stroke-dasharray", "3 3");
    pk.forEach(function (d) {
      svg.append("line").attr("x1", x(d.label)).attr("x2", x(d.label)).attr("y1", y(d.lo)).attr("y2", y(d.hi)).attr("stroke", LINE).attr("stroke-width", 6).attr("stroke-linecap", "round");
      svg.append("circle").attr("cx", x(d.label)).attr("cy", y(d.conv)).attr("r", 6).attr("fill", AMBER);
      svg.append("text").attr("x", x(d.label)).attr("y", H - 20).attr("text-anchor", "middle").attr("class", "pen-axlabel").text("kick " + d.label);
      svg.append("text").attr("x", x(d.label)).attr("y", H - 8).attr("text-anchor", "middle").attr("class", "pen-axlabel").text("n=" + d.n);
    });
    if (pk.length < 5) d3.select("#press-take").text("With this few shootout kicks, “clutch” is a story the data can't yet tell.");
  }

  function findings(B) {
    var gt = B.game_theory.all, f = d3.select("#findings");
    var cards = [
      { h: "The corners win", p: "Placement clusters tight to the posts; <strong>dead centre is the emptiest zone</strong> on the goal, despite converting as well as anywhere." },
      { h: "Dives are unmeasurable", p: "Open data only reveals a keeper's dive when they save — about <strong>" + pct(B.meta.dive_coverage) + "</strong> of kicks. The clean keeper-dive frequency everyone quotes simply isn't in here." },
      { h: "Roughly at equilibrium", p: "Conversion is statistically equal across the zones shooters use (<strong>p = " + (gt.chisq_equal_success ? gt.chisq_equal_success.p.toFixed(2) : "—") + "</strong>): no obvious edge left on the table. A null, printed proudly." }
    ];
    cards.forEach(function (c) { var a = f.append("article"); a.append("h3").text(c.h); a.append("p").html(c.p); });
  }

  // ── boot ────────────────────────────────────────────────────────────────
  function boot() {
    d3.json("../data/penalties.json").then(function (B) {
      fillPlaceholders(B); fillStats(B); coldOpen(B); act1(B); act2(B); act3(B); buildGame(B); act4(B); findings(B);
    }).catch(function (e) {
      d3.select("#stats").html("<p style='color:var(--muted)'>Couldn't load the data bundle.</p>");
      console.error("penalties:", e);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
