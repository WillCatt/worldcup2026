/* Who Missed Out — hub piece 10. One static missed.json: the strongest non-qualifiers,
   ranked on world ranking / value / Elo, plus a value comparison against the weakest
   teams that did qualify. Vanilla JS, hub palette, no build step. */
(function () {
  "use strict";

  var DATA = null, sortKey = "fifa_rank";

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

  fetch("../data/missed.json").then(function (r) { return r.json(); })
    .then(init)
    .catch(function () {
      document.getElementById("list").innerHTML =
        '<p style="text-align:center;color:var(--muted)">Couldn\'t load the data.</p>';
    });

  function init(d) {
    DATA = d;
    fillStats();
    document.querySelectorAll("#sort button").forEach(function (b) {
      b.onclick = function () {
        sortKey = b.dataset.key;
        document.querySelectorAll("#sort button").forEach(function (x) { x.classList.toggle("on", x === b); });
        renderList();
      };
    });
    renderList();
    renderComparison();
    renderFindings();
  }

  function fillStats() {
    var m = DATA.missed, s = document.getElementById("stats");
    var richest = m.slice().sort(function (a, b) { return (b.value_eur || 0) - (a.value_eur || 0); })[0];
    [{ n: "#" + m[0].fifa_rank, l: "world rank of the top absentee (" + m[0].name + ")" },
     { n: m.length, l: "strong teams watching from home" },
     { n: eur(richest.value_eur), l: "priciest squad that missed (" + richest.name + ")" }
    ].forEach(function (c) {
      var d = el("div", "stat");
      d.appendChild(el("div", "num", c.n));
      d.appendChild(el("div", "lbl", c.l));
      s.appendChild(d);
    });
  }

  function renderList() {
    var box = document.getElementById("list"); box.innerHTML = "";
    var rows = DATA.missed.slice().sort(function (a, b) {
      if (sortKey === "fifa_rank") return a.fifa_rank - b.fifa_rank;
      return (b[sortKey] || 0) - (a[sortKey] || 0);  // value / elo: high first
    });
    var maxVal = Math.max.apply(null, DATA.missed.map(function (x) { return x.value_eur || 0; }));
    rows.forEach(function (r, i) {
      var row = el("div", "mo-row" + (i === 0 ? " top" : ""));
      row.appendChild(el("div", "mo-rank", "#<b>" + r.fifa_rank + "</b>"));

      var id = el("div", "mo-id");
      var titles = r.titles > 0 ? '<span class="mo-title">' + r.titles + "× champion" +
        (r.titles > 1 ? "s" : "") + "</span>" : "";
      id.appendChild(el("div", "mo-name",
        '<span class="flag">' + (r.flag || "") + "</span> " + esc(r.name) + titles));
      var lastWc = typeof r.last_wc === "number" ? "Last WC " + r.last_wc
        : (r.best_finish === "Never qualified" ? "Never reached a World Cup" : "Last WC —");
      var ped = lastWc + (r.best_finish && r.best_finish !== "Never qualified"
        ? " · best: " + esc(r.best_finish) : "");
      if (r.note) ped += ' · <span class="note">' + esc(r.note) + "</span>";
      id.appendChild(el("div", "mo-ped", ped));
      row.appendChild(id);

      var stats = el("div", "mo-stats");
      var vstat = el("div", "mo-stat");
      vstat.innerHTML = '<div class="v">' + eur(r.value_eur) + "</div>" +
        '<div class="mo-valbar"><div style="width:' + (100 * (r.value_eur || 0) / maxVal) + '%"></div></div>';
      var estat = el("div", "mo-stat");
      estat.innerHTML = '<div class="v">' + (r.elo != null ? Math.round(r.elo) : "—") + "</div>" +
        '<div class="k">Elo</div>';
      stats.appendChild(vstat);
      stats.appendChild(estat);
      row.appendChild(stats);
      box.appendChild(row);
    });
  }

  function renderComparison() {
    var box = document.getElementById("cmp"); box.innerHTML = "";
    var missed = DATA.missed.slice()
      .sort(function (a, b) { return (b.value_eur || 0) - (a.value_eur || 0); })
      .slice(0, 8)
      .map(function (m) { return { name: m.name, flag: m.flag, value_eur: m.value_eur, grp: "missed" }; });
    var qual = (DATA.weakest_qualified || []).map(function (q) {
      return { name: q.nation, flag: q.flag, value_eur: q.value_eur, grp: "qual" };
    });
    var all = missed.concat(qual).sort(function (a, b) { return b.value_eur - a.value_eur; });
    var maxV = Math.max.apply(null, all.map(function (x) { return x.value_eur; }));
    all.forEach(function (r) {
      var bar = el("div", "mo-bar " + r.grp);
      bar.innerHTML =
        '<div class="lab"><span class="flag">' + (r.flag || "") + "</span> " + esc(r.name) + "</div>" +
        '<div class="track"><div class="fill" style="width:' + (100 * r.value_eur / maxV) + '%"></div></div>' +
        '<div class="amt">' + eur(r.value_eur) + "</div>";
      box.appendChild(bar);
    });
    var topMiss = missed[0], minQual = qual.slice().sort(function (a, b) { return a.value_eur - b.value_eur; })[0];
    if (topMiss && minQual) {
      document.getElementById("cmp-cap").innerHTML =
        "<strong>" + esc(topMiss.name) + "</strong>'s " + eur(topMiss.value_eur) + " squad stayed home, while " +
        esc(minQual.name) + " qualified with a squad worth " + eur(minQual.value_eur) + " — about " +
        "<strong>" + Math.round(topMiss.value_eur / minQual.value_eur) + "×</strong> less.";
    }
  }

  function renderFindings() {
    var f = document.getElementById("findings");
    var m = DATA.missed;
    var champs = m.filter(function (x) { return x.titles > 0; });
    var never = m.filter(function (x) { return x.best_finish === "Never qualified"; });
    var richest = m.slice().sort(function (a, b) { return (b.value_eur || 0) - (a.value_eur || 0); })[0];
    var cards = [
      ["A four-time champion at home",
        "<strong>" + esc(m[0].name) + "</strong> is the highest-ranked side missing 2026 — world #" +
        m[0].fifa_rank + ", and " + (champs.length ? "the only past winner watching on" : "a former finalist") +
        ". " + (m[0].note ? esc(m[0].note) : "")],
      ["The money left behind",
        "<strong>" + esc(richest.name) + "</strong> fields the priciest absent squad at " +
        eur(richest.value_eur) + " — worth more than several teams that did qualify. Value buys you " +
        "nothing if you finish third in your group."],
      [never.length ? "Strong, but never there" : "Pedigree counts for nothing",
        never.length
          ? "<strong>" + esc(never[0].name) + "</strong>" + (never.length > 1 ? " and " + (never.length - 1) +
            " others" : "") + " rank among the world's best yet have never reached a World Cup — ranking and " +
            "history don't decide qualification, the draw and the route do."
          : "Qualification turns on confederation and group, not a global table — which is why a top-15 side " +
            "can be out while lower-ranked teams are in."]
    ];
    cards.forEach(function (c) {
      var a = el("article");
      a.appendChild(el("h3", null, c[0]));
      a.appendChild(el("p", null, c[1]));
      f.appendChild(a);
    });
  }
})();
