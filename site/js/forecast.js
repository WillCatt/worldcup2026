/* Forecast — hub piece. Fetch one static forecast.json: predict every match as
   probabilities (frozen pre-tournament) and grade the model against actual results.
   Hand-drawn in D3, hub palette. No build step. */
(function () {
  "use strict";

  var INK = "#1a1714", MUTED = "#7a6e63", LINE = "#e6ded2", AMBER = "#b06a16",
      TEAL = "#2a8f8f", PANEL = "#fffdfa";
  var HEAT = ["#faf8f4", "#f2dcae", "#e8c98f", "#d39a3f", "#b06a16", "#7a430b"];
  var pct = function (x, d) { return x == null || isNaN(x) ? "—" : (100 * x).toFixed(d || 0) + "%"; };
  function heat(t) {
    t = Math.max(0, Math.min(1, Math.sqrt(t))); var n = HEAT.length - 1, i = Math.floor(t * n), f = t * n - i;
    return i >= n ? HEAT[n] : d3.interpolateRgb(HEAT[i], HEAT[i + 1])(f);
  }
  var OUT = { home: "home win", draw: "draw", away: "away win" };

  function fillStats(B) {
    var sc = B.scorecard, s = d3.select("#stats");
    [{ n: B.meta.n_fixtures, l: "group matches predicted" },
     { n: B.meta.n_played, l: "played and graded so far" },
     { n: sc.pct_correct == null ? "—" : pct(sc.pct_correct), l: "results called correctly" }
    ].forEach(function (c) {
      var d = s.append("div").attr("class", "stat");
      d.append("div").attr("class", "num").html(c.n);
      d.append("div").attr("class", "lbl").text(c.l);
    });
  }

  // ── Part I: fixture picker + card ────────────────────────────────────────
  function picker(B) {
    var fx = B.fixtures.filter(function (f) { return f.known; });
    var sel = d3.select("#fc-select"), i = 0;
    fx.forEach(function (f, k) {
      var date = new Date(f.date + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
      sel.append("option").attr("value", k).text(date + " · " + f.home + " v " + f.away + "  (Grp " + f.group + ")");
    });
    // default to the first not-yet-played fixture
    var played = new Set(B.log.map(function (l) { return l.home + "|" + l.away; }));
    var firstUp = fx.findIndex(function (f) { return !played.has(f.home + "|" + f.away); });
    i = firstUp >= 0 ? firstUp : 0;
    function show() { sel.property("value", i); renderCard(fx[i], B); }
    sel.on("change", function () { i = +this.value; show(); });
    d3.select("#fc-prev").on("click", function () { i = (i - 1 + fx.length) % fx.length; show(); });
    d3.select("#fc-next").on("click", function () { i = (i + 1) % fx.length; show(); });
    show();
  }

  function renderCard(f, B) {
    var box = d3.select("#fc-card"); box.html("");
    var log = B.log.find(function (l) { return l.home === f.home && l.away === f.away; });
    var date = new Date(f.date + "T00:00:00Z").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "long", timeZone: "UTC" });
    // header
    var mh = box.append("div").attr("class", "fc-mh");
    mh.append("div").attr("class", "tm home").text(f.home);
    var mid = mh.append("div").attr("class", "mid");
    if (log) {
      mid.html("<span style='font-size:20px;color:" + INK + ";font-weight:700'>" + log.actual.h + "–" + log.actual.a + "</span>" +
        "<span class='fc-actual " + (log.correct ? "ok" : "no") + "'>" + (log.correct ? "called ✓" : "missed ✗") + "</span>");
    } else { mid.html("vs"); }
    mh.append("div").attr("class", "tm away").text(f.away);
    box.append("div").attr("class", "fc-meta").html(date + " · " + f.venue +
      (f.host_edge.length ? " · " + f.host_edge.join(", ") + " at home" : " · neutral"));

    // 1X2 bar
    var bar = box.append("div").attr("class", "fc-1x2");
    [["h", f.p_home], ["d", f.p_draw], ["a", f.p_away]].forEach(function (d) {
      bar.append("div").attr("class", d[0]).style("width", (100 * d[1]) + "%").text(d[1] >= 0.08 ? pct(d[1]) : "");
    });
    box.append("div").attr("class", "fc-1x2lbl")
      .html("<span>" + f.home + " win</span><span>draw</span><span>" + f.away + " win</span>");
    box.append("div").attr("class", "fc-xg").html("expected goals &nbsp;<b>" + f.exp_home + "</b> – <b>" + f.exp_away + "</b>");

    // grid heatmap + top scores
    var wrap = box.append("div").attr("class", "fc-grid-wrap");
    scoreHeat(wrap.append("div").attr("class", "fc-heat"), f, log);
    var tops = wrap.append("div").attr("class", "fc-tops");
    tops.append("div").style("color", MUTED).style("margin-bottom", "4px").text("most likely scores");
    f.top_scores.forEach(function (t) {
      var r = tops.append("div").attr("class", "row");
      r.append("span").attr("class", "sc").text(t.h + "–" + t.a);
      r.append("span").attr("class", "pb").text(pct(t.p, 1));
    });

    // pick-along
    var g = box.append("div").attr("class", "fc-guess");
    g.append("div").style("font-size", "13px").style("color", MUTED).style("margin-bottom", "8px")
      .text(log ? "Would you have called it?" : "Your call?");
    var btns = g.append("div").attr("class", "gbtns");
    var note = g.append("div").attr("class", "fc-gnote");
    [["home", f.home + " win"], ["draw", "Draw"], ["away", f.away + " win"]].forEach(function (o) {
      btns.append("button").attr("class", "fc-gb").text(o[1]).on("click", function () {
        btns.selectAll("button").classed("sel", false); d3.select(this).classed("sel", true);
        var modelP = { home: f.p_home, draw: f.p_draw, away: f.p_away }[o[0]];
        var modelPick = ["home", "draw", "away"].reduce(function (a, k) {
          return ({ home: f.p_home, draw: f.p_draw, away: f.p_away })[k] > ({ home: f.p_home, draw: f.p_draw, away: f.p_away })[a] ? k : a; }, "home");
        var msg = "Model gives that <b>" + pct(modelP) + "</b>" +
          (o[0] === modelPick ? " — it agrees, that's its pick." : " — the model leans " + OUT[modelPick] + ".");
        if (log) msg += " Actual result: <b>" + OUT[log.actual_outcome] + "</b>, you were " +
          (o[0] === log.actual_outcome ? "<span style='color:#1f6d6d'>right</span>." : "<span style='color:#a23c28'>wrong</span>.");
        note.html(msg);
      });
    });
  }

  function scoreHeat(sel, f, log) {
    var g = f.grid, N = g.length, cell = 30, pad = 22, S = N * cell;
    var svg = sel.append("svg").attr("viewBox", "0 0 " + (S + pad + 6) + " " + (S + pad + 16)).attr("height", S + pad + 16).attr("width", S + pad + 6);
    var root = svg.append("g").attr("transform", "translate(" + pad + ",6)");
    var max = d3.max(g.flat());
    var best = { p: -1 };
    for (var i = 0; i < N; i++) for (var j = 0; j < N; j++) if (g[i][j] > best.p) best = { p: g[i][j], i: i, j: j };
    for (i = 0; i < N; i++) for (j = 0; j < N; j++) {
      root.append("rect").attr("x", j * cell).attr("y", i * cell).attr("width", cell - 2).attr("height", cell - 2).attr("rx", 3)
        .attr("fill", heat(g[i][j] / max))
        .attr("stroke", (i === best.i && j === best.j) ? INK : "none").attr("stroke-width", 1.5);
    }
    // actual score ring
    if (log && log.actual.h < N && log.actual.a < N) {
      root.append("rect").attr("x", log.actual.a * cell - 1).attr("y", log.actual.h * cell - 1).attr("width", cell).attr("height", cell).attr("rx", 4)
        .attr("fill", "none").attr("stroke", TEAL).attr("stroke-width", 2.5);
    }
    // axis labels
    for (i = 0; i < N; i++) {
      root.append("text").attr("x", -7).attr("y", i * cell + cell / 2 - 1).attr("text-anchor", "end").attr("dy", ".35em")
        .attr("font-family", "JetBrains Mono, monospace").attr("font-size", 9).attr("fill", MUTED).text(i);
      root.append("text").attr("x", i * cell + cell / 2 - 1).attr("y", S + 10).attr("text-anchor", "middle")
        .attr("font-family", "JetBrains Mono, monospace").attr("font-size", 9).attr("fill", MUTED).text(i);
    }
    svg.append("text").attr("x", 4).attr("y", S / 2 + 6).attr("transform", "rotate(-90,8," + (S / 2 + 6) + ")").attr("text-anchor", "middle")
      .attr("font-family", "JetBrains Mono, monospace").attr("font-size", 9).attr("fill", MUTED).text(f.home + " goals");
    svg.append("text").attr("x", pad + S / 2).attr("y", S + pad + 14).attr("text-anchor", "middle")
      .attr("font-family", "JetBrains Mono, monospace").attr("font-size", 9).attr("fill", MUTED).text(f.away + " goals");
  }

  // ── Part II: scorecard, calibration, log ─────────────────────────────────
  function scorecard(B) {
    var sc = B.scorecard, box = d3.select("#fc-scorecard");
    if (!sc.n_played) { d3.select("#fc-warn").text("No results in yet — the scorecard fills as matches are played."); return; }
    d3.select("#fc-warn").html("<b>" + sc.n_played + " matches in.</b> Far too few to judge a forecaster — read these as a running tally, not a verdict. " +
      "Brier and log-loss are scored against a 33/33/33 coin-flip; lower is better.");
    var beat = sc.brier_model < sc.brier_uniform;
    [{ v: sc.n_correct + "<small>/" + sc.n_played + "</small>", k: "results called right" },
     { v: sc.n_exact + "<small>/" + sc.n_played + "</small>", k: "exact scorelines" },
     { v: sc.brier_model, k: "Brier (" + (beat ? "beats" : "trails") + " coin-flip " + sc.brier_uniform + ")" },
     { v: sc.logloss_model, k: "log-loss (vs " + sc.logloss_uniform + ")" }
    ].forEach(function (c) {
      var d = box.append("div").attr("class", "fc-sc");
      d.append("div").attr("class", "v").html(c.v).style("color", typeof c.v === "number" ? INK : INK);
      d.append("div").attr("class", "k").html(c.k);
    });
  }

  function calibration(B) {
    var cal = B.calibration;
    if (!cal || !cal.length) { d3.select("#fc-calib-cap").text(""); return; }
    var W = 320, H = 300, m = 40;
    var svg = d3.select("#fc-calib").append("svg").attr("viewBox", "0 0 " + W + " " + H).attr("height", H).style("max-width", "340px").style("display", "block").style("margin", "0 auto");
    var x = d3.scaleLinear().domain([0, 1]).range([m, W - 14]), y = d3.scaleLinear().domain([0, 1]).range([H - m, 14]);
    svg.append("line").attr("x1", x(0)).attr("y1", y(0)).attr("x2", x(1)).attr("y2", y(1)).attr("stroke", LINE).attr("stroke-dasharray", "4 4");
    [0, 0.5, 1].forEach(function (t) {
      svg.append("text").attr("x", x(t)).attr("y", H - m + 16).attr("text-anchor", "middle").attr("font-family", "JetBrains Mono").attr("font-size", 9).attr("fill", MUTED).text(pct(t));
      svg.append("text").attr("x", m - 8).attr("y", y(t) + 3).attr("text-anchor", "end").attr("font-family", "JetBrains Mono").attr("font-size", 9).attr("fill", MUTED).text(pct(t));
    });
    svg.append("text").attr("x", (m + W) / 2).attr("y", H - 6).attr("text-anchor", "middle").attr("font-size", 10).attr("fill", MUTED).text("model said");
    svg.append("text").attr("x", 12).attr("y", H / 2).attr("transform", "rotate(-90,12," + H / 2 + ")").attr("text-anchor", "middle").attr("font-size", 10).attr("fill", MUTED).text("actually happened");
    cal.forEach(function (c) {
      svg.append("circle").attr("cx", x(c.pred_mean)).attr("cy", y(c.obs_freq)).attr("r", 4 + Math.sqrt(c.n)).attr("fill", AMBER).attr("fill-opacity", .55).attr("stroke", AMBER);
    });
    svg.append("path").attr("d", d3.line().x(function (c) { return x(c.pred_mean); }).y(function (c) { return y(c.obs_freq); })(cal))
      .attr("fill", "none").attr("stroke", AMBER).attr("stroke-width", 1.5);
    d3.select("#fc-calib-cap").html("Each dot is a confidence band (sized by how many predictions fall in it). On the dashed line = perfectly calibrated. Above it, the model was too cautious; below, overconfident. With this little data the curve is noisy by nature.");
  }

  function logTable(B) {
    var tb = d3.select("#fc-logtable tbody");
    B.log.forEach(function (l) {
      var date = new Date(l.date + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
      var probs = pct(l.p_home) + "/" + pct(l.p_draw) + "/" + pct(l.p_away);
      tb.append("tr").html(
        "<td>" + date + "</td><td>" + l.home + " v " + l.away + "</td>" +
        "<td>" + OUT[l.pred] + " <span style='color:" + MUTED + "'>(" + l.likely.h + "–" + l.likely.a + ")</span></td>" +
        "<td class='r'>" + probs + "</td><td class='r'>" + l.actual.h + "–" + l.actual.a + "</td>" +
        "<td class='r " + (l.correct ? "tick" : "cross") + "'>" + (l.correct ? "✓" : "✗") + "</td>");
    });
    var sc = B.scorecard;
    d3.select("#fc-take").text(sc.n_played
      ? "Through " + sc.n_played + " matches the model has called " + sc.n_correct + " results right and sits "
        + (sc.brier_model < sc.brier_uniform ? "just ahead of" : "level with") + " a coin flip — proof that an opening round of upsets humbles even a 150-year model."
      : "The forecast is frozen and waiting — the marking begins as soon as the results land.");
  }

  function findings(B) {
    var f = d3.select("#findings"), sc = B.scorecard;
    [{ h: "Frozen, so it's honest", p: "The model is fit only on matches before <strong>" + B.meta.asof + "</strong>, then never touched — so every call is a true out-of-sample prediction, not hindsight." },
     { h: "Probabilities, not prophecies", p: "A 60% favourite is meant to lose 40% of the time. The piece scores the model on calibration and Brier, not just whether the headline pick came in." },
     { h: "No verdict without N", p: "After <strong>" + sc.n_played + "</strong> games the scoreboard is mostly noise. The honest read comes near the end of the group stage, and the page updates as it gets there." }
    ].forEach(function (c) { var a = f.append("article"); a.append("h3").text(c.h); a.append("p").html(c.p); });
  }

  function boot() {
    d3.json("../data/forecast.json").then(function (B) {
      document.querySelectorAll("[data-fc]").forEach(function (e) { if (B.meta[e.getAttribute("data-fc")] != null) e.textContent = B.meta[e.getAttribute("data-fc")]; });
      fillStats(B); picker(B); scorecard(B); calibration(B); logTable(B); findings(B);
    }).catch(function (e) {
      d3.select("#stats").html("<p style='color:var(--muted)'>Couldn't load the forecast bundle.</p>");
      console.error("forecast:", e);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
