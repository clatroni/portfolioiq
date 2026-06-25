// Portfolio IQ — demo site behavior
// Pure vanilla JS, no dependencies. Renders inline dashboard from real data, then
// drives the button → animated overlay → result reveal flow.

(() => {
  "use strict";

  // ----- Real portfolio data (pulled from Agent ①'s outputs · January 2026) -----
  const DATA = {
    // Each tile: value + label + sub + accent + optional delta vs prior period + optional filter
    // `filter` maps the click to one of: 'all' | 'Red' | 'Amber' | 'overdue' | null (not clickable)
    tiles: [
      { value: 201,     label: "Total projects", sub: "100 active · 101 pending",        accent: "green", delta: { v: "+5",  dir: "flat" }, filter: "all"     },
      { value: 25,      label: "Completed",      sub: "lifetime",                          accent: "green", delta: { v: "+3",  dir: "good" }, filter: null      },
      { value: 12,      label: "Overdue",        sub: "12% of active",                     accent: "red",   delta: { v: "+2",  dir: "bad"  }, filter: "overdue" },
      { value: "€39.4M",label: "Committed budget", sub: "€21.5M active · €18.0M pending", accent: "green", delta: { v: "−€0.8M", dir: "flat" }, filter: null   },
      { value: "16.5%", label: "YTD Spend",      sub: "€6.5M of €39.4M",                  accent: "amber", delta: { v: "+4.2pp", dir: "good" }, filter: null   },
    ],
    schedule: [
      { label: "On Track",      value: 19, color: "green" },
      { label: "Delayed ≤20%",  value: 1,  color: "amber" },
      { label: "Delayed >20%",  value: 22, color: "red"   },
      { label: "No Baseline",   value: 58, color: "grey"  },
    ],
    budget: [
      { label: "Long Term Maintenance", value_m: 21.5, pct: 54, color: "#86BC25" },
      { label: "Financial Performance", value_m: 13.4, pct: 34, color: "#5A8000" },
      { label: "Betterment",            value_m: 3.9,  pct: 10, color: "#ED8B00" },
      { label: "Safety / Regulatory",   value_m: 0.7,  pct: 2,  color: "#005EB8" },
    ],
    projects: [
      {rag:"Red",  code:"2025-00144", project:"ST Hydraulic Pumps Replacement",                                                       owner:"Thisvi",            go_live:"TBD",      budget:"€168k", pct:5 },
      {rag:"Red",  code:"2025-00040", project:"myElpedison Redesign/Relauch Phase 1 (MVP) Design",                                    owner:"Commercial",        go_live:"Dec 2025", budget:"€0",    pct:5 },
      {rag:"Red",  code:"2025-00159", project:"3D HRSG Scanning",                                                                     owner:"Technical Services",go_live:"Dec 2025", budget:"€0",    pct:0 },
      {rag:"Red",  code:"2025-00095", project:"Strategic spare parts (pending GT turning gear, GT and ST Gen VT/CT)",                 owner:"Thessaloniki",      go_live:"Sep 2024", budget:"€0",    pct:95},
      {rag:"Amber",code:"2025-00127", project:"Steam Turbine Major Inspection",                                                       owner:"Thessaloniki",      go_live:"Jan 2027", budget:"€4.5M", pct:5 },
      {rag:"Amber",code:"2025-00164", project:"TIL001121 Auto Tune System Installation at Thisvi Plant",                              owner:"Thisvi",            go_live:"TBD",      budget:"€500k", pct:10},
      {rag:"Amber",code:"2025-00188", project:"Replacement of High Pressure (HP) and Hot Reheat (HRH) Steam turbine valves",          owner:"Thessaloniki",      go_live:"Feb 2026", budget:"€360k", pct:10},
      {rag:"Amber",code:"2025-00113", project:"HRSG HRH Vent stop valve replacement & part of pipeline replacement",                  owner:"Thessaloniki",      go_live:"TBD",      budget:"€115k", pct:10},
      {rag:"Amber",code:"2025-00118", project:"Fuel Gas AGI Flow computer and flow meters replacement",                               owner:"Thessaloniki",      go_live:"TBD",      budget:"€110k", pct:80},
      {rag:"Amber",code:"2025-00157", project:"Evaporative Cooling Tower (ECT) supply & installation",                                owner:"Thisvi",            go_live:"Dec 2025", budget:"€60k",  pct:5 },
      {rag:"Amber",code:"2025-00116", project:"ST Lube oil mist eliminator upgrade",                                                  owner:"Thessaloniki",      go_live:"TBD",      budget:"€57k",  pct:70},
      {rag:"Amber",code:"2025-00156", project:"Addition of oil moisture analyser in GT & ST lube oil tanks",                          owner:"Thisvi",            go_live:"TBD",      budget:"€30k",  pct:20},
      {rag:"Amber",code:"2025-00117", project:"Desuperheaters replacement (HP intermediate and HRH Final)",                           owner:"Thessaloniki",      go_live:"TBD",      budget:"€0",    pct:90},
    ],
  };

  // ----- Config: how the fake "agentic pipeline" paces itself -----
  // Each step is shown active for `duration` ms, then marked done.
  // Total run time is ~4.2s — long enough to feel real, short enough to keep a demo audience awake.
  const STEPS = [
    { id: 1, duration: 700 },  // Connecting to GOLD
    { id: 2, duration: 900 },  // Reading 201 projects
    { id: 3, duration: 1100 }, // GPT-5.4-mini-2 narrative
    { id: 4, duration: 800 },  // Render
    { id: 5, duration: 700 },  // QA
  ];

  const NUM_SLIDES = 10;
  const THUMB_PATH = "public/thumbnails";

  // ----- Element refs -----
  const btnGenerate    = document.getElementById("generate");
  const btnRegenerate  = document.getElementById("regenerate");
  const overlay        = document.getElementById("overlay");
  const overlayElapsed = document.getElementById("overlay-elapsed");
  const result         = document.getElementById("result");
  const resultElapsed  = document.getElementById("elapsed");
  const thumbsRoot     = document.getElementById("thumbnails");

  // ----- Pre-populate slide thumbnails into the (hidden) result section -----
  for (let i = 1; i <= NUM_SLIDES; i++) {
    const n = String(i).padStart(2, "0");
    const img = document.createElement("img");
    img.src = `${THUMB_PATH}/slide_${n}.png`;
    img.alt = `Slide ${i}`;
    img.loading = "lazy";
    img.addEventListener("click", () => openLightbox(img.src, img.alt));
    thumbsRoot.appendChild(img);
  }

  // ----- Persona switch (header) -----
  wirePersonaSwitch();

  // ----- Active period + available periods (populated from manifest at startup) -----
  let CURRENT_PERIOD = "2026-01";  // overwritten by manifest.default once loaded
  let MANIFEST = null;             // { periods: [{code, ymd, display}, ...], default: "<ymd>" }

  // Where the dashboard JSON lives. Defaults to the bundled public/data/, but can point
  // at an external store that Fabric publishes to (e.g. Azure Blob / OneLake / CDN) via
  // window.PIQ_CONFIG.dataBaseUrl — no Fabric auth in the request path; the site just reads.
  const DATA_BASE = (window.PIQ_CONFIG && window.PIQ_CONFIG.dataBaseUrl)
    ? String(window.PIQ_CONFIG.dataBaseUrl).replace(/\/+$/, "")
    : "public/data";
  const dataUrl = (name) => `${DATA_BASE}/${name}`;

  // ----- Bootstrap: load manifest, pick latest period, render -----
  // Falls back to inlined DATA if any fetch fails (e.g. opened from file://).
  (async () => {
    await loadManifest();
    CURRENT_PERIOD = (MANIFEST && MANIFEST.default) || "2026-01";
    await loadPeriod(CURRENT_PERIOD);
    renderAll();
    wireFilters();
    wireChat();
    wireDonutClicks();
    wirePeriodSelector();  // builds buttons from manifest, marks default active
  })();

  async function loadManifest() {
    try {
      const r = await fetch(dataUrl("manifest.json"), { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      MANIFEST = await r.json();
    } catch (e) {
      console.warn("Manifest unavailable; using inline defaults:", e.message);
      MANIFEST = {
        periods: [
          { code: "202512", ymd: "2025-12", display: "December 2025" },
          { code: "202601", ymd: "2026-01", display: "January 2026" },
          { code: "202602", ymd: "2026-02", display: "February 2026" },
        ],
        default: "2026-01",
      };
    }
  }

  function renderAll() {
    document.getElementById("kpi-grid").innerHTML = "";
    document.getElementById("schedule-bars").innerHTML = "";
    renderKPIs();
    renderScheduleBars();
    renderBudgetDonut();
    renderProjectsTable(DATA.projects);
    renderWhatChanged();
    renderActionItems();
    syncHeadline();
    syncDownloadLinks();
  }

  // Period-aware "What changed since prior period" strip. Hides itself
  // entirely if there's no prior period (earliest period in the manifest).
  function renderWhatChanged() {
    const strip   = document.getElementById("changed-strip");
    const eyebrow = document.getElementById("changed-eyebrow");
    const root    = document.getElementById("changed-bullets-root");
    if (!strip || !eyebrow || !root) return;
    const wc = DATA.whatChanged;
    if (!wc) { strip.style.display = "none"; return; }
    strip.style.display = "";
    eyebrow.textContent = wc.eyebrow;
    root.innerHTML = "";
    wc.bullets.forEach((b) => {
      const art = document.createElement("article");
      art.className = `changed-item changed-${b.dir}`;
      const arrow = b.dir === "bad" ? "▲" : b.dir === "good" ? "▼" : "—";
      art.innerHTML = `
        <span class="changed-arrow">${arrow}</span>
        <div class="changed-body">
          <strong>${b.headline}</strong>
          <em>${b.detail}</em>
        </div>`;
      root.appendChild(art);
    });
  }

  // Rule-based "Decisions needed this cycle" — items per period from thresholds.
  // Visible only in Executive persona (CSS controls visibility).
  function renderActionItems() {
    const list  = document.getElementById("action-items-list");
    const title = document.getElementById("action-items-title");
    if (!list || !DATA.actionItems) return;
    if (title) title.textContent = DATA.actionItems.subtitle;
    list.innerHTML = "";
    DATA.actionItems.items.forEach((it, idx) => {
      const sevLabel = it.severity.charAt(0).toUpperCase() + it.severity.slice(1);
      const li = document.createElement("li");
      li.className = `action-item action-${it.severity}`;
      li.innerHTML = `
        <div class="action-rank-col">
          <span class="action-rank">${String(idx + 1).padStart(2, "0")}</span>
          <span class="action-severity">${sevLabel}</span>
        </div>
        <div class="action-body">
          <h3>${it.title}</h3>
          <p>${it.detail}</p>
          <p class="action-meta">
            <span><strong>Owner</strong> ${it.owner}</span>
            <span class="dot"></span>
            <span><strong>Target</strong> ${it.target}</span>
          </p>
        </div>`;
      list.appendChild(li);
    });
  }

  // Derive the PPTX filename for a period from its display name in the manifest.
  // Convention: "December 2025" → "PortfolioIQ_December2025.pptx"
  function pptxFilenameForCurrent() {
    if (!MANIFEST) return "PortfolioIQ_January2026.pptx";
    const p = MANIFEST.periods.find((x) => x.ymd === CURRENT_PERIOD);
    if (!p) return "PortfolioIQ_January2026.pptx";
    return `PortfolioIQ_${p.display.replace(/\s+/g, "")}.pptx`;
  }
  function syncDownloadLinks() {
    const file = pptxFilenameForCurrent();
    document.querySelectorAll("[data-period-download]").forEach((a) => {
      a.href = `public/${file}`;
      a.setAttribute("download", file);
    });
  }

  // ----- Fetch one period's JSON and patch DATA in place -----
  async function loadPeriod(ymd) {
    try {
      const r = await fetch(dataUrl(`${ymd}.json`), { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      DATA.tiles       = d.tiles;
      DATA.schedule    = d.schedule;
      DATA.budget      = d.budget;
      DATA.projects    = d.projects;
      DATA.whatChanged = d.whatChanged || null;
      DATA.actionItems = d.actionItems || null;
      DATA._meta = {
        period_code:    d.period_code,
        period_display: d.period_display,
        headline:       d.headline,
      };
      CURRENT_PERIOD = ymd;
    } catch (e) {
      console.warn(`Falling back to inlined DATA for ${ymd}:`, e.message);
      DATA._meta = { period_display: "January 2026", headline: "100 active projects · 13 flagged · €5.9M exposure" };
    }
  }

  // ----- Switch periods (re-fetch + re-render whole dashboard) -----
  async function switchPeriod(ymd) {
    await loadPeriod(ymd);
    renderAll();
    showToast(`Loaded ${DATA._meta?.period_display || ymd}`);
  }

  function syncHeadline() {
    const headline = document.querySelector(".summary-headline");
    if (headline && DATA._meta?.headline) headline.textContent = DATA._meta.headline;
  }

  // Expose for the period selector
  window.__switchPeriod = switchPeriod;

  // ----- Persona switch: Executive / PM / Full -----
  // Sets body[data-persona] which the CSS uses to hide/show sections.
  // Default = 'pm' (rich workspace). Saved across sessions.
  function wirePersonaSwitch() {
    const STORAGE_KEY = "portfolio-iq-persona";
    const VALID = new Set(["executive", "deepdive"]);
    const LABELS = { executive: "Executive", deepdive: "Deep dive" };
    const trigger    = document.getElementById("persona-trigger");
    const dropdown   = document.getElementById("persona-dropdown");
    const valueEl    = document.getElementById("persona-trigger-value");
    const options    = document.querySelectorAll(".persona-option");
    if (!trigger || !dropdown || !options.length) return;

    // Load saved persona (defaults to 'deepdive' — rich workspace)
    let saved = "deepdive";
    try { saved = localStorage.getItem(STORAGE_KEY) || "deepdive"; } catch (e) {}
    // Migrate any legacy 'pm' or 'full' value to 'deepdive'.
    if (saved === "pm" || saved === "full") saved = "deepdive";
    if (!VALID.has(saved)) saved = "deepdive";
    apply(saved, /*silent=*/ true);

    // Open/close dropdown
    const open  = () => { dropdown.classList.remove("hidden"); trigger.setAttribute("aria-expanded", "true"); };
    const close = () => { dropdown.classList.add("hidden");    trigger.setAttribute("aria-expanded", "false"); };
    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      dropdown.classList.contains("hidden") ? open() : close();
    });
    document.addEventListener("click", (e) => {
      if (!dropdown.contains(e.target) && e.target !== trigger) close();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !dropdown.classList.contains("hidden")) close();
    });

    options.forEach((opt) => {
      opt.addEventListener("click", () => {
        apply(opt.dataset.persona);
        close();
      });
    });

    function apply(persona, silent) {
      document.body.setAttribute("data-persona", persona);
      options.forEach((o) => {
        const active = o.dataset.persona === persona;
        o.classList.toggle("persona-active", active);
        if (active) o.setAttribute("aria-current", "true");
        else        o.removeAttribute("aria-current");
      });
      if (valueEl) valueEl.textContent = LABELS[persona];
      try { localStorage.setItem(STORAGE_KEY, persona); } catch (e) {}
      if (!silent && typeof showToast === "function") {
        showToast(`Switched to ${LABELS[persona]} view`);
      }
    }
  }

  // ----- Filter the at-risk table from any click (KPI tile, schedule bar, donut segment) -----
  // Filter keys: 'all' | 'Red' | 'Amber' | 'overdue' (TBD or past go-live in the at-risk subset)
  function applyFilter(key, source) {
    // Sync filter chips above the table
    const chips = document.querySelectorAll(".filter-controls .chip");
    chips.forEach((c) => c.classList.remove("chip-active"));
    const chipMap = { all: "all", Red: "Red", Amber: "Amber", overdue: "all" };
    const target = chipMap[key] || "all";
    const targetChip = document.querySelector(`.filter-controls .chip[data-filter="${target}"]`);
    if (targetChip) targetChip.classList.add("chip-active");

    // Filter the rows
    let rows = DATA.projects;
    if (key === "Red" || key === "Amber") {
      rows = rows.filter((p) => p.rag === key);
    } else if (key === "overdue") {
      // "overdue" approximated as TBD go-live OR an already-passed go-live
      const now = new Date(2026, 0, 1);  // demo period
      rows = rows.filter((p) => {
        if (p.go_live === "TBD") return true;
        const parsed = parseGoLive(p.go_live);
        return parsed && parsed < now;
      });
    }
    renderProjectsTable(rows);

    // Flash + scroll the table card
    const card = document.querySelector(".dash-table-card");
    if (card) {
      card.classList.remove("flash");
      void card.offsetWidth;  // re-trigger animation
      card.classList.add("flash");
      card.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    if (source) showToast(`Filtered by ${source}`);
  }

  function parseGoLive(s) {
    if (!s || s === "TBD") return null;
    const m = s.match(/^([A-Za-z]+)\s+(\d{4})$/);
    if (!m) return null;
    const months = { Jan:0,Feb:1,Mar:2,Apr:3,May:4,Jun:5,Jul:6,Aug:7,Sep:8,Oct:9,Nov:10,Dec:11 };
    const mo = months[m[1].slice(0,3)];
    if (mo == null) return null;
    return new Date(parseInt(m[2], 10), mo, 1);
  }

  // ----- Donut segment clicks -----
  function wireDonutClicks() {
    // Donut categories don't map to the at-risk subset, so clicks reset the filter
    // but show a toast explaining the click. PM-tool feedback, not a no-op.
    const segs = document.querySelectorAll("#budget-donut circle.segment");
    const labels = ["Long Term Maintenance", "Financial Performance", "Betterment", "Safety / Regulatory"];
    segs.forEach((s, i) => {
      s.setAttribute("data-clickable", "true");
      s.addEventListener("click", () => {
        applyFilter("all", `Budget: ${labels[i] || "segment"}`);
      });
    });
  }

  // ----- Period selector — dynamically built from the manifest -----
  // Buttons render in chronological order from manifest.periods; the
  // manifest.default period gets the active state. Adding new periods to
  // the CSV → new JSONs → new manifest → buttons appear automatically, no
  // HTML edits required.
  function wirePeriodSelector() {
    const root = document.getElementById("period-selector");
    if (!root || !MANIFEST) return;
    root.innerHTML = "";

    MANIFEST.periods.forEach((p) => {
      const btn = document.createElement("button");
      btn.className = "period-btn" + (p.ymd === CURRENT_PERIOD ? " period-active" : "");
      btn.dataset.period = p.ymd;
      btn.setAttribute("aria-label", p.display);
      // Compact label: "Jan 2026" or "Dec '25" — show year only if it differs from default
      btn.textContent = p.display.replace(/(\w+) (\d{4})/, (_, mon, yr) => {
        // Show "Jan 2026" for the active/default year; "Dec '25" for others
        const defaultYear = (MANIFEST.default || "2026-01").slice(0, 4);
        return yr === defaultYear ? `${mon.slice(0,3)} ${yr}` : `${mon.slice(0,3)} '${yr.slice(-2)}`;
      });
      btn.addEventListener("click", async () => {
        if (btn.classList.contains("period-active")) return;
        root.querySelectorAll(".period-btn").forEach((b) => b.classList.remove("period-active"));
        btn.classList.add("period-active");
        if (typeof window.__switchPeriod === "function") {
          await window.__switchPeriod(p.ymd);
        }
      });
      root.appendChild(btn);
    });
  }

  // ----- Toast helper (top center, auto-hides after 3.5s) -----
  let toastTimer = null;
  function showToast(message) {
    const t = document.getElementById("toast");
    if (!t) return;
    t.innerHTML = `<span class="toast-icon">✓</span><span>${message}</span>`;
    t.classList.remove("hidden");
    requestAnimationFrame(() => t.classList.add("show"));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      t.classList.remove("show");
      setTimeout(() => t.classList.add("hidden"), 250);
    }, 3500);
  }

  // ----- Chat with the AI assistant (floating widget) -----
  function wireChat() {
    const toggle  = document.getElementById("chat-toggle");
    const panel   = document.getElementById("chat-panel");
    const close   = document.getElementById("chat-close");
    const form    = document.getElementById("chat-form");
    const input   = document.getElementById("chat-input");
    const win     = document.getElementById("chat-window");
    const chips   = document.querySelectorAll(".chat-chip");
    if (!form || !input || !win || !toggle || !panel) return;

    // Toggle widget visibility from the header button
    const openPanel  = () => {
      panel.classList.remove("hidden");
      panel.setAttribute("aria-hidden", "false");
      toggle.classList.add("active");
      setTimeout(() => input.focus(), 250);
    };
    const closePanel = () => {
      panel.classList.add("hidden");
      panel.setAttribute("aria-hidden", "true");
      toggle.classList.remove("active");
    };
    toggle.addEventListener("click", () => {
      if (panel.classList.contains("hidden")) openPanel(); else closePanel();
    });
    if (close) close.addEventListener("click", closePanel);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !panel.classList.contains("hidden")) closePanel();
    });

    chips.forEach((chip) => {
      chip.addEventListener("click", () => submitQuestion(chip.dataset.q));
    });
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const q = input.value.trim();
      if (!q) return;
      input.value = "";
      submitQuestion(q);
    });

    async function submitQuestion(q) {
      clearEmpty();
      appendBubble("user", escapeHtml(q));
      const thinking = appendThinking();
      let answer;
      try {
        answer = await askAI(q);            // live Azure OpenAI call, grounded on current data
      } catch (e) {
        console.warn("AI backend unavailable, using offline answer:", e.message);
        await sleep(400);                   // brief pause so the fallback still feels considered
        answer = matchAnswer(q);            // scripted fallback (file://, offline, or no key)
      }
      thinking.remove();
      const bubble = appendBubble("ai", "");
      streamHtml(bubble, answer, 12);
    }

    // Ask the real, published Microsoft Fabric data agent (via the same-origin proxy).
    // Requires the user to be signed in (MSAL) so their delegated token can be forwarded;
    // the agent enforces RLS per user and queries the semantic model itself.
    async function askAI(q) {
      if (!fabricEnabled()) throw new Error("fabric not configured");
      const token = await getFabricToken();      // interactive sign-in on first use
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), 90000);  // agent runs can take tens of seconds
      try {
        const r = await fetch("/api/ask", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: "Bearer " + token,
          },
          body: JSON.stringify({ question: q }),
          signal: ctrl.signal,
        });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const j = await r.json();
        if (!j || !j.answer) throw new Error("empty answer");
        return sanitizeHtml(j.answer);
      } finally {
        clearTimeout(to);
      }
    }

    function currentPeriodDisplay() {
      const m = MANIFEST && MANIFEST.periods
        ? MANIFEST.periods.find((p) => p.ymd === CURRENT_PERIOD)
        : null;
      return (m && m.display) || "the latest period";
    }

    // Allow only a small set of formatting tags from the model; drop everything else.
    function sanitizeHtml(html) {
      const ALLOWED = /^(P|UL|OL|LI|STRONG|EM|BR)$/;
      const root = document.createElement("div");
      root.innerHTML = String(html);
      (function clean(node) {
        Array.from(node.childNodes).forEach((n) => {
          if (n.nodeType === 1) {
            if (ALLOWED.test(n.tagName)) {
              Array.from(n.attributes).forEach((a) => n.removeAttribute(a.name));
              clean(n);
            } else {
              n.replaceWith(document.createTextNode(n.textContent));
            }
          } else if (n.nodeType !== 3) {
            n.remove();
          }
        });
      })(root);
      return root.innerHTML;
    }

    function clearEmpty() {
      const empty = win.querySelector(".chat-empty");
      if (empty) empty.remove();
    }

    function appendBubble(role, html) {
      const msg = document.createElement("div");
      msg.className = `chat-msg ${role}`;
      msg.innerHTML = `
        <div class="chat-avatar">${role === "ai" ? "IQ" : "YOU"}</div>
        <div class="chat-bubble">${html}</div>`;
      win.appendChild(msg);
      win.scrollTop = win.scrollHeight;
      return msg.querySelector(".chat-bubble");
    }

    function appendThinking() {
      const msg = document.createElement("div");
      msg.className = "chat-msg ai chat-thinking";
      msg.innerHTML = `
        <div class="chat-avatar">IQ</div>
        <div class="chat-bubble"><span class="thinking-dots"><span></span><span></span><span></span></span></div>`;
      win.appendChild(msg);
      win.scrollTop = win.scrollHeight;
      return msg;
    }

    // Stream pre-formatted HTML char-by-char (preserves tags).
    function streamHtml(el, html, speed) {
      el.innerHTML = "";
      let i = 0;
      const tick = () => {
        if (i >= html.length) return;
        // If we're at a "<", append the whole tag in one go (don't break markup).
        if (html.charAt(i) === "<") {
          const end = html.indexOf(">", i) + 1;
          el.innerHTML += html.slice(i, end);
          i = end;
        } else {
          el.innerHTML += html.charAt(i);
          i++;
        }
        win.scrollTop = win.scrollHeight;
        setTimeout(tick, speed);
      };
      tick();
    }
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // ----- Microsoft Fabric data agent auth (MSAL, delegated user identity) -----
  // Configuration comes from window.PIQ_CONFIG (see config.example.js). When it's not
  // present, the chat silently uses the offline scripted fallback instead.
  let _msalApp = null;

  function fabricEnabled() {
    const c = window.PIQ_CONFIG;
    return !!(c && c.clientId && c.tenantId && c.scope && window.msal);
  }

  function msalApp() {
    if (_msalApp) return _msalApp;
    const c = window.PIQ_CONFIG;
    _msalApp = new window.msal.PublicClientApplication({
      auth: {
        clientId: c.clientId,
        authority: `https://login.microsoftonline.com/${c.tenantId}`,
        redirectUri: c.redirectUri || window.location.origin,
      },
      cache: { cacheLocation: "sessionStorage" },
    });
    return _msalApp;
  }

  // Acquire a delegated token for the Fabric/Power BI scope: silent if possible,
  // otherwise an interactive popup the first time.
  async function getFabricToken() {
    const app = msalApp();
    if (app.initialize) await app.initialize();          // required by msal-browser v3+
    const scopes = [window.PIQ_CONFIG.scope];
    let account = app.getActiveAccount() || app.getAllAccounts()[0];
    if (!account) {
      const login = await app.loginPopup({ scopes });
      account = login.account;
      app.setActiveAccount(account);
    }
    try {
      const r = await app.acquireTokenSilent({ scopes, account });
      return r.accessToken;
    } catch (e) {
      const r = await app.acquireTokenPopup({ scopes, account });
      return r.accessToken;
    }
  }

  // Match a question against known intents and return an HTML answer using real data.
  function matchAnswer(question) {
    const q = question.toLowerCase();
    if (/baseline|schedule|delay|81/.test(q)) {
      return `<p>The <strong>81%</strong> headline breaks down across the 100 active projects as:</p>
        <ul>
          <li><strong>19</strong> on track</li>
          <li><strong>1</strong> delayed ≤ 20%</li>
          <li><strong>22</strong> delayed > 20%</li>
          <li><strong>58</strong> missing schedule baselines entirely</li>
        </ul>
        <p>The dominant contributor is <strong>missing baselines (58 of 100)</strong> — not actual delay. Enforcing baseline submission would cut the headline in half almost overnight.</p>`;
    }
    if (/exposure|expose|euro|€|amount|money/.test(q)) {
      return `<p>Total RAG exposure for January 2026: <strong>€5.9M</strong>, spread across <strong>13 flagged projects</strong>.</p>
        <ul>
          <li><strong>4 Red</strong> projects: ST Hydraulic Pumps · myElpedison Redesign · 3D HRSG Scanning · Strategic spare parts</li>
          <li><strong>9 Amber</strong> projects</li>
        </ul>
        <p>Dominated by <strong>Steam Turbine Major Inspection (€4.5M Amber)</strong>. The 4 Red projects combined sit at only €168k of budget — the financial risk is concentrated, not diffuse.</p>`;
    }
    if (/summar|takeaway|exec|overview|month|janu/.test(q)) {
      return `<p><strong>Portfolio performance shows strong budget control but schedule risks.</strong></p>
        <p>96% of projects are within budget, with €39.4M committed and 16.5% spent YTD. However, 12 projects are overdue and 22 face significant delays — impacting 81% of schedule adherence.</p>
        <p><strong>→ Immediate action:</strong> prioritize overdue and delayed projects to mitigate €5.9M exposure.</p>`;
    }
    if (/draft|recommend|steerco|steering|action|propos/.test(q)) {
      return `<p>Suggested SteerCo recommendation:</p>
        <p><em>"Approve mandatory schedule baseline submission for all 58 active projects currently missing one. Without baseline dates, 81% of the active portfolio cannot be tracked — neither schedule slippage nor recovery progress can be reported reliably. Owner: Portfolio PMO Lead. Target: end of Feb 2026."</em></p>
        <p>This addresses the largest structural risk in the portfolio and is the prerequisite for any meaningful schedule-recovery work next quarter.</p>`;
    }
    if (/budget|spend|over|fiscal|category/.test(q)) {
      return `<p>FY2026 budget distribution by category:</p>
        <ul>
          <li><strong>Long Term Maintenance</strong>: €21.5M (54%) — dominant category</li>
          <li><strong>Financial Performance</strong>: €13.4M (34%)</li>
          <li><strong>Betterment</strong>: €3.9M (10%)</li>
          <li><strong>Safety / Regulatory</strong>: €0.7M (2%)</li>
        </ul>
        <p>96 of 100 active projects within budget. Only <strong>4 at overrun risk</strong> — strong fiscal discipline overall.</p>`;
    }
    if (/most|top|risk|red|amber|riskiest|critical/.test(q)) {
      return `<p>The most material at-risk project is <strong>Steam Turbine Major Inspection</strong> (Amber, Thessaloniki).</p>
        <ul>
          <li>CY Budget: <strong>€4.5M</strong> — by far the largest exposure on the watchlist</li>
          <li>Progress: <strong>5%</strong> complete</li>
          <li>Target go-live: <strong>Jan 2027</strong></li>
        </ul>
        <p>It's <strong>76% of the entire €5.9M Red/Amber exposure</strong>. Recommended action: escalate to PM, validate baseline, confirm 2026 milestone plan.</p>`;
    }
    if (/owner|who|team|responsible|pm|manager/.test(q)) {
      return `<p>The Red/Amber watchlist is concentrated in two sites:</p>
        <ul>
          <li><strong>Thessaloniki</strong> — 7 projects, including the €4.5M Steam Turbine Inspection</li>
          <li><strong>Thisvi</strong> — 4 projects</li>
          <li>Commercial: 1 · Technical Services: 1</li>
        </ul>
        <p>If you want one focal owner to escalate to first, it's the Thessaloniki PM lead.</p>`;
    }
    if (/help|what.*can.*do|how|use/.test(q)) {
      return `<p>I can answer questions about the January 2026 portfolio. Try things like:</p>
        <ul>
          <li>"Why is the schedule so red?"</li>
          <li>"Which project worries you most?"</li>
          <li>"How much budget is at risk?"</li>
          <li>"Draft me a 1-paragraph CFO update"</li>
          <li>"Who owns the worst projects?"</li>
        </ul>`;
    }
    // Fallback
    return `<p>Good question — I don't have specific data on that yet for this period.</p>
      <p>For the demo, try one of the suggested questions above, or ask about schedule health, budget exposure, top-risk projects, or recommendations for the SteerCo.</p>`;
  }

  function streamAIHero() {
    const verdictEl = document.getElementById("ai-verdict");
    const detailEl  = document.getElementById("ai-detail");
    const actionEl  = document.getElementById("ai-action");
    if (!verdictEl) return;

    // Verdict has two clauses — second is rendered as italic green (editorial accent).
    const verdictPart1 = "Portfolio performance shows strong budget control ";
    const verdictPart2 = "but schedule risks.";
    const detail  = "96% of projects are within budget, with €39.4M committed and 16.5% spent YTD. However, 12 projects are overdue, and 22 face significant delays — impacting 81% of schedule adherence.";
    const action  = "→ Immediate action required: prioritize overdue and delayed projects to mitigate €5.9M exposure.";

    type(verdictEl, verdictPart1, 28, () => {
      verdictEl.classList.remove("typing");
      const italic = document.createElement("i");
      verdictEl.appendChild(italic);
      italic.classList.add("typing");
      type(italic, verdictPart2, 28, () => {
        italic.classList.remove("typing");
        type(detailEl, detail, 12, () => {
          detailEl.classList.remove("typing");
          type(actionEl, action, 18, () => {
            actionEl.classList.remove("typing");
          });
        });
      });
    });
  }

  function type(el, text, speed, done) {
    el.textContent = "";
    el.classList.add("typing");
    let i = 0;
    const tick = () => {
      if (i < text.length) {
        el.textContent += text.charAt(i++);
        setTimeout(tick, speed);
      } else if (done) {
        done();
      }
    };
    tick();
  }

  function renderKPIs() {
    const root = document.getElementById("kpi-grid");
    if (!root) return;
    DATA.tiles.forEach((t, idx) => {
      const el = document.createElement("div");
      el.className = `kpi-tile accent-${t.accent}${t.filter ? " clickable" : ""}`;
      const deltaHtml = t.delta ? `
        <div class="kpi-delta ${t.delta.dir}">
          <span class="kpi-delta-arrow">${t.delta.dir === "bad" ? "▲" : t.delta.dir === "good" ? "▲" : "—"}</span>
          <span>${t.delta.v} vs Dec</span>
        </div>` : "";
      el.innerHTML = `
        <div class="kpi-value" data-target="${t.value}">${t.value}</div>
        <div class="kpi-label">${t.label}</div>
        <div class="kpi-sub">${t.sub}</div>
        ${deltaHtml}`;
      if (t.filter) {
        el.addEventListener("click", () => applyFilter(t.filter, `KPI: ${t.label}`));
      }
      root.appendChild(el);
      // Stagger the count-up animation across tiles for a "cascading" feel.
      animateNumber(el.querySelector(".kpi-value"), t.value, 900, idx * 120);
    });
  }

  // Animate a number/currency/percent string from "0" up to its target value.
  function animateNumber(el, target, durationMs, delayMs) {
    const text = String(target);
    // Parse leading symbol (€) and trailing suffix (M, k, %)
    const match = text.match(/^([^\d]*)([0-9]+(?:\.[0-9]+)?)([^\d]*)$/);
    if (!match) return;
    const [, prefix, numStr, suffix] = match;
    const end = parseFloat(numStr);
    const decimals = (numStr.split(".")[1] || "").length;
    const t0 = performance.now() + delayMs;
    const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);
    el.textContent = `${prefix}0${suffix}`;
    const tick = (now) => {
      if (now < t0) { requestAnimationFrame(tick); return; }
      const t = Math.min(1, (now - t0) / durationMs);
      const v = end * easeOutCubic(t);
      el.textContent = `${prefix}${v.toFixed(decimals)}${suffix}`;
      if (t < 1) requestAnimationFrame(tick);
      else el.textContent = text;
    };
    requestAnimationFrame(tick);
  }

  function renderScheduleBars() {
    const root = document.getElementById("schedule-bars");
    if (!root) return;
    const max = Math.max(...DATA.schedule.map((s) => s.value));
    // Each bar's color also drives a sensible filter on the at-risk table.
    const BAR_FILTER = {
      green: "all",      // "On Track" → reset (those projects aren't on the at-risk list)
      amber: "Amber",
      red:   "Red",
      grey:  "overdue",  // "No Baseline" → maps to overdue/TBD subset
    };
    DATA.schedule.forEach((s) => {
      const row = document.createElement("div");
      row.className = "bar-row clickable";
      row.innerHTML = `
        <span class="bar-label">${s.label}</span>
        <div class="bar-track"><div class="bar-fill bar-${s.color}" data-target="${(s.value / max) * 100}"></div></div>
        <span class="bar-value">${s.value}</span>`;
      row.addEventListener("click", () => applyFilter(BAR_FILTER[s.color] || "all", `Schedule: ${s.label}`));
      root.appendChild(row);
    });
    // Animate bars in after a short delay so transition kicks in.
    requestAnimationFrame(() => {
      setTimeout(() => {
        root.querySelectorAll(".bar-fill").forEach((b) => {
          b.style.width = `${b.dataset.target}%`;
        });
      }, 150);
    });
  }

  function renderBudgetDonut() {
    const svg = document.getElementById("budget-donut");
    const legend = document.getElementById("budget-legend");
    if (!svg || !legend) return;
    const r = 80;
    const c = 2 * Math.PI * r;       // circumference
    let acc = 0;
    DATA.budget.forEach((seg) => {
      const len = (seg.pct / 100) * c;
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", "100");
      circle.setAttribute("cy", "100");
      circle.setAttribute("r", r);
      circle.setAttribute("stroke", seg.color);
      circle.setAttribute("class", "segment");
      circle.setAttribute("stroke-dasharray", `${len} ${c - len}`);
      circle.setAttribute("stroke-dashoffset", `${-acc}`);
      svg.appendChild(circle);
      acc += len;

      const li = document.createElement("li");
      li.innerHTML = `
        <span class="swatch" style="background:${seg.color}"></span>
        <span class="lg-label">${seg.label}</span>
        <span class="lg-value">€${seg.value_m}M</span>
        <span class="lg-pct">${seg.pct}%</span>`;
      legend.appendChild(li);
    });
  }

  // Re-renders the donut SVG segments + legend based on current DATA.budget.
  // Replaces the static SVG content in HTML so period switches update the chart.
  function renderBudgetDonut() {
    const svg    = document.getElementById("budget-donut");
    const legend = document.getElementById("budget-legend");
    if (!svg || !legend) return;
    // Strip any existing segments + legend rows (keep background ring)
    svg.querySelectorAll("circle.segment").forEach(c => c.remove());
    legend.innerHTML = "";
    const r = 80;
    const c = 2 * Math.PI * r;
    let acc = 0;
    DATA.budget.forEach((seg) => {
      const len = (seg.pct / 100) * c;
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", "100");
      circle.setAttribute("cy", "100");
      circle.setAttribute("r", String(r));
      circle.setAttribute("fill", "none");
      circle.setAttribute("stroke", seg.color);
      circle.setAttribute("stroke-width", "32");
      circle.setAttribute("class", "segment");
      circle.setAttribute("stroke-dasharray", `${len.toFixed(2)} ${(c - len).toFixed(2)}`);
      circle.setAttribute("stroke-dashoffset", `${(-acc).toFixed(2)}`);
      svg.appendChild(circle);
      acc += len;

      const li = document.createElement("li");
      li.innerHTML = `
        <span class="swatch" style="background:${seg.color}"></span>
        <span class="lg-label">${seg.legend_label || seg.label}</span>
        <span class="lg-value">€${seg.value_m}M</span>
        <span class="lg-pct">${seg.pct}%</span>`;
      legend.appendChild(li);
    });
  }

  function renderProjectsTable(rows) {
    const tbody = document.querySelector("#risk-table tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    if (rows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="table-empty">
        <span class="table-empty-icon">○</span>
        <span>No projects match this filter.</span>
      </td></tr>`;
      return;
    }
    rows.forEach((p) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class="rag-pill rag-${p.rag}">${p.rag.toUpperCase()}</span></td>
        <td>${p.project}</td>
        <td>${p.owner}</td>
        <td>${p.go_live}</td>
        <td>${p.budget}</td>
        <td>${p.pct}%</td>`;
      tbody.appendChild(tr);
    });
  }

  function wireFilters() {
    const chips = document.querySelectorAll(".chip");
    chips.forEach((chip) => {
      chip.addEventListener("click", () => {
        chips.forEach((c) => c.classList.remove("chip-active"));
        chip.classList.add("chip-active");
        const f = chip.dataset.filter;
        const filtered = f === "all" ? DATA.projects : DATA.projects.filter((p) => p.rag === f);
        renderProjectsTable(filtered);
      });
    });

    // Click-to-sort on table headers
    document.querySelectorAll("#risk-table thead th").forEach((th, idx) => {
      let asc = true;
      th.addEventListener("click", () => {
        const keys = ["rag", "project", "owner", "go_live", "budget", "pct"];
        const key = keys[idx];
        const activeChip = document.querySelector(".chip.chip-active");
        const f = activeChip ? activeChip.dataset.filter : "all";
        const rows = (f === "all" ? DATA.projects : DATA.projects.filter((p) => p.rag === f)).slice();
        rows.sort((a, b) => {
          let av = a[key], bv = b[key];
          if (typeof av === "string") return asc ? av.localeCompare(bv) : bv.localeCompare(av);
          return asc ? av - bv : bv - av;
        });
        asc = !asc;
        renderProjectsTable(rows);
      });
    });
  }

  // ----- Click handlers -----
  btnGenerate.addEventListener("click", runPipeline);
  btnRegenerate.addEventListener("click", () => {
    result.classList.add("hidden");
    runPipeline();
  });

  // ----- "How it works" modal -----
  const howLink   = document.getElementById("how-link");
  const howModal  = document.getElementById("how-modal");
  const howClose  = document.getElementById("how-close");
  if (howLink && howModal && howClose) {
    const open = (e) => {
      e.preventDefault();
      howModal.classList.remove("hidden");
      howModal.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
    };
    const close = () => {
      howModal.classList.add("hidden");
      howModal.setAttribute("aria-hidden", "true");
      document.body.style.overflow = "";
    };
    howLink.addEventListener("click", open);
    howClose.addEventListener("click", close);
    howModal.addEventListener("click", (e) => {
      if (e.target === howModal) close();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !howModal.classList.contains("hidden")) close();
    });
  }

  // ----- The animated "pipeline run" -----
  async function runPipeline() {
    // Reset step state
    document.querySelectorAll(".step").forEach((el) => {
      el.classList.remove("active", "done");
    });
    overlayElapsed.textContent = "0.0";

    // Show overlay
    overlay.classList.remove("hidden");
    overlay.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";

    // Kick off a REAL build immediately (renders this period's deck server-side).
    // Resolves to {url, filename, seconds} or null if no build endpoint (static host).
    const buildPromise = startLiveBuild();

    // Start elapsed-time counter
    const t0 = performance.now();
    const tick = setInterval(() => {
      const elapsed = (performance.now() - t0) / 1000;
      overlayElapsed.textContent = elapsed.toFixed(1);
    }, 50);

    // Animate every step except the last (which we tie to the real render finishing)
    const lead = STEPS.slice(0, -1);
    const last = STEPS[STEPS.length - 1];
    for (const step of lead) {
      const el = document.querySelector(`.step[data-step="${step.id}"]`);
      el.classList.add("active");
      await sleep(step.duration);
      el.classList.remove("active");
      el.classList.add("done");
    }

    // Final step (QA) stays active until the actual build resolves — honest timing.
    const lastEl = document.querySelector(`.step[data-step="${last.id}"]`);
    lastEl.classList.add("active");
    const [build] = await Promise.all([buildPromise, sleep(last.duration)]);
    lastEl.classList.remove("active");
    lastEl.classList.add("done");
    await sleep(250);

    const totalElapsed = ((performance.now() - t0) / 1000).toFixed(1);
    clearInterval(tick);

    // If we got a fresh build, point the download links at it and report its time.
    if (build) {
      applyLiveBuild(build);
      resultElapsed.textContent = build.seconds || totalElapsed;
    } else {
      syncDownloadLinks();                 // fall back to the pre-rendered file
      resultElapsed.textContent = totalElapsed;
    }

    // Dismiss animation overlay
    overlay.classList.add("hidden");
    overlay.setAttribute("aria-hidden", "true");

    // Show result modal (overlay-style) — keep body scroll locked
    result.classList.remove("hidden");
    result.setAttribute("aria-hidden", "false");
  }

  // Ask the local build endpoint to render this period now. Returns a blob URL +
  // filename + server build seconds, or null if the endpoint isn't available
  // (e.g. the static Vercel site or `python -m http.server`) — caller falls back.
  let _lastBlobUrl = null;
  async function startLiveBuild() {
    try {
      const r = await fetch(`/api/generate?period=${encodeURIComponent(CURRENT_PERIOD)}`, {
        cache: "no-store",
      });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const blob = await r.blob();
      const cd = r.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename="?([^"]+)"?/);
      const filename = (m && m[1]) || pptxFilenameForCurrent();
      if (_lastBlobUrl) URL.revokeObjectURL(_lastBlobUrl);
      _lastBlobUrl = URL.createObjectURL(blob);
      return { url: _lastBlobUrl, filename, seconds: r.headers.get("X-Build-Seconds") };
    } catch (e) {
      console.warn("Live build unavailable, using pre-rendered deck:", e.message);
      return null;
    }
  }

  function applyLiveBuild(build) {
    document.querySelectorAll("[data-period-download]").forEach((a) => {
      a.href = build.url;
      a.setAttribute("download", build.filename);
    });
  }

  // Close result modal — restore body scroll
  const resultClose = document.getElementById("result-close");
  if (resultClose) {
    const closeResult = () => {
      result.classList.add("hidden");
      result.setAttribute("aria-hidden", "true");
      document.body.style.overflow = "";
    };
    resultClose.addEventListener("click", closeResult);
    result.addEventListener("click", (e) => { if (e.target === result) closeResult(); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !result.classList.contains("hidden")) closeResult();
    });
  }

  // ----- Sleep helper -----
  function sleep(ms) {
    return new Promise((res) => setTimeout(res, ms));
  }

  // ----- Lightbox for thumbnails (click to enlarge) -----
  function openLightbox(src, alt) {
    const lb = document.createElement("div");
    lb.style.cssText = `
      position: fixed; inset: 0; background: rgba(0,0,0,0.9);
      display: flex; align-items: center; justify-content: center;
      padding: 2rem; z-index: 2000; cursor: zoom-out;
    `;
    const img = document.createElement("img");
    img.src = src;
    img.alt = alt;
    img.style.cssText = `
      max-width: 100%; max-height: 100%; border-radius: 4px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.5);
    `;
    lb.appendChild(img);
    lb.addEventListener("click", () => lb.remove());
    document.body.appendChild(lb);

    // Esc to close
    const esc = (e) => {
      if (e.key === "Escape") {
        lb.remove();
        document.removeEventListener("keydown", esc);
      }
    };
    document.addEventListener("keydown", esc);
  }
})();
