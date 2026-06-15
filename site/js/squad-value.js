/* Squad Value — hub piece. Fetch one static squad_value.json and render the value
   ladder + a fixtures hub where each group game opens to two starting XIs priced by
   Transfermarkt. No build step, no D3 — bars are divs. */
(function () {
  "use strict";

  var AMBER = "#b06a16", TEAL = "#2a8f8f";

  function money(eur) {
    if (!eur) return "—";
    if (eur >= 1e9) return "€" + (eur / 1e9).toFixed(2) + "bn";
    if (eur >= 1e6) return "€" + Math.round(eur / 1e6) + "m";
    return "€" + Math.round(eur / 1e3) + "k";
  }
  function fmtDate(iso) {
    var d = new Date(iso + "T00:00:00Z");
    return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
  }
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }

  function fillStats(B) {
    var total = B.ranking.reduce(function (a, r) { return a + r.squad_value; }, 0);
    var top = B.ranking[0];
    var stats = document.getElementById("stats");
    [{ n: money(total), l: "total market value, all 48 squads" },
     { n: top.flag + " " + money(top.squad_value), l: "richest squad (" + top.nation + ")" },
     { n: Math.round(B.meta.coverage * 100) + "%", l: B.meta.n_valued + " of " + B.meta.n_players + " players priced" }
    ].forEach(function (c) {
      var d = el("div", "stat");
      d.appendChild(el("div", "num", c.n));
      d.appendChild(el("div", "lbl", c.l));
      stats.appendChild(d);
    });
  }

  function renderRanking(B) {
    var box = document.getElementById("rank"), max = B.ranking[0].squad_value;
    B.ranking.forEach(function (r, i) {
      var row = el("div", "sv-rk");
      row.appendChild(el("div", "pos", i + 1));
      row.appendChild(el("div", "flag", r.flag));
      var bw = el("div", "barwrap");
      var bar = el("div", "bar"); bar.style.width = (100 * r.squad_value / max) + "%";
      bw.appendChild(bar);
      bw.appendChild(el("div", "nm", r.nation));
      row.appendChild(bw);
      row.appendChild(el("div", "val", money(r.squad_value)));
      box.appendChild(row);
    });
    var top3 = B.ranking.slice(0, 3).map(function (r) { return r.nation; }).join(", ");
    var bot = B.ranking[B.ranking.length - 1];
    document.getElementById("rank-cap").innerHTML =
      "The top three — <strong>" + top3 + "</strong> — each carry over a billion euros. The poorest squad, " +
      bot.flag + " " + bot.nation + " (" + money(bot.squad_value) + "), is worth roughly " +
      Math.round(B.ranking[0].squad_value / bot.squad_value) + "× less than the richest. Value buys favouritism, not trophies — but it's the cleanest one-number prior we have.";
  }

  function xiRows(nation) {
    var wrap = el("div", "sv-xi");
    var xi = nation.players.filter(function (p) { return p.in_xi; });
    var head = el("h4", null, "Best XI <b>" + money(nation.xi_value) + "</b>");
    wrap.appendChild(head);
    xi.forEach(function (p) {
      var r = el("div", "sv-pl");
      r.appendChild(el("div", "pp", p.pos));
      r.appendChild(el("div", "pn", p.name + " <small>" + p.club + "</small>"));
      r.appendChild(el("div", "pv", money(p.value_eur)));
      wrap.appendChild(r);
    });
    return wrap;
  }

  function renderFixtures(B) {
    var box = document.getElementById("fixtures");
    var nat = B.nations, byDay = {};
    B.fixtures.forEach(function (f) { (byDay[f.date] = byDay[f.date] || []).push(f); });
    Object.keys(byDay).sort().forEach(function (date) {
      var grp = el("div", "sv-daygrp");
      grp.appendChild(el("div", "sv-day", fmtDate(date)));
      byDay[date].forEach(function (f) {
        var h = nat[f.home] || {}, a = nat[f.away] || {};
        var tot = (f.home_xi + f.away_xi) || 1;
        var card = el("div", "sv-fx");
        var head = el("div", "sv-fxhead");
        head.appendChild(el("div", "sv-side home",
          "<span class='flag'>" + (h.flag || "") + "</span><span><div class='tn'>" + f.home +
          "</div><div class='xv'>" + money(f.home_xi) + "</div></span>"));
        head.appendChild(el("div", "sv-grp", "Group " + f.group + "<br>vs"));
        head.appendChild(el("div", "sv-side away",
          "<span><div class='tn'>" + f.away + "</div><div class='xv'>" + money(f.away_xi) +
          "</div></span><span class='flag'>" + (a.flag || "") + "</span>"));
        card.appendChild(head);
        var vbar = el("div", "sv-vbar");
        var hh = el("div", "h"); hh.style.width = (100 * f.home_xi / tot) + "%";
        var aa = el("div", "a"); aa.style.width = (100 * f.away_xi / tot) + "%";
        vbar.appendChild(hh); vbar.appendChild(aa);
        card.appendChild(vbar);
        var detail = el("div", "sv-detail");
        var xis = el("div", "sv-xis");
        if (h.players) xis.appendChild(xiRows(h));
        if (a.players) xis.appendChild(xiRows(a));
        detail.appendChild(xis);
        var gap = Math.abs(f.home_xi - f.away_xi);
        var rich = f.home_xi >= f.away_xi ? f.home : f.away;
        detail.appendChild(el("div", "sv-fxnote",
          "Best-XI gap: " + money(gap) + " in favour of " + rich +
          " · " + f.venue + " · best XI = top GK plus the ten most valuable outfielders"));
        card.appendChild(detail);
        card.addEventListener("click", function () { card.classList.toggle("open"); });
        grp.appendChild(card);
      });
      box.appendChild(grp);
    });
  }

  function findings(B) {
    var f = document.getElementById("findings"), r = B.ranking;
    var top = r[0], gap = Math.round(r[0].squad_value / r[r.length - 1].squad_value);
    [{ h: "Money is top-heavy", p: "Just three squads — " + r.slice(0, 3).map(function (x) { return x.nation; }).join(", ") +
        " — clear a billion euros each, while the bottom half of the field shares a fraction of that. Top to bottom spans about <strong>" + gap + "×</strong>." },
     { h: "Value ≠ who starts", p: "Best XI here means most <em>valuable</em>, which rewards youth and potential — so a €30m prospect keeper can edge a veteran starter. It's a market prior, not a team-sheet." },
     { h: "Honest coverage", p: "<strong>" + Math.round(B.meta.coverage * 100) + "%</strong> of squad players matched a current Transfermarkt value; the rest (mostly home-league names) are shown unvalued rather than guessed." }
    ].forEach(function (c) { var a = document.createElement("article"); a.appendChild(el("h3", null, c.h)); a.appendChild(el("p", null, c.p)); f.appendChild(a); });
  }

  function fillPlaceholders(B) {
    var v = { n_valued: B.meta.n_valued, n_players: B.meta.n_players };
    document.querySelectorAll("[data-sv]").forEach(function (e) {
      var k = e.getAttribute("data-sv"); if (v[k] != null) e.textContent = v[k];
    });
  }

  function boot() {
    fetch("../data/squad_value.json").then(function (r) { return r.json(); }).then(function (B) {
      fillStats(B); fillPlaceholders(B); renderRanking(B); renderFixtures(B); findings(B);
    }).catch(function (e) {
      document.getElementById("stats").innerHTML = "<p style='color:var(--muted)'>Couldn't load the data bundle.</p>";
      console.error("squad-value:", e);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
