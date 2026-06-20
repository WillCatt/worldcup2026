/* Model vs Market — hub piece 07.
   Standalone: fetch one static market.json and draw the drift (match view), the cumulative
   Brier race (scoreboard), the reliability diagram and the methods note in D3, in the hub
   palette. ONE colour for the model (amber), ONE for the market (teal); the three outcomes
   are split by dash weight, not extra hues. No build step, no runtime ML or DB. */
(function () {
  "use strict";

  var MODEL = "#b06a16", MARKET = "#2a8f8f", BACK = "#8bb6b6",
      INK = "#1a1714", MUTED = "#7a6e63", LINE = "#e6ded2", PANEL = "#fffdfa",
      LOSS = "#c0533b", GOOD = "#3a8f57";
  var OUTCOMES = ["home", "draw", "away"];
  var DASH = { home: null, draw: "6 4", away: "2 3" };   // outcome → stroke-dasharray
  var fmtPct = function (p) { return (p * 100).toFixed(0) + "%"; };
  var fmtN = function (x, d) { return x == null ? "—" : x.toFixed(d == null ? 3 : d); };

  var DATA = null, focusOutcome = "home", curMatch = 0, playable = [];

  function init() {
    d3.json("../data/market.json").then(function (data) {
      DATA = data;
      banner(); fresh(); stats();
      playable = data.matches.filter(function (m) {
        return m.model && m.market && m.market.sportsbet && m.market.sportsbet.length > 1;
      }).sort(function (a, b) {
        return (a.kickoff_utc || "") < (b.kickoff_utc || "") ? -1
          : (a.kickoff_utc || "") > (b.kickoff_utc || "") ? 1 : 0;
      });
      // open on the most interesting settled match: largest |edge| (model vs closing)
      var settled = playable.filter(function (m) { return m.score; });
      if (settled.length) {
        settled.sort(function (a, b) { return Math.abs(b.score.edge) - Math.abs(a.score.edge); });
        curMatch = playable.indexOf(settled[0]);
      }
      picker();
      drawMatch();
      race(); cards(); calibration(); methods();
      window.addEventListener("resize", debounce(function () {
        drawMatch(); race(); calibration();
      }, 180));
    });
  }

  // ── header bits ────────────────────────────────────────────────────────────
  function banner() {
    if (DATA.meta.synthetic) {
      d3.select("#banner").html(
        '<div class="mvm-banner"><b>Preview data.</b> ' + DATA.meta.synthetic_note +
        ' The charts below show a fabricated mid-tournament state so the layout can be read; ' +
        'live capture replaces it.</div>');
    }
  }

  function fresh() {
    var f = DATA.freshness || {};
    var lvl = f.status === "ok" ? "" : (f.status === "critical" ? "critical" : "degraded");
    var when = f.last_capture ? timeago(f.last_capture) : "no capture yet";
    var bits = ['<span class="mvm-dot ' + lvl + '"></span>',
      "<span>Market last captured " + when + "</span>",
      "<span>·</span><span>" + DATA.meta.book + " vs model <code>" + DATA.meta.model_version +
      "</code></span>",
      "<span>·</span><span>de-vig: " + DATA.meta.devig + "</span>"];
    var iss = (f.integrity && f.integrity.issues) || [];
    if (iss.length) bits.push("<span>·</span><span>⚠ " + iss.join("; ") + "</span>");
    d3.select("#fresh").html(bits.join(" "));
  }

  function stats() {
    var sb = DATA.scoreboard.series, n = DATA.meta.n_settled;
    var rows = [
      { num: n, lbl: "matches scored" + (n === 0 ? " — tournament just started" : "") },
      { num: fmtN(sb.model.mean_brier), lbl: "model Brier  ·  N=" + (sb.model.n || 0) },
      { num: fmtN(sb.closing.mean_brier), lbl: "closing-line Brier  ·  N=" + (sb.closing.n || 0) }
    ];
    d3.select("#stats").html(rows.map(function (r) {
      return '<div class="stat"><div class="num">' + r.num + '</div>' +
             '<div class="lbl">' + r.lbl + "</div></div>";
    }).join(""));
  }

  // ── match picker ─────────────────────────────────────────────────────────────
  function picker() {
    var wrap = d3.select("#pick").html("");
    if (!playable.length) {
      wrap.html('<span style="color:var(--muted);font-size:14.5px">Odds capture has not ' +
        "started returning matches yet — the drift charts appear here as soon as the first " +
        "snapshots land. The model is already frozen for upcoming fixtures.</span>");
      d3.select("#drift").html(""); d3.select("#driftcap").html("");
      d3.select("#legend").html(""); d3.select("#matchmeta").html("");
      return;
    }
    wrap.append("button").attr("class", "nav").text("‹ prev")
      .on("click", function () { step(-1); });
    var sel = wrap.append("select").on("change", function () {
      curMatch = +this.value; drawMatch();
    });
    sel.selectAll("option").data(playable).join("option")
      .attr("value", function (d, i) { return i; })
      .text(function (d) {
        var tag = d.score ? "✓ " : (isUpcoming(d) ? "· " : "  ");
        return tag + d.home + " v " + d.away + (d.grp ? "  (Grp " + d.grp + ")" : "");
      });
    wrap.append("button").attr("class", "nav").text("next ›")
      .on("click", function () { step(1); });
    legendLines("#legend");
  }
  function step(d) {
    curMatch = (curMatch + d + playable.length) % playable.length;
    d3.select("#pick select").property("value", curMatch);
    drawMatch();
  }

  function legendLines(sel) {
    var L = d3.select(sel).html("");
    function mk(color, label, dash) {
      var k = L.append("span").attr("class", "key");
      var s = k.append("svg").attr("width", 26).attr("height", 10);
      s.append("line").attr("x1", 0).attr("y1", 5).attr("x2", 26).attr("y2", 5)
        .attr("stroke", color).attr("stroke-width", 2.4)
        .attr("stroke-dasharray", dash || null);
      k.append("span").text(label);
    }
    mk(MARKET, "market (Sportsbet)"); mk(MODEL, "model (frozen)");
    L.append("span").attr("class", "key").style("color", MUTED).text("│  outcome:");
    mk(INK, "home", DASH.home); mk(INK, "draw", DASH.draw); mk(INK, "away", DASH.away);
    L.append("span").attr("class", "key").style("color", MUTED)
      .style("cursor", "pointer").text("│  focus: ")
      .selectAll("b").data(OUTCOMES).join("b");
    OUTCOMES.forEach(function (o) {
      L.append("span").attr("class", "key").style("cursor", "pointer")
        .style("color", o === focusOutcome ? MODEL : MUTED)
        .style("font-weight", o === focusOutcome ? 700 : 400)
        .text(o).on("click", function () { focusOutcome = o; legendLines(sel); drawMatch(); });
    });
  }

  // ── PART I: the drift ──────────────────────────────────────────────────────
  function drawMatch() {
    var m = playable[curMatch];
    if (!m) return;
    d3.select("#matchmeta").html(
      m.stage.toUpperCase() + (m.grp ? " · Group " + m.grp : "") +
      " · " + (m.venue || "") + " · kickoff " + fmtKO(m.kickoff_utc) +
      (m.kickoff_src === "estimated" ? "  (time estimated)" : ""));

    var svg = d3.select("#drift"), W = svgW(svg), H = 380,
        mg = { t: 18, r: 92, b: 38, l: 46 };
    svg.attr("viewBox", "0 0 " + W + " " + H).attr("width", "100%").attr("height", H).html("");
    var iw = W - mg.l - mg.r, ih = H - mg.t - mg.b;
    var g = svg.append("g").attr("transform", "translate(" + mg.l + "," + mg.t + ")");

    var parse = function (s) { return new Date(s); };
    var ko = parse(m.kickoff_utc);
    var sb = m.market.sportsbet.map(function (d) { return { t: parse(d.ts), home: d.home, draw: d.draw, away: d.away }; });
    var bk = (m.market["backstop:tab"] || []).map(function (d) { return { t: parse(d.ts), home: d.home, draw: d.draw, away: d.away }; });
    var tmin = d3.min(sb, function (d) { return d.t; }) || new Date(ko - 6e8);
    var x = d3.scaleTime().domain([tmin, ko]).range([0, iw]);
    var y = d3.scaleLinear().domain([0, Math.min(1, d3.max(sb, function (d) {
      return Math.max(d.home, d.draw, d.away); }) * 1.15 || 1)]).range([ih, 0]);

    // gridlines + axes
    g.append("g").attr("transform", "translate(0," + ih + ")")
      .call(d3.axisBottom(x).ticks(5).tickFormat(d3.timeFormat("%b %e")))
      .call(strip);
    g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(fmtPct)).call(strip);
    g.selectAll(".tick line").attr("stroke", LINE);

    // shaded gap band for the focused outcome (model flat vs market line)
    var fo = focusOutcome;
    var modelP = m.model[fo];
    var area = d3.area().x(function (d) { return x(d.t); })
      .y0(function (d) { return y(d[fo]); }).y1(y(modelP)).curve(d3.curveMonotoneX);
    g.append("path").datum(sb).attr("fill", MODEL).attr("opacity", 0.12).attr("d", area);

    // market lines (teal), then backstop (dashed light), then model flat (amber)
    OUTCOMES.forEach(function (o) {
      var dim = o === fo ? 1 : 0.28;
      if (bk.length) g.append("path").datum(bk).attr("fill", "none").attr("stroke", BACK)
        .attr("stroke-width", 1).attr("opacity", dim * 0.8).attr("stroke-dasharray", "1 4")
        .attr("d", line(x, y, o));
      g.append("path").datum(sb).attr("fill", "none").attr("stroke", MARKET)
        .attr("stroke-width", o === fo ? 2.6 : 1.6).attr("opacity", dim)
        .attr("stroke-dasharray", DASH[o]).attr("d", line(x, y, o));
      // model flat reference line
      g.append("line").attr("x1", 0).attr("x2", iw).attr("y1", y(m.model[o])).attr("y2", y(m.model[o]))
        .attr("stroke", MODEL).attr("stroke-width", o === fo ? 2.4 : 1.4).attr("opacity", dim)
        .attr("stroke-dasharray", DASH[o]);
      // direct labels at right edge
      var last = sb[sb.length - 1];
      g.append("text").attr("class", "mvm-directlbl").attr("x", iw + 6)
        .attr("y", y(last[o])).attr("dy", "0.32em").attr("fill", MARKET).attr("opacity", dim)
        .text(cap(o));
      g.append("text").attr("class", "mvm-directlbl").attr("x", iw + 6)
        .attr("y", y(m.model[o])).attr("dy", "0.32em").attr("fill", MODEL).attr("opacity", dim * 0.9)
        .text("◦");
    });

    // kickoff rule
    g.append("line").attr("x1", x(ko)).attr("x2", x(ko)).attr("y1", 0).attr("y2", ih)
      .attr("stroke", INK).attr("stroke-width", 1).attr("stroke-dasharray", "3 3").attr("opacity", 0.5);
    g.append("text").attr("class", "mvm-anno").attr("x", x(ko)).attr("y", -4)
      .attr("text-anchor", "end").text("kickoff");

    // steam markers on the focused outcome's market line
    (m.steam || []).filter(function (s) { return s.outcome === fo; }).forEach(function (s) {
      var t = parse(s.to_ts);
      var pt = nearest(sb, t);
      if (!pt) return;
      g.append("path").attr("d", d3.symbol(d3.symbolTriangle, 46)())
        .attr("transform", "translate(" + x(t) + "," + (y(pt[fo]) - 10) + ")")
        .attr("fill", s.delta > 0 ? GOOD : LOSS);
    });

    // widest-gap annotation
    var widest = sb.reduce(function (best, d) {
      var gap = Math.abs(d[fo] - modelP);
      return gap > best.gap ? { gap: gap, t: d.t, p: d[fo] } : best;
    }, { gap: -1 });
    if (widest.gap > 0.02) {
      g.append("text").attr("class", "mvm-anno").attr("fill", MODEL)
        .attr("x", x(widest.t)).attr("y", y((widest.p + modelP) / 2))
        .attr("text-anchor", "middle").attr("dy", "-0.4em")
        .text("gap " + (widest.gap * 100).toFixed(0) + "pts");
    }

    // result stamp
    if (m.result) {
      g.append("text").attr("class", "mvm-anno").attr("x", x(ko) + 6).attr("y", 14)
        .attr("fill", INK)
        .text("FT " + m.result.home_goals + "–" + m.result.away_goals + " (" + m.result.outcome + ")");
    }

    driftCaption(m);
    verdict(m);
  }

  function line(x, y, o) {
    return d3.line().x(function (d) { return x(d.t); })
      .y(function (d) { return y(d[o]); }).curve(d3.curveMonotoneX);
  }

  function driftCaption(m) {
    var fo = focusOutcome, mp = m.model[fo];
    var close = m.market.sportsbet[m.market.sportsbet.length - 1][fo];
    var dir = mp > close ? "higher than" : "lower than";
    var txt = "Frozen model: <strong>" + cap(fo) + " " + fmtPct(mp) + "</strong>. Closing market: " +
      fmtPct(close) + ". The model sits " + (Math.abs(mp - close) * 100).toFixed(0) +
      " points " + dir + " the market on this outcome.";
    if (m.result) {
      txt += " Outcome: <strong>" + m.result.outcome + "</strong>.";
    } else {
      txt += " Not yet played.";
    }
    d3.select("#driftcap").html(txt);
  }

  function verdict(m) {
    var v = d3.select("#verdict").html("");
    if (!m.score) {
      v.html('<div class="mvm-vcard" style="grid-column:1/-1"><div class="lbl">awaiting kickoff</div>' +
        '<div class="sub">Per-match scoring appears here after full-time — the model is already ' +
        'frozen (' + fmtKO(m.model.frozen_at) + ').</div></div>');
      return;
    }
    v.append("div").attr("class", "mvm-vcard model").html(
      '<div class="lbl">model Brier</div><div class="big">' + fmtN(m.score.brier_model) +
      '</div><div class="sub">lower is better</div>');
    v.append("div").attr("class", "mvm-vcard market").html(
      '<div class="lbl">closing-line Brier</div><div class="big">' + fmtN(m.score.brier_closing) +
      '</div><div class="sub">the benchmark</div>');
    var who = m.score.model_less_wrong;
    v.append("div").attr("class", "mvm-lesswrong").html(
      "On this match, the <b class='" + (who ? "model" : "market") + "'>" +
      (who ? "model" : "market") + "</b> was less wrong by " +
      Math.abs(m.score.edge).toFixed(3) + " Brier. " +
      "<span style='color:var(--muted)'>One match is noise — see the scoreboard.</span>");
  }

  // ── PART II: cumulative Brier race ──────────────────────────────────────────
  function race() {
    legendSeries("#legend2");
    var sb = DATA.scoreboard.series;
    var svg = d3.select("#race"), W = svgW(svg), H = 360, mg = { t: 18, r: 96, b: 40, l: 48 };
    svg.attr("viewBox", "0 0 " + W + " " + H).attr("width", "100%").attr("height", H).html("");
    var iw = W - mg.l - mg.r, ih = H - mg.t - mg.b;
    var g = svg.append("g").attr("transform", "translate(" + mg.l + "," + mg.t + ")");

    var seriesDefs = [
      { key: "model", color: MODEL, label: "model", dash: null },
      { key: "closing", color: MARKET, label: "closing", dash: null },
      { key: "opening", color: BACK, label: "opening", dash: "5 4" },
      { key: "uniform", color: MUTED, label: "uniform", dash: "1 3" }
    ];
    var maxN = d3.max(seriesDefs, function (s) { return (sb[s.key].history || []).length; }) || 1;
    if (maxN < 1) { d3.select("#racecap").html("No settled matches yet — the race begins at the first full-time whistle."); return; }
    var allv = [];
    seriesDefs.forEach(function (s) {
      (sb[s.key].history || []).forEach(function (h) { if (h) allv.push(h.cum_brier); });
    });
    var x = d3.scaleLinear().domain([1, Math.max(maxN, 2)]).range([0, iw]);
    var y = d3.scaleLinear().domain([d3.min(allv) * 0.95 || 0, d3.max(allv) * 1.05 || 1]).range([ih, 0]);

    g.append("g").attr("transform", "translate(0," + ih + ")")
      .call(d3.axisBottom(x).ticks(Math.min(maxN, 8)).tickFormat(d3.format("d"))).call(strip);
    g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(function (v) { return v.toFixed(2); })).call(strip);
    g.append("text").attr("class", "mvm-axislbl").attr("x", iw).attr("y", ih + 34)
      .attr("text-anchor", "end").text("matches scored (N) →");

    seriesDefs.forEach(function (s) {
      var h = (sb[s.key].history || []).filter(Boolean);
      if (!h.length) return;
      var ln = d3.line().x(function (d) { return x(d.n); }).y(function (d) { return y(d.cum_brier); })
        .curve(d3.curveMonotoneX);
      g.append("path").datum(h).attr("fill", "none").attr("stroke", s.color)
        .attr("stroke-width", s.key === "model" || s.key === "closing" ? 2.6 : 1.5)
        .attr("stroke-dasharray", s.dash).attr("d", ln);
      var last = h[h.length - 1];
      g.append("text").attr("class", "mvm-directlbl").attr("x", iw + 6).attr("y", y(last.cum_brier))
        .attr("dy", "0.32em").attr("fill", s.color).text(s.label + " " + last.cum_brier.toFixed(3));
    });

    var nn = DATA.scoreboard.n_needed, edge = nn.mean_edge;
    var lead = sb.model.mean_brier <= sb.closing.mean_brier ? "model" : "closing line";
    var cap = "After <strong>N=" + DATA.meta.n_settled + "</strong>, the " + lead + " leads on Brier.";
    if (nn.n_for_signif) {
      cap += " The model's gap to the closing line (" + fmtN(edge, 3) +
        " ± noise) wouldn't clear two standard errors until <strong>N≈" + nn.n_for_signif +
        "</strong> — so treat any lead as variance until then.";
    }
    d3.select("#racecap").html(cap);
  }

  function legendSeries(sel) {
    var L = d3.select(sel).html("");
    [["model", MODEL, null], ["closing market", MARKET, null],
     ["opening market", BACK, "5 4"], ["uniform dummy", MUTED, "1 3"]].forEach(function (d) {
      var k = L.append("span").attr("class", "key");
      var s = k.append("svg").attr("width", 26).attr("height", 10);
      s.append("line").attr("x1", 0).attr("y1", 5).attr("x2", 26).attr("y2", 5)
        .attr("stroke", d[1]).attr("stroke-width", 2.4).attr("stroke-dasharray", d[2]);
      k.append("span").text(d[0]);
    });
  }

  // ── editorial cards ─────────────────────────────────────────────────────────
  function cards() {
    var c = DATA.scoreboard.cards, wrap = d3.select("#cards").html("");
    if (!c || !c.best) {
      wrap.html('<div class="mvm-card"><div class="tag">no matches yet</div>' +
        '<p class="quote">The best and worst calls appear once matches are played.</p></div>');
      return;
    }
    function card(p, kind, tagtxt) {
      var who = kind === "win" ? "model" : "market";
      var q = "The model gave <b>" + cap(argmax(p.model)) + " " +
        fmtPct(Math.max(p.model[0], p.model[1], p.model[2])) + "</b> when the market said " +
        fmtPct(p.closing[argmaxI(p.model)]) + " — " +
        p.home + " v " + p.away + " finished <b>" + p.outcome + "</b>.";
      wrap.append("div").attr("class", "mvm-card " + kind).html(
        '<div class="tag">' + tagtxt + '</div><p class="quote">' + q + "</p>" +
        '<div class="n">Brier: model ' + fmtN(p.brier_model) + " · closing " + fmtN(p.brier_closing) +
        "  ·  one of N=" + c.n + " scored</div>");
    }
    card(c.best, "win", "Model's best call");
    card(c.worst, "miss", "Model's worst miss");
  }

  // ── calibration / reliability diagram ───────────────────────────────────────
  function calibration() {
    legendSeries2("#legend3");
    var cal = DATA.scoreboard.calibration;
    var svg = d3.select("#calib"), W = svgW(svg), H = 360, mg = { t: 16, r: 18, b: 42, l: 48 };
    svg.attr("viewBox", "0 0 " + W + " " + H).attr("width", "100%").attr("height", H).html("");
    var iw = W - mg.l - mg.r, ih = H - mg.t - mg.b, side = Math.min(iw, ih);
    var g = svg.append("g").attr("transform", "translate(" + mg.l + "," + mg.t + ")");
    var x = d3.scaleLinear().domain([0, 1]).range([0, side]);
    var y = d3.scaleLinear().domain([0, 1]).range([side, 0]);

    g.append("g").attr("transform", "translate(0," + side + ")").call(d3.axisBottom(x).ticks(5).tickFormat(fmtPct)).call(strip);
    g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(fmtPct)).call(strip);
    g.append("line").attr("x1", x(0)).attr("y1", y(0)).attr("x2", x(1)).attr("y2", y(1))
      .attr("stroke", INK).attr("stroke-dasharray", "3 3").attr("opacity", 0.4);
    g.append("text").attr("class", "mvm-axislbl").attr("x", side).attr("y", side + 36)
      .attr("text-anchor", "end").text("predicted probability →");
    g.append("text").attr("class", "mvm-axislbl").attr("transform", "rotate(-90)")
      .attr("x", 0).attr("y", -34).attr("text-anchor", "end").text("observed frequency →");

    [["model", MODEL, cal.model], ["closing", MARKET, cal.closing]].forEach(function (d) {
      var pts = d[2].filter(function (b) { return b.n > 0; });
      var ln = d3.line().x(function (b) { return x(b.pred); }).y(function (b) { return y(b.obs); });
      g.append("path").datum(pts).attr("fill", "none").attr("stroke", d[1])
        .attr("stroke-width", 2).attr("opacity", 0.85).attr("d", ln);
      g.selectAll(".pt-" + d[0]).data(pts).join("circle")
        .attr("cx", function (b) { return x(b.pred); }).attr("cy", function (b) { return y(b.obs); })
        .attr("r", function (b) { return 3 + Math.sqrt(b.n); }).attr("fill", d[1]).attr("opacity", 0.5)
        .attr("stroke", d[1]);
      g.selectAll(".n-" + d[0]).data(pts).join("text")
        .attr("x", function (b) { return x(b.pred); }).attr("y", function (b) { return y(b.obs) - 8 - Math.sqrt(b.n); })
        .attr("text-anchor", "middle").attr("class", "mvm-directlbl").attr("fill", d[1])
        .text(function (b) { return "n=" + b.n; });
    });
    d3.select("#calibcap").html(
      "Dot size is the bin's count — small dots are barely-evidenced. Points above the diagonal " +
      "mean the outcome happened more often than predicted (under-confident); below means over-confident.");
  }

  function legendSeries2(sel) {
    var L = d3.select(sel).html("");
    [["model", MODEL], ["closing market", MARKET]].forEach(function (d) {
      var k = L.append("span").attr("class", "key");
      k.append("svg").attr("width", 16).attr("height", 12).append("circle")
        .attr("cx", 8).attr("cy", 6).attr("r", 5).attr("fill", d[1]).attr("opacity", 0.6);
      k.append("span").text(d[0]);
    });
  }

  // ── PART III: methods ────────────────────────────────────────────────────────
  function methods() {
    var dv = DATA.devig_comparison, nn = DATA.scoreboard.n_needed, m = DATA.meta;
    var html = "";
    html += "<p>Bookmaker odds imply probabilities that sum to more than 100% — the " +
      "<em>overround</em>, the margin. To compare a book to the model you must strip it. Two " +
      "standard methods are computed and they are <em>not</em> equivalent.</p>";

    (dv.examples || []).forEach(function (ex) {
      html += "<h4>" + (ex.kind === "lopsided" ? "On a lopsided market they diverge" :
        "On a near coin-flip they agree") + " — " + ex.label + "</h4>";
      html += '<table class="mvm-devig"><thead><tr><th>outcome</th><th>proportional</th>' +
        "<th>Shin</th><th>gap</th></tr></thead><tbody>";
      ex.by_outcome.forEach(function (r) {
        html += "<tr><td>" + r.outcome + "</td><td>" + fmtPct(r.proportional) + "</td><td>" +
          fmtPct(r.shin) + '</td><td class="gap">' + (r.gap >= 0 ? "+" : "") +
          (r.gap * 100).toFixed(1) + "pts</td></tr>";
      });
      html += "</tbody></table>";
      html += '<p style="font-size:13px;color:var(--muted)">Overround ' +
        (ex.overround * 100).toFixed(1) + "% · Shin z=" + ex.shin_z.toFixed(3) + "</p>";
    });
    html += "<p>Shin attributes the margin to insider traders, which concentrates it on " +
      "longshots; at z=0 it collapses to proportional. They split exactly where it matters — " +
      "the long-odds outcomes. This piece scores against the <b>Shin-de-vigged closing line</b>.</p>";

    html += "<h4>The freeze protocol</h4><p>Each match's model probability is written once, " +
      "timestamped, before kickoff, and can never be edited — the storage layer refuses " +
      "retroactive changes and refuses to write after kickoff. A retrain is a new " +
      "<em>model version</em> tracked alongside, never an overwrite. The model (" +
      "<code>" + m.model_version + "</code>) reads only international-results history; it cannot " +
      "see the odds, so it cannot be circular.</p>";

    html += "<h4>Why the closing line is the benchmark</h4><p>The closing line is the market's " +
      "last, most-informed price, and the closing-line-value literature treats beating it " +
      "consistently as the real test of a forecast. Opening odds are shown only to watch the " +
      "market <em>learn</em> — calling opening odds 'the market' would be moving the goalposts.</p>";

    html += "<h4>How big must N be?</h4><p>";
    if (nn.n_for_signif) {
      html += "At the current per-match spread, the model's Brier gap to the closing line " +
        "wouldn't be distinguishable from noise until <b>N≈" + nn.n_for_signif + "</b> matches. " +
        "The group stage is 72; the whole tournament 104. So even a clean answer is only " +
        "arriving late — and any early lead is variance.";
    } else {
      html += "Not enough settled matches yet to estimate the N required for significance.";
    }
    html += "</p>";

    html += "<h4>Group vs knockout</h4><p>Group matches can draw and are priced as 1X2; knockouts " +
      "resolve via extra time and penalties, a different regime the model and market both handle " +
      "differently. The two are flagged separately so they're never silently pooled.</p>";

    html += '<p class="mvm-disclaim">All probabilities are for measurement only. Nothing here is ' +
      "betting advice; no odds are presented as actionable.</p>";
    d3.select("#methods-body").html(html);
  }

  // ── helpers ──────────────────────────────────────────────────────────────────
  function svgW(svg) { var n = svg.node(); return (n && n.parentNode.clientWidth) || 760; }
  function strip(sel) { sel.select(".domain").attr("stroke", LINE); sel.selectAll("text").attr("fill", MUTED).attr("font-family", "JetBrains Mono, monospace").attr("font-size", 11); }
  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
  function argmaxI(a) { return a.indexOf(Math.max(a[0], a[1], a[2])); }
  function argmax(a) { return OUTCOMES[argmaxI(a)]; }
  function isUpcoming(m) { return new Date(m.kickoff_utc) > new Date(); }
  function nearest(arr, t) {
    var best = null, bd = Infinity;
    arr.forEach(function (d) { var dd = Math.abs(d.t - t); if (dd < bd) { bd = dd; best = d; } });
    return best;
  }
  function fmtKO(s) { return d3.timeFormat("%b %e, %H:%M")(new Date(s)) + " UTC"; }
  function timeago(s) {
    var sec = (Date.now() - new Date(s)) / 1000;
    if (sec < 0) return "just now";
    if (sec < 3600) return Math.round(sec / 60) + " min ago";
    if (sec < 86400) return Math.round(sec / 3600) + " h ago";
    return Math.round(sec / 86400) + " d ago";
  }
  function debounce(fn, ms) { var t; return function () { clearTimeout(t); t = setTimeout(fn, ms); }; }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
