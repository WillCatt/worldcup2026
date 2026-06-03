// project-page.js — shared loader for project detail pages
// Reads window.PROJECT + <template> tags, renders header + tabs

(function () {
  const P = window.PROJECT;
  if (!P) { console.error("window.PROJECT not defined"); return; }
  document.title = `${P.title} · William Catt`;

  const root = document.getElementById("root");
  const statusLabel = P.status === "live" ? "LIVE" : P.status === "wip" ? "IN PROGRESS" : "ARCHIVED";

  // Tabs are template-driven: render a tab for whichever <template id="tab-*">
  // blocks exist on the page, in this canonical order. A page can therefore
  // expose any subset — e.g. a single WRITE-UP, or split OVERVIEW/TECHNICAL.
  // The APP tab is additionally gated on P.demo (set demo:false to hide it).
  const TAB_LABELS = {
    overview:  "OVERVIEW",
    writeup:   "WRITE-UP",
    technical: "TECHNICAL",
    results:   "RESULTS",
    examples:  "WORKED EXAMPLES",
    code:      "CODE",
    app:       "APP",
    raw:       "RAW RESULTS",
  };
  const tabsAvailable = ["overview", "writeup", "technical", "results", "examples", "code", "app", "raw"]
    .filter(key => document.getElementById(`tab-${key}`))
    .filter(key => key !== "app" || P.demo !== false)
    .map(key => ({ key, label: TAB_LABELS[key] }));

  root.innerHTML = `
    <div class="page">
      <div class="topbar">
        <a href="../index.html" style="color: var(--accent); font-size: 13px;">william_catt<span style="opacity:0.4">.portfolio</span></a>
        <a href="../all-projects.html">← all projects</a>
      </div>

      <header class="proj-header">
        <div class="proj-index" style="color:${P.color}">${P.index}</div>
        <h1 class="proj-title">${P.title}</h1>
        <p class="proj-subtitle">${P.subtitle}</p>
        <div class="proj-meta">
          <span class="status-pill ${P.status}">
            <span class="status-dot ${P.status}"></span>${statusLabel}
          </span>
          <div class="proj-tags">
            ${P.tags.map(t => `<span class="proj-tag">${t}</span>`).join("")}
          </div>
        </div>
      </header>

      <nav class="tabs" id="tabs">
        ${tabsAvailable.map((t, i) => `<button class="tab${i === 0 ? " active" : ""}" data-tab="${t.key}">${t.label}</button>`).join("")}
      </nav>

      <div id="tab-content"></div>
    </div>
  `;

  const tabContent = document.getElementById("tab-content");
  const tabButtons = document.querySelectorAll(".tab");

  // Highlight redaction tokens like [PERSON], [ORG_A] inside example output
  // blocks only (class .anon-out), so the Code tab is never touched.
  function highlightTokens(scope) {
    scope.querySelectorAll(".anon-out").forEach(el => {
      el.innerHTML = el.innerHTML.replace(/\[[A-Z][A-Z0-9_]*\]/g, '<mark class="tok">$&</mark>');
    });
  }

  function showTab(key) {
    tabButtons.forEach(b => b.classList.toggle("active", b.dataset.tab === key));
    const tpl = document.getElementById(`tab-${key}`);
    tabContent.innerHTML = "";
    if (tpl) tabContent.appendChild(tpl.content.cloneNode(true));
    highlightTokens(tabContent);
  }

  const tabsNav = document.getElementById("tabs");
  tabButtons.forEach(b => b.addEventListener("click", () => {
    showTab(b.dataset.tab);
    // Reset the viewport to the top of the tab bar so a switched-to tab starts
    // at its beginning, rather than wherever the previous tab was scrolled to.
    tabsNav.scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  const requestedTab = new URLSearchParams(window.location.search).get("tab")
    || window.location.hash.replace(/^#/, "");
  const initialTab = tabsAvailable.some(t => t.key === requestedTab)
    ? requestedTab
    : tabsAvailable[0].key;
  showTab(initialTab);  // initial render — no scroll on load
})();
