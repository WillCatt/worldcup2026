/* Penalty Geometry & Game Theory — hub piece.
   World Cup shootouts (1982-2022) with the keeper's dive recorded on every kick.
   Fetch one static penalties.json and hand-draw the cold open, five acts and the
   keeper game in D3, in the hub palette. No build step. */
(function () {
  "use strict";

  var GOAL_W = 7.32, GOAL_H = 2.44;
  var INK = "#1a1714", MUTED = "#7a6e63", LINE = "#e6ded2", AMBER = "#b06a16",
      RED = "#c0533b", TEAL = "#2a8f8f", GREY = "#cdbfae", PANEL = "#fffdfa";

  // zone 1-9 (shooter's view) -> grid column/row centres in goal metres
  var COL_X = { L: -2.44, C: 0, R: 2.44 }, ROW_Z = { T: 2.03, M: 1.22, B: 0.41 };
  var ZONE_COL = { 1: "L", 2: "C", 3: "R", 4: "L", 5: "C", 6: "R", 7: "L", 8: "C", 9: "R" };
  var ZONE_ROW = { 1: "T", 2: "T", 3: "T", 4: "M", 5: "M", 6: "M", 7: "B", 8: "B", 9: "B" };
  function zoneCentre(z) { return { x: COL_X[ZONE_COL[z]], z: ROW_Z[ZONE_ROW[z]] }; }

  // ── pure game logic (also node-exportable for tests) ────────────────────
  // The player picks a dive direction. Miss the shot's column and the keeper is
  // out of the play (goal). Match it and the save lands with the empirical rate
  // observed when real keepers committed to that zone/direction.
  function resolveKick(kick, dive, saveByZone, saveByDir, rng) {
    rng = rng || Math.random;
    if (dive !== kick.dir) return { saved: false, reason: "wrong way" };
    var ps = saveByZone[kick.zone];
    if (ps == null) ps = saveByDir[dive];
    var saved = rng() < ps;
    return { saved: saved, reason: saved ? "saved" : "beaten in the corner" };
  }
  if (typeof document === "undefined") {
    module.exports = { resolveKick: resolveKick, zoneCentre: zoneCentre };
    return;
  }

  var pct = function (x, d) { return x == null || isNaN(x) ? "—" : (100 * x).toFixed(d || 0) + "%"; };

  // diverging conversion ramp: low (saves) teal -> high (goals) red
  function convColor(c) {
    if (c == null) return "#f1ece3";
    var stops = ["#2a8f8f", "#9fc4bd", "#e9e0cf", "#e2b86b", "#d39a3f", "#c0533b"];
    var t = Math.max(0, Math.min(1, c)), n = stops.length - 1, i = Math.floor(t * n), f = t * n - i;
    return i >= n ? stops[n] : d3.interpolateRgb(stops[i], stops[i + 1])(f);
  }
  function textOn(c) { return c != null && c >= 0.45 ? "#fff" : INK; }

  // ── reusable goal mouth at true 7.32×2.44 aspect, with 3×3 zone grid ─────
  function buildGoal(svgSel, m, withZones) {
    m = m || 58;
    var padX = 0.62, padTop = 0.55, padBot = 0.5;
    var domX = [-GOAL_W / 2 - padX, GOAL_W / 2 + padX], domZ = [0, GOAL_H + padTop];
    var W = (domX[1] - domX[0]) * m, H = (domZ[1] - domZ[0]) * m + padBot * m;
    svgSel.selectAll("*").remove();
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
    if (withZones) {
      [-GOAL_W / 6, GOAL_W / 6].forEach(function (zx) {
        frame.append("line").attr("class", "pen-zone").attr("x1", sx(zx)).attr("x2", sx(zx)).attr("y1", ty).attr("y2", groundY);
      });
      [GOAL_H / 3, 2 * GOAL_H / 3].forEach(function (zz) {
        frame.append("line").attr("class", "pen-zone").attr("x1", lx).attr("x2", rx).attr("y1", sz(zz)).attr("y2", sz(zz));
      });
    }
    frame.append("path").attr("class", "pen-post").attr("d", "M" + lx + "," + groundY + " L" + lx + "," + ty + " L" + rx + "," + ty + " L" + rx + "," + groundY);
    frame.append("line").attr("class", "pen-ground").attr("x1", sx(domX[0])).attr("x2", sx(domX[1])).attr("y1", groundY).attr("y2", groundY);
    return { sx: sx, sz: sz, heat: heat, dots: dots, groundY: groundY, W: W, H: H, m: m };
  }

  // ── stats + placeholders ─────────────────────────────────────────────────
  function fillStats(B) {
    var m = B.meta, s = d3.select("#stats");
    [{ n: m.n_clean.toLocaleString(), l: "World Cup shootout kicks" },
     { n: m.n_games, l: "shootouts, 1982–2022" },
     { n: pct(m.overall_conv), l: "of them scored" }].forEach(function (c) {
      var d = s.append("div").attr("class", "stat");
      d.append("div").attr("class", "num").html(c.n);
      d.append("div").attr("class", "lbl").text(c.l);
    });
  }
  function fillPlaceholders(B) {
    var vals = {
      n_clean: B.meta.n_clean, n_games: B.meta.n_games,
      keeper_correct_pct: pct(B.coin_flip.keeper_correct_rate),
      keeper_centre_pct: pct(B.centre.keeper_stays_centre)
    };
    document.querySelectorAll("[data-pen]").forEach(function (el) {
      var k = el.getAttribute("data-pen"); if (vals[k] != null) el.textContent = vals[k];
    });
  }

  // ── cold open: every kick, jittered into its zone ────────────────────────
  function coldOpen(B) {
    var G = buildGoal(d3.select("#coldopen"), 54, true);
    var kicks = B.game.kicks, seed = 7;
    function rnd() { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; }
    var cw = GOAL_W / 6 * 0.74, ch = GOAL_H / 6 * 0.74;
    kicks.forEach(function (k) {
      var c = zoneCentre(k.zone);
      G.dots.append("circle")
        .attr("cx", G.sx(c.x + (rnd() - 0.5) * 2 * cw))
        .attr("cy", G.sz(c.z + (rnd() - 0.5) * 2 * ch))
        .attr("r", 4.2).attr("fill", k.scored ? RED : TEAL)
        .attr("fill-opacity", 0.62).attr("stroke", "#fff").attr("stroke-width", 0.5);
    });
    d3.select("#cold-cap").html("All <strong>" + kicks.length + "</strong> on-target shootout kicks, " +
      "placed in the third of the goal they were struck. The bottom corners are crowded; dead centre " +
      "is nearly empty — and yet, as Act IV shows, the empty middle is some of the safest real estate on the goal.");
  }

  // ── Act I: the coin flip ─────────────────────────────────────────────────
  function act1(B) {
    var cf = B.coin_flip, f = d3.select("#flip");
    [{ cls: "wrong", tag: "keeper guesses wrong side", big: pct(cf.conv_when_wrong), n: cf.n_wrong,
       sub: "of those kicks score. With the keeper committed the wrong way, the goal is wide open." },
     { cls: "right", tag: "keeper guesses right side", big: pct(cf.conv_when_right), n: cf.n_right,
       sub: "still score even when the keeper reads it — the strike just has to beat their reach." }
    ].forEach(function (c) {
      var card = f.append("div").attr("class", "fcard " + c.cls);
      card.append("div").attr("class", "ftag").text(c.tag);
      card.append("div").attr("class", "fbig").text(c.big);
      card.append("div").attr("class", "fsub").html(c.sub + " <span style='color:var(--muted)'>(n=" + c.n + ")</span>");
    });
    d3.select("#flip-cap").html("Keepers read the correct side on <strong>" + pct(cf.keeper_correct_rate) +
      "</strong> of kicks — and they barely use the centre as a dive, going left or right on <strong>" +
      pct(1 - cf.keeper_dive_dist.C) + "</strong> of them. The guess is close to a 50/50, and getting it " +
      "right is the only thing standing between the taker and an almost-automatic goal.");
  }

  // ── Act II: payoff matrix heatmap ─────────────────────────────────────────
  function act2(B) {
    var dirs = B.matrix.dirs, lbl = { L: "left", C: "centre", R: "right" };
    var cell = {}; B.matrix.cells.forEach(function (c) { cell[c.shot + c.keeper] = c; });
    var t = d3.select("#payoff");
    var thead = t.append("thead").append("tr");
    thead.append("th").html("&nbsp;");
    thead.append("th").attr("colspan", dirs.length).text("keeper dives →");
    var sub = t.append("thead").append("tr");
    sub.append("th").html("shot ↓");
    dirs.forEach(function (k) { sub.append("th").text(lbl[k]); });
    var tb = t.append("tbody");
    dirs.forEach(function (sd) {
      var tr = tb.append("tr");
      tr.append("td").attr("class", "rowlbl").text(lbl[sd]);
      dirs.forEach(function (kd) {
        var c = cell[sd + kd], td = tr.append("td").attr("class", "cell" + (sd === kd ? " diag" : ""));
        td.style("background", convColor(c.conv)).style("color", textOn(c.conv));
        td.append("div").attr("class", "cv").text(c.conv == null ? "—" : pct(c.conv));
        td.append("div").attr("class", "cn").text("n=" + c.n);
      });
    });
    d3.select("#payoff-cap").html("Read down the <strong>outlined diagonal</strong> — keeper and ball " +
      "to the same side — and conversion collapses toward a coin flip. Read anywhere off it and it's 80–95%. " +
      "The middle column is thin because keepers so rarely stay home; the takers who shoot there against a " +
      "diving keeper cash in.");
  }

  // ── Act III: Nash table ───────────────────────────────────────────────────
  function act3(B) {
    var n = B.nash, lbl = { L: "left", C: "centre", R: "right" }, tb = d3.select("#nash tbody");
    n.by_dir.forEach(function (z) {
      tb.append("tr").html(
        "<td>" + lbl[z.dir] + "</td><td>" + z.n + "</td><td>" + pct(z.usage) + "</td>" +
        "<td>" + pct(z.conv) + "</td><td class='ci'>[" + pct(z.lo) + ", " + pct(z.hi) + "]</td>");
    });
    var p = n.chisq.p, equal = p >= 0.05;
    d3.select("#nash-verdict").html("<b>Verdict.</b> " + (equal
      ? "Conversion is statistically indistinguishable across the three sides (χ² p = " + p.toFixed(2) +
        "; spread just " + n.spread_pp + " pts). That is exactly what mixed-strategy equilibrium predicts — " +
        "no side is obviously being left on the table. A null worth printing proudly, though with " +
        n.by_dir.reduce(function (a, b) { return a + b.n; }, 0) + " kicks the test could also be too weak to catch a small gap."
      : "Conversion differs across sides (χ² p = " + p.toFixed(2) + "): a " + n.spread_pp +
        "-point spread the takers could be exploiting."));
    d3.select("#nash-cap").html("Unlike the old open-data version of this piece, the equilibrium read no " +
      "longer leans on the shooter alone — the keeper's actual dive is in every row of the matrix above. " +
      "Footedness is the one tell left: right-footers favour the across-body side, so a keeper who knows the " +
      "taker's stronger foot starts a half-step ahead.");
    d3.select("#nash-take").text(equal
      ? "Take the whole tournament's worth of kicks and shooters look like textbook equilibrium players — spreading their bets so no side pays more than another."
      : "Shooters appear to under-use their best-converting side — a small edge left on the table.");
  }

  // ── Act IV: the abandoned centre ──────────────────────────────────────────
  function act4(B) {
    var c = B.centre, W = 540, H = 150, mL = 12, mR = 12, mT = 28, mB = 8;
    var rows = [
      { lbl: "keeper stays central", v: c.keeper_stays_centre, col: TEAL },
      { lbl: "shooter aims centre", v: c.shooter_centre_usage, col: AMBER }
    ];
    var svg = d3.select("#centre").append("svg").attr("viewBox", "0 0 " + W + " " + H).attr("height", H);
    var x = d3.scaleLinear().domain([0, 0.5]).range([mL, W - mR - 60]);
    var y = d3.scalePoint().domain(rows.map(function (r) { return r.lbl; })).range([mT, H - mB]).padding(0.6);
    [0, 0.1, 0.2, 0.3, 0.4, 0.5].forEach(function (t) {
      svg.append("line").attr("x1", x(t)).attr("x2", x(t)).attr("y1", mT - 10).attr("y2", H - mB).attr("stroke", LINE);
      svg.append("text").attr("x", x(t)).attr("y", mT - 16).attr("text-anchor", "middle").attr("class", "pen-axlabel").text(pct(t));
    });
    rows.forEach(function (r) {
      svg.append("rect").attr("x", x(0)).attr("y", y(r.lbl) - 11).attr("width", x(r.v) - x(0)).attr("height", 22).attr("rx", 4).attr("fill", r.col);
      svg.append("text").attr("x", x(0) + 6).attr("y", y(r.lbl) - 16).attr("class", "pen-axlabel").text(r.lbl);
      svg.append("text").attr("x", x(r.v) + 8).attr("y", y(r.lbl) + 4).attr("class", "pen-axlabel").style("fill", INK).style("font-size", "13px").text(pct(r.v));
    });
    d3.select("#centre-cap").html("A centre shot against a keeper who commits to a side scores <strong>" +
      pct(c.centre_vs_committed_conv) + "</strong> (n=" + c.centre_vs_committed_n + "). The only way it goes " +
      "wrong is if the keeper holds the middle — and they do that just " + pct(c.keeper_stays_centre) +
      " of the time, scoring a brutal " + pct(c.centre_vs_centre_conv) + " when they call the bluff " +
      "(n=" + c.centre_vs_centre_n + ", so read that as a warning, not a precise rate).");
  }

  // ── the game ──────────────────────────────────────────────────────────────
  function buildGame(B) {
    var g = B.game, deck = g.kicks;
    var byZone = {}, byDir = g.save_when_right_by_dir;
    Object.keys(g.save_when_right_by_zone).forEach(function (z) { byZone[z] = g.save_when_right_by_zone[z]; });
    var box = d3.select("#game"); box.html("");
    var head = box.append("div").attr("class", "pen-game-head");
    head.append("div").html("Kick <span class='kno'>1</span> of 5");
    var pips = head.append("div").attr("class", "pen-pips");
    var savesEl = head.append("div").attr("class", "saves").text("0 saves");
    var goalwrap = box.append("div").attr("class", "pen-goalwrap");
    var G = buildGoal(goalwrap.append("svg"), 52, true);
    var result = box.append("div").attr("class", "pen-game-result").html("Choose a side to dive.");
    var controls = box.append("div").attr("class", "pen-dives");
    var st = { i: 0, saves: 0, dives: [], deck: [] };
    for (var k = 0; k < 5; k++) st.deck.push(deck[Math.floor(Math.random() * deck.length)]);
    for (var pi = 0; pi < 5; pi++) pips.append("div").attr("class", "pen-pip");
    [["← Left", "L"], ["Centre", "C"], ["Right →", "R"]].forEach(function (b) {
      controls.append("button").attr("class", "pen-dive").text(b[0]).on("click", function () { play(b[1]); });
    });
    function diveCentre(d) { return { x: COL_X[d], z: d === "C" ? 0.9 : 0.8 }; }
    function play(dive) {
      if (st.i >= 5) return;
      var kick = st.deck[st.i], res = resolveKick(kick, dive, byZone, byDir);
      st.dives.push(dive); if (res.saved) st.saves++;
      G.dots.selectAll("*").remove();
      var t = diveCentre(dive), c = zoneCentre(kick.zone);
      G.dots.append("rect").attr("x", G.sx(t.x) - 13).attr("y", G.sz(t.z) - 26).attr("width", 26).attr("height", 52)
        .attr("rx", 9).attr("fill", "none").attr("stroke", MUTED).attr("stroke-width", 2.5).attr("opacity", 0.7);
      G.dots.append("circle").attr("cx", G.sx(c.x)).attr("cy", G.sz(c.z)).attr("r", 8)
        .attr("fill", res.saved ? TEAL : RED).attr("stroke", "#fff").attr("stroke-width", 1.5);
      pips.selectAll(".pen-pip").filter(function (d, idx) { return idx === st.i; }).classed(res.saved ? "save" : "goal", true);
      result.html(res.saved ? "<b>Saved!</b> You got across and reached it." :
        (res.reason === "wrong way" ? "<b>Goal.</b> Wrong way — it went the other side." : "<b>Goal.</b> Right side, but it beat your reach."));
      savesEl.text(st.saves + (st.saves === 1 ? " save" : " saves"));
      st.i++; head.select(".kno").text(Math.min(st.i + 1, 5));
      if (st.i >= 5) { controls.selectAll("button").attr("disabled", true); setTimeout(endCard, 700); }
    }
    function endCard() {
      box.html("");
      var rate = st.saves / 5, ec = box.append("div").attr("class", "pen-endcard");
      ec.append("div").attr("class", "big").text(st.saves + " / 5");
      ec.append("div").attr("class", "sub").text("you saved " + pct(rate) + " of five real penalties");
      var vs = ec.append("div").attr("class", "vs");
      vs.append("div").html("<b>" + pct(g.real_keeper_save_rate) + "</b>real keepers");
      vs.append("div").html("<b>" + pct(B.coin_flip.keeper_correct_rate) + "</b>read the side");
      ec.append("div").attr("class", "fb").html(feedback(st, rate, g.real_keeper_save_rate));
      ec.append("button").attr("class", "pen-replay").text("↻ Face five more").on("click", function () { buildGame(B); });
    }
    function feedback(st, rate, real) {
      var counts = { L: 0, C: 0, R: 0 }; st.dives.forEach(function (d) { counts[d]++; });
      var top = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; })[0], share = counts[top] / 5;
      var name = { L: "left", C: "centre", R: "right" }[top];
      if (share >= 0.8) return "You dived " + name + " " + pct(share) + " of the time — a real shooter reads that in two kicks and rolls it into the open side.";
      if (rate > real + 0.15) return "Better than the real keepers managed (" + pct(real) + "). Small sample, but you read the corners well.";
      if (rate < real - 0.15) return "Below the real-keeper rate of " + pct(real) + " — the corners are brutal when you commit early.";
      return "Right about where real keepers land (" + pct(real) + "). Mixing your dives is what keeps shooters honest.";
    }
  }

  // ── Act V: pressure ───────────────────────────────────────────────────────
  function act5(B) {
    var pk = B.pressure.by_kick, el = B.pressure.elimination;
    var W = 560, H = 250, mL = 50, mB = 38, mT = 16, mR = 16;
    var svg = d3.select("#pressure").append("svg").attr("viewBox", "0 0 " + W + " " + H).attr("height", H);
    var x = d3.scalePoint().domain(pk.map(function (d) { return d.num; })).range([mL, W - mR]).padding(0.5);
    var y = d3.scaleLinear().domain([0, 1]).range([H - mB, mT]);
    [0, 0.25, 0.5, 0.75, 1].forEach(function (t) {
      svg.append("line").attr("x1", mL).attr("x2", W - mR).attr("y1", y(t)).attr("y2", y(t)).attr("stroke", LINE);
      svg.append("text").attr("x", mL - 8).attr("y", y(t) + 3).attr("text-anchor", "end").attr("class", "pen-axlabel").text(pct(t));
    });
    svg.append("line").attr("x1", mL).attr("x2", W - mR).attr("y1", y(B.meta.overall_conv)).attr("y2", y(B.meta.overall_conv))
      .attr("stroke", MUTED).attr("stroke-dasharray", "3 3");
    svg.append("text").attr("x", W - mR).attr("y", y(B.meta.overall_conv) - 5).attr("text-anchor", "end").attr("class", "pen-axlabel").text("overall " + pct(B.meta.overall_conv));
    pk.forEach(function (d) {
      svg.append("line").attr("x1", x(d.num)).attr("x2", x(d.num)).attr("y1", y(d.lo)).attr("y2", y(d.hi)).attr("stroke", LINE).attr("stroke-width", 6).attr("stroke-linecap", "round");
      svg.append("circle").attr("cx", x(d.num)).attr("cy", y(d.conv)).attr("r", 6).attr("fill", AMBER);
      svg.append("text").attr("x", x(d.num)).attr("y", H - 20).attr("text-anchor", "middle").attr("class", "pen-axlabel").text("kick " + d.num);
      svg.append("text").attr("x", x(d.num)).attr("y", H - 8).attr("text-anchor", "middle").attr("class", "pen-axlabel").text("n=" + d.n);
    });
    d3.select("#press-cap").html("<strong>The confound:</strong> kick order is manager-chosen, so order " +
      "effects and taker quality are tangled together. Even a real dip would not prove pressure — it could just " +
      "be who managers send when.");
    d3.select("#press-take").text("Must-score elimination kicks convert " + pct(el.must_conv) + " (n=" + el.must_n +
      "), all-but-identical to the " + pct(el.rest_conv) + " everywhere else — the choke, if it exists, hides well.");
  }

  function findings(B) {
    var f = d3.select("#findings"), cf = B.coin_flip;
    [{ h: "Guess right, win a coin flip", p: "Read the wrong side and <strong>" + pct(cf.conv_when_wrong) +
        "</strong> of kicks score; read the right side and it still scores <strong>" + pct(cf.conv_when_right) +
        "</strong>. The dive only converts a near-certain goal into a 50/50." },
     { h: "Shooters play equilibrium", p: "Conversion is statistically equal across left, centre and right " +
        "(χ² p = " + B.nash.chisq.p.toFixed(2) + "): no side left on the table. The clean game-theory null, " +
        "now grounded in the keeper's real dives." },
     { h: "The middle is underrated", p: "Keepers stay central only <strong>" + pct(B.centre.keeper_stays_centre) +
        "</strong> of the time, so a centred shot usually meets empty net — the panenka is a read, not a flourish." }
    ].forEach(function (c) { var a = f.append("article"); a.append("h3").text(c.h); a.append("p").html(c.p); });
  }

  // ── boot ────────────────────────────────────────────────────────────────
  function boot() {
    d3.json("../data/penalties.json").then(function (B) {
      fillStats(B); fillPlaceholders(B); coldOpen(B); act1(B); act2(B); act3(B); act4(B); buildGame(B); act5(B); findings(B);
    }).catch(function (e) {
      d3.select("#stats").html("<p style='color:var(--muted)'>Couldn't load the data bundle.</p>");
      console.error("penalties:", e);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
