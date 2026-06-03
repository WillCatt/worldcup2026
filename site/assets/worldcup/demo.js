/* World Cup 2026 — live forecast dashboard.
 * Renders the genuine model output: forecast.json (the 50k-sim result, regenerated
 * daily by a GitHub Action) and market.json (de-vigged Australian bookmaker odds).
 * No server, no API — it just draws the numbers the model committed.
 *
 * Self-initialises via a MutationObserver so it never touches the shared
 * project-page.js: when #wc-demo is swapped into the App tab, it fetches once and renders.
 */
(function () {
  "use strict";
  const FORECAST = "../assets/worldcup/forecast.json";
  const MARKET = "../assets/worldcup/market.json";

  let DATA = null;          // { forecast, market }
  let loading = null;
  const STATE = { mode: "title", selected: null };

  const esc = s => String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const pct = x => (x * 100).toFixed(1) + "%";
  const STAGES = [
    ["advance", "Out of group"], ["R16", "Round of 16"], ["QF", "Quarter-final"],
    ["SF", "Semi-final"], ["final", "Final"], ["win", "Champions"],
  ];

  // ---------- rendering ----------
  function statusBar(fc) {
    const played = fc.matches_played || 0;
    const when = (fc.generated_at || "").replace("T", " ").replace("Z", " UTC");
    const phase = played === 0
      ? "Pre-tournament forecast"
      : `${played} of 104 matches played`;
    return `<div class="wc-status">
      <span><span class="wc-dot"></span>${esc(phase)}</span>
      <span>·</span><span>${fc.n_sims.toLocaleString()} simulations</span>
      <span>·</span><span>updated ${esc(when)}</span>
      <span>·</span><span>refreshes daily</span>
    </div>`;
  }

  function controls() {
    const b = (k, label) => `<button data-mode="${k}" class="${STATE.mode === k ? "active" : ""}">${label}</button>`;
    return `<div class="wc-toggle">${b("title", "Title race")}${b("market", "vs Market")}</div>`;
  }

  function titleView(fc) {
    const teams = Object.entries(fc.teams).slice(0, 18);
    const max = teams[0][1].win || 1;
    const rows = teams.map(([name, r], i) => {
      const w = (r.win / max) * 100;
      return `<div class="wc-row ${STATE.selected === name ? "sel" : ""}" data-team="${esc(name)}">
        <div class="wc-name">${esc(name)}<span class="wc-grp">${esc(r.group_of)}</span></div>
        <div class="wc-track"><div class="wc-fill ${i === 0 ? "lead" : ""}" style="width:${w}%"></div></div>
        <div class="wc-val">${pct(r.win)}</div>
      </div>`;
    }).join("");
    return `<div class="wc-bars">${rows}</div>`;
  }

  function marketView(fc, mk) {
    // Top teams by market probability; show model vs market side by side.
    const implied = mk.implied || {};
    const rows = Object.entries(implied)
      .sort((a, b) => b[1] - a[1]).slice(0, 16);
    const max = Math.max(...rows.map(([t, m]) => Math.max(m, (fc.teams[t] || {}).win || 0)));
    const body = rows.map(([name, market]) => {
      const model = (fc.teams[name] || {}).win || 0;
      return `<div class="wc-row ${STATE.selected === name ? "sel" : ""}" data-team="${esc(name)}">
        <div class="wc-name">${esc(name)}</div>
        <div class="wc-track dual">
          <div class="wc-mini"><i class="model" style="width:${(model / max) * 100}%"></i></div>
          <div class="wc-mini"><i class="market" style="width:${(market / max) * 100}%"></i></div>
        </div>
        <div class="wc-val">${model > market ? "+" : ""}${((model - market) * 100).toFixed(1)}</div>
      </div>`;
    }).join("");
    return `<div class="wc-legend"><span class="lg-model">model</span><span class="lg-market">market (de-vigged)</span>
        <span style="margin-left:auto">overround ${(mk.overround * 100).toFixed(0)}%</span></div>
      <div class="wc-bars">${body}</div>`;
  }

  function pathPanel(fc) {
    const name = STATE.selected;
    if (!name || !fc.teams[name]) return "";
    const r = fc.teams[name];
    const steps = STAGES.map(([key, label]) => {
      const p = r[key] || 0;
      return `<div class="wc-step">
        <div class="wc-stage">${label}</div>
        <div class="wc-track"><div class="wc-fill ${key === "win" ? "win" : ""}" style="width:${p * 100}%"></div></div>
        <div class="wc-p">${pct(p)}</div>
      </div>`;
    }).join("");
    return `<div class="wc-path">
      <h4>${esc(name)} <span style="color:var(--text-dim);font-weight:400">· Group ${esc(r.group_of)}</span></h4>
      <div class="wc-sub">Probability of reaching each stage</div>
      <div class="wc-ladder">${steps}</div>
      <div class="wc-note">Conditioned on results so far; recomputed daily.</div>
    </div>`;
  }

  function render(el) {
    const { forecast, market } = DATA;
    if (!STATE.selected) STATE.selected = Object.keys(forecast.teams)[0];
    const view = STATE.mode === "market" ? marketView(forecast, market) : titleView(forecast);
    el.innerHTML = statusBar(forecast) + controls() + view + pathPanel(forecast);

    el.querySelectorAll("[data-mode]").forEach(b =>
      b.addEventListener("click", () => { STATE.mode = b.dataset.mode; render(el); }));
    el.querySelectorAll("[data-team]").forEach(row =>
      row.addEventListener("click", () => { STATE.selected = row.dataset.team; render(el); }));
  }

  // ---------- load + init ----------
  async function ensureData() {
    if (DATA) return DATA;
    if (!loading) loading = Promise.all([
      fetch(FORECAST).then(r => r.json()),
      fetch(MARKET).then(r => r.json()).catch(() => ({ implied: {}, overround: 0 })),
    ]).then(([forecast, market]) => (DATA = { forecast, market }));
    return loading;
  }

  async function init(el) {
    el.innerHTML = `<p class="wc-loading">Loading the live forecast…</p>`;
    try { await ensureData(); render(el); }
    catch (e) { el.innerHTML = `<p class="wc-loading">Could not load the forecast. ${esc(String(e))}</p>`; }
  }

  if (typeof document !== "undefined") {
    const obs = new MutationObserver(() => {
      const el = document.getElementById("wc-demo");
      if (el && !el.dataset.ready) { el.dataset.ready = "1"; init(el); }
    });
    obs.observe(document.body, { childList: true, subtree: true });
    const initial = document.getElementById("wc-demo");
    if (initial && !initial.dataset.ready) { initial.dataset.ready = "1"; init(initial); }
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { STAGES };  // for a node smoke test
  }
})();
