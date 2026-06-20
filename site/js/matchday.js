/* Matchday — hub piece 09. One static matchday.json: today's (or the next) fixtures,
   each opened into a full preview — model call, both value-ranked XIs on a pitch,
   managers, form, and tournament-so-far. Vanilla JS, hub palette, no build step. */
(function () {
  "use strict";

  var DATA = null, dates = [], windowDate = null, sel = null;
  var WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var POS_ORDER = ["Goalkeepers", "Defenders", "Midfielders", "Forwards"];
  var POS_SHORT = { Goalkeepers: "GK", Defenders: "DF", Midfielders: "MF", Forwards: "FW" };

  function pct(x) { return x == null || isNaN(x) ? "—" : Math.round(100 * x) + "%"; }
  function eur(v) {
    if (v == null || !v) return "—";
    return v >= 1e9 ? "€" + (v / 1e9).toFixed(2) + "bn" : "€" + Math.round(v / 1e6) + "m";
  }
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function lastName(n) { var p = String(n || "").split(" "); return p[p.length - 1]; }
  function fmtDate(iso) {
    var d = new Date(iso + "T00:00:00Z");
    return WEEKDAY[d.getUTCDay()] + " " + d.getUTCDate() + " " + MONTH[d.getUTCMonth()];
  }
  function todayISO() {
    var n = new Date();
    return n.getFullYear() + "-" + String(n.getMonth() + 1).padStart(2, "0") + "-" +
      String(n.getDate()).padStart(2, "0");
  }
  function isUpcoming(f) { return f.status !== "done"; }
  function team(name) { return (DATA.teams || {})[name] || {}; }

  // ── boot ────────────────────────────────────────────────────────────────────
  fetch("../data/matchday.json").then(function (r) { return r.json(); })
    .then(init)
    .catch(function () {
      document.getElementById("md-preview").innerHTML =
        '<p class="md-empty">Couldn\'t load the matchday data.</p>';
    });

  function init(d) {
    DATA = d;
    dates = Array.from(new Set(d.fixtures.map(function (f) { return f.date; }))).sort();
    fillStats();
    windowDate = computeWindow();
    bindNav();
    document.getElementById("md-methodtext").innerHTML =
      "The model is the project's Dixon-Coles goals model, <b>frozen the day before the tournament</b> " +
      "(" + esc(d.meta.asof_model) + ") — so every match call here is a genuine pre-tournament prediction, " +
      "the same engine behind the Forecast piece. The two elevens are <b>value-ranked</b> (top goalkeeper " +
      "plus the ten most valuable outfielders, from Transfermarkt) — a strength proxy, <b>not a tactical " +
      "lineup prediction</b>, so a fixture's true XI may differ. Form is each side's last five internationals " +
      "before kickoff (martj42 history); the tournament line is computed live from results. " +
      "<b>What's missing, honestly:</b> there is no clean, free source for per-player minutes at this " +
      "World Cup — the live feed carries results and goal events only, not lineups — so player detail is " +
      "career caps, goals, club and market value, plus any goals scored at this tournament.";
    selectDate(windowDate);
  }

  function fillStats() {
    var s = document.getElementById("stats");
    var inWin = DATA.fixtures.filter(function (f) { return f.date === computeWindow(); }).length;
    [{ n: inWin, l: "games on the card" },
     { n: DATA.meta.n_played + "<small>/" + DATA.meta.n_fixtures + "</small>", l: "group games played" },
     { n: 48, l: "squads, fully priced" }
    ].forEach(function (c) {
      var d = el("div", "stat");
      d.appendChild(el("div", "num", c.n));
      d.appendChild(el("div", "lbl", c.l));
      s.appendChild(d);
    });
  }

  // pick the matchday to open on: today if it has an unplayed game, else the next
  // date with fixtures; clamp to the tournament window for out-of-range visitors.
  function computeWindow() {
    var ref = todayISO();
    if (ref < dates[0]) return dates[0];
    if (ref > dates[dates.length - 1]) return dates[dates.length - 1];
    var onRef = DATA.fixtures.filter(function (f) { return f.date === ref; });
    if (onRef.length && onRef.some(isUpcoming)) return ref;
    var nxt = dates.filter(function (dd) { return dd > ref; })[0];
    return nxt || dates[dates.length - 1];
  }

  function bindNav() {
    document.getElementById("md-prev").onclick = function () { stepDay(-1); };
    document.getElementById("md-next").onclick = function () { stepDay(1); };
  }
  function stepDay(dir) {
    var i = dates.indexOf(windowDate) + dir;
    if (i < 0 || i >= dates.length) return;
    selectDate(dates[i]);
  }

  function whenLabel(date) {
    var ref = todayISO();
    var di = dates.indexOf(date);
    if (date === ref) return "Today";
    // tomorrow relative to real today
    var t = new Date(ref + "T00:00:00Z"); t.setUTCDate(t.getUTCDate() + 1);
    var tomorrow = t.toISOString().slice(0, 10);
    if (date === tomorrow) return "Tomorrow";
    return di === 0 ? "Opening day" : di === dates.length - 1 ? "Final group day" : "Matchday";
  }

  function selectDate(date) {
    windowDate = date;
    document.getElementById("md-prev").disabled = dates.indexOf(date) <= 0;
    document.getElementById("md-next").disabled = dates.indexOf(date) >= dates.length - 1;
    document.getElementById("md-when").textContent = whenLabel(date);
    document.getElementById("md-date").textContent = fmtDate(date);
    var fx = DATA.fixtures.filter(function (f) { return f.date === date; })
      .sort(function (a, b) { return (a.kickoff || "").localeCompare(b.kickoff || "") || a.group.localeCompare(b.group); });
    renderCards(fx);
    var def = fx.filter(isUpcoming)[0] || fx[0];
    if (def) selectFixture(def, fx);
    else document.getElementById("md-preview").innerHTML =
      '<p class="md-empty">No fixtures on this date.</p>';
  }

  function renderCards(fx) {
    var box = document.getElementById("md-cards"); box.innerHTML = "";
    fx.forEach(function (f) {
      var c = el("div", "md-card");
      c.dataset.key = f.home + "|" + f.away;
      var th = team(f.home), ta = team(f.away);
      c.appendChild(el("div", "teams",
        '<span class="flag">' + (th.flag || "") + "</span> " + esc(f.home) +
        ' <span style="color:var(--muted)">v</span> ' + esc(f.away) +
        ' <span class="flag">' + (ta.flag || "") + "</span>"));
      var right = f.status === "done" && f.score
        ? '<span class="sc">' + f.score.h + "–" + f.score.a + "</span>"
        : (f.model && f.model.p_home != null ? favLabel(f) : "");
      c.appendChild(el("div", "meta",
        "<span>" + esc(f.kickoff || ("Grp " + f.group)) + "</span><span>" + right + "</span>"));
      c.onclick = function () { selectFixture(f, fx); };
      box.appendChild(c);
    });
  }
  function favLabel(f) {
    var m = f.model, best = Math.max(m.p_home, m.p_draw, m.p_away);
    var who = best === m.p_home ? f.home : best === m.p_away ? f.away : "draw";
    return esc(who === "draw" ? "draw" : lastName(who)) + " " + pct(best);
  }

  function selectFixture(f, fx) {
    sel = f;
    Array.prototype.forEach.call(document.querySelectorAll(".md-card"), function (c) {
      c.classList.toggle("sel", c.dataset.key === f.home + "|" + f.away);
    });
    renderPreview(f);
  }

  // ── the preview ───────────────────────────────────────────────────────────────
  function renderPreview(f) {
    var box = document.getElementById("md-preview"); box.innerHTML = "";
    var th = team(f.home), ta = team(f.away);

    // header
    var head = el("div", "md-head");
    head.appendChild(teamHead(f.home, th, false));
    var center = el("div", "md-center");
    if (f.status === "done" && f.score) {
      center.innerHTML = '<div class="ko">' + esc(f.kickoff || "") + " · Grp " + f.group + "</div>" +
        '<div class="score">' + f.score.h + "–" + f.score.a + "</div>" +
        '<span class="md-badge done">full time</span>';
    } else {
      center.innerHTML = '<div class="ko">' + esc(f.kickoff || "") + " · Grp " + f.group + "</div>" +
        '<div class="vs">v</div><span class="md-badge upcoming">upcoming</span>';
    }
    head.appendChild(center);
    head.appendChild(teamHead(f.away, ta, true));
    box.appendChild(head);
    box.appendChild(el("p", "md-venue", esc(f.venue || f.ground || "")));

    if (f.status === "done" && f.scorers) box.appendChild(scorerLine(f));

    // model strip
    if (f.model && f.model.p_home != null) box.appendChild(modelStrip(f));

    // dossiers
    var dos = el("div", "md-dossier");
    dos.appendChild(dossier(f.home, th));
    dos.appendChild(dossier(f.away, ta));
    box.appendChild(dos);

    // pitch
    box.appendChild(pitchPanel(f, th, ta));

    // full squads
    var sq = el("div", "md-squads");
    sq.appendChild(squadList(f.home, th));
    sq.appendChild(squadList(f.away, ta));
    box.appendChild(sq);
  }

  function teamHead(name, t, away) {
    var d = el("div", "md-team" + (away ? " away" : ""));
    d.appendChild(el("span", "flag", t.flag || ""));
    var box = el("div");
    box.appendChild(el("div", "nm", esc(name)));
    box.appendChild(el("div", "mgr", t.manager ? "Mgr · <b>" + esc(t.manager) + "</b>" : ""));
    d.appendChild(box);
    return d;
  }

  function scorerLine(f) {
    function side(list, who) {
      if (!list || !list.length) return "";
      return "<b>" + esc(who) + ":</b> " + list.map(function (g) {
        return esc(g.name) + (g.minute ? " " + esc(g.minute) + "'" : "");
      }).join(", ");
    }
    var parts = [side(f.scorers.home, f.home), side(f.scorers.away, f.away)].filter(Boolean);
    return el("p", "md-scorers", parts.length
      ? '<div style="text-align:center">⚽ ' + parts.join(" &nbsp;·&nbsp; ") + "</div>" : "");
  }

  function modelStrip(f) {
    var m = f.model, wrap = el("div", "md-model");
    wrap.appendChild(el("h4", null, "Model call — frozen before kickoff"));
    var bar = el("div", "md-bar");
    [["h", m.p_home], ["d", m.p_draw], ["a", m.p_away]].forEach(function (seg) {
      var w = (100 * seg[1]).toFixed(1) + "%";
      var d = el("div", seg[0], (seg[1] >= 0.1 ? pct(seg[1]) : ""));
      d.style.width = w; bar.appendChild(d);
    });
    wrap.appendChild(bar);
    wrap.appendChild(el("div", "md-barlbl",
      "<span>" + esc(f.home) + " win</span><span>draw</span><span>" + esc(f.away) + " win</span>"));
    var xg = el("div", "md-xg");
    xg.innerHTML = "expected goals &nbsp; <b>" + (m.exp_home != null ? m.exp_home.toFixed(1) : "—") +
      "</b> &nbsp;–&nbsp; <b>" + (m.exp_away != null ? m.exp_away.toFixed(1) : "—") + "</b>" +
      (m.top_score ? '<span style="margin-left:18px">most likely &nbsp;<b>' +
        m.top_score.h + "–" + m.top_score.a + "</b> (" + pct(m.top_score.p) + ")</span>" : "");
    wrap.appendChild(xg);
    return wrap;
  }

  function dossier(name, t) {
    var d = el("div", "md-dos");
    d.appendChild(el("div", "dos-team", '<span style="font-size:18px">' + (t.flag || "") +
      "</span> " + esc(name)));
    // form
    var rf = t.recent_form || { games: [], w: 0, d: 0, l: 0 };
    var chips = rf.games.map(function (g) {
      return '<span class="fchip ' + g.res + '" title="' + esc(g.date) + " v " + esc(g.opp) +
        " " + g.gf + "-" + g.ga + '">' + g.res + "</span>";
    }).join("");
    var formRow = el("div", "dos-row");
    formRow.innerHTML = '<span class="k">Form coming in</span>' +
      '<div class="md-form">' + (chips || '<span class="ftext">no recent matches</span>') +
      '<span class="ftext">W' + rf.w + " D" + rf.d + " L" + rf.l + "</span></div>";
    var last = rf.games.slice(-3).reverse().map(function (g) {
      return (g.res === "W" ? "✓ " : g.res === "L" ? "✗ " : "= ") + g.gf + "–" + g.ga + " v " + esc(g.opp);
    }).join(" · ");
    if (last) formRow.appendChild(el("div", "md-results", last));
    d.appendChild(formRow);
    // tournament so far
    var tr = el("div", "dos-row");
    if (t.tournament) {
      tr.innerHTML = '<span class="k">This tournament</span><div class="md-tour"><span class="summ">' +
        esc(t.tournament.summary) + "</span></div>";
      if (t.tournament.scorers && t.tournament.scorers.length)
        tr.appendChild(el("div", "md-scorers", "Scorers: " + t.tournament.scorers.map(function (g) {
          return esc(g.name) + (g.minute ? " " + esc(g.minute) + "'" : "");
        }).join(", ")));
    } else {
      tr.innerHTML = '<span class="k">This tournament</span><div class="md-tour" style="color:var(--muted)">Yet to play.</div>';
    }
    d.appendChild(tr);
    // value
    d.appendChild(el("div", "dos-row",
      '<span class="k">Squad value · best XI</span>' + eur(t.squad_value) + " · " + eur(t.xi_value) +
      ' <span style="color:var(--muted)">(' + (t.n_valued || 0) + "/" + (t.n_players || 0) + " priced)</span>"));
    return d;
  }

  // ── the pitch (both value-ranked XIs facing off) ──────────────────────────────
  function xiByLine(t) {
    var xi = (t.players || []).filter(function (p) { return p.in_xi; });
    var lines = { Goalkeepers: [], Defenders: [], Midfielders: [], Forwards: [] };
    xi.forEach(function (p) { (lines[p.pos_group] || lines.Midfielders).push(p); });
    return lines;
  }
  function pitchPanel(f, th, ta) {
    var wrap = el("div", "md-pitchwrap");
    wrap.appendChild(el("div", "md-section-h", "Likely elevens — value-ranked"));
    var W = 1000, H = 560;
    var svg = '<svg class="md-pitch" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Pitch with both value-ranked elevens">';
    // turf + markings
    svg += '<rect x="0" y="0" width="' + W + '" height="' + H + '" rx="14" fill="#eef3ec"/>';
    svg += '<rect x="14" y="14" width="' + (W - 28) + '" height="' + (H - 28) + '" rx="8" fill="none" stroke="#cdd9c8" stroke-width="2"/>';
    svg += '<line x1="' + (W / 2) + '" y1="14" x2="' + (W / 2) + '" y2="' + (H - 14) + '" stroke="#cdd9c8" stroke-width="2"/>';
    svg += '<circle cx="' + (W / 2) + '" cy="' + (H / 2) + '" r="60" fill="none" stroke="#cdd9c8" stroke-width="2"/>';
    svg += '<rect x="14" y="' + (H / 2 - 110) + '" width="120" height="220" fill="none" stroke="#cdd9c8" stroke-width="2"/>';
    svg += '<rect x="' + (W - 134) + '" y="' + (H / 2 - 110) + '" width="120" height="220" fill="none" stroke="#cdd9c8" stroke-width="2"/>';
    svg += sidePlayers(xiByLine(th), false, W, H, "var(--amber)");
    svg += sidePlayers(xiByLine(ta), true, W, H, "var(--accent)");
    svg += "</svg>";
    wrap.appendChild(el("div", null, svg));

    // value mismatch bar
    var hv = th.xi_value || 0, av = ta.xi_value || 0, tot = hv + av || 1;
    var vm = el("div", "md-vmis");
    vm.innerHTML = '<div class="md-vbar"><div class="h" style="width:' + (100 * hv / tot) +
      '%"></div><div class="a" style="width:' + (100 * av / tot) + '%"></div></div>' +
      '<div class="md-vlbl"><span><b>' + eur(hv) + "</b> " + esc(f.home) + " XI</span>" +
      "<span>" + esc(f.away) + " XI <b>" + eur(av) + "</b></span></div>";
    wrap.appendChild(vm);
    return wrap;
  }
  function sidePlayers(lines, away, W, H, color) {
    // column x positions from each team's own goal toward the centre
    var cols = away ? { Goalkeepers: .955, Defenders: .80, Midfielders: .655, Forwards: .53 }
                    : { Goalkeepers: .045, Defenders: .20, Midfielders: .345, Forwards: .47 };
    var out = "";
    POS_ORDER.forEach(function (grp) {
      var ps = lines[grp] || [], n = ps.length;
      ps.forEach(function (p, i) {
        var cx = cols[grp] * W;
        var cy = (H - 36) * (i + 1) / (n + 1) + 18;
        var nm = lastName(p.name);
        out += '<g><circle cx="' + cx.toFixed(0) + '" cy="' + cy.toFixed(0) + '" r="15" fill="' +
          color + '" stroke="#fff" stroke-width="2"><title>' + esc(p.name) + " — " + esc(p.pos) +
          ", " + esc(p.club) + " · " + (p.caps || 0) + " caps" +
          (p.goals != null ? ", " + p.goals + " gls" : "") + " · " + eur(p.value_eur) + "</title></circle>";
        out += '<text class="md-pl-name" x="' + cx.toFixed(0) + '" y="' + (cy - 22).toFixed(0) +
          '" text-anchor="middle" font-size="15" fill="#1a1714">' + esc(nm) + "</text>";
        out += '<text class="md-pl-val" x="' + cx.toFixed(0) + '" y="' + (cy + 30).toFixed(0) +
          '" text-anchor="middle" font-size="12" fill="#7a6e63">' + eur(p.value_eur) + "</text></g>";
      });
    });
    return out;
  }

  function squadList(name, t) {
    var d = el("div", "md-sq");
    var players = (t.players || []);
    d.appendChild(el("h4", null, '<span>' + (t.flag || "") + " " + esc(name) +
      "</span><b>" + (t.n_players || players.length) + "</b>"));
    // XI first (value order already), then bench
    var xi = players.filter(function (p) { return p.in_xi; });
    var bench = players.filter(function (p) { return !p.in_xi; });
    xi.concat(bench).forEach(function (p) {
      var row = el("div", "md-pl " + (p.in_xi ? "xi" : "bench"));
      row.innerHTML = '<span class="pp">' + (POS_SHORT[p.pos_group] || p.pos) + "</span>" +
        '<span class="pn">' + esc(p.name) + " <small>" + esc(p.club) +
        " · " + (p.caps || 0) + "c" + (p.goals != null ? "/" + p.goals + "g" : "") + "</small></span>" +
        '<span class="pv">' + eur(p.value_eur) + "</span>";
      d.appendChild(row);
    });
    return d;
  }
})();
