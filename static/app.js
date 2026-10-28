/* CareRules page: runs fully in the browser on a free static Space. The engine (engine.js) reads the handbook, picks
   the rule pages, builds the prompt and checks every quote; the CareRules API Worker only gates and forwards the call
   to Beam (access code, spending limits, cache). */
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// Same origin on care.backpr.com (the Worker serves page and API); the Hugging Face copy and local tests call it there.
const API = /(^|\.)backpr\.com$/.test(location.hostname) ? "" : "https://care.backpr.com";
const REQUEST_EMAIL = "hi@backpr.com";
const LIBS = {
  pdfjs: "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs",
  pdfWorker: "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs",
  mammoth: "https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.8.0/mammoth.browser.min.js",
  mammothSri: "sha512-wuWo/cLB9W5BsZeyTYLuiTwr+FDlvjQC7C6atr+To7Jk92XHWI7WsImJZiruw7C9bnc8Zg7N0ncQI2Q/B4PQYw==",
};
const MAX_FILE = 12 * 1024 * 1024, MAX_TEXT = 240000;
const COLORS = CR.COLORS;
const LABELS = { conflict: "Breaks a rule", missing: "Missing", partial: "Incomplete", covered: "Covered" };
const SCOPE = { AR: "out-of-school-time programs" };  // a state whose rules cover only one kind of program
const US = { AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California", CO: "Colorado", CT: "Connecticut", DE: "Delaware",
  DC: "District of Columbia", FL: "Florida", GA: "Georgia", HI: "Hawaii", ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa", KS: "Kansas",
  KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland", MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi",
  MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada", NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York",
  NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma", OR: "Oregon", PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina",
  SD: "South Dakota", TN: "Tennessee", TX: "Texas", UT: "Utah", VT: "Vermont", VA: "Virginia", WA: "Washington", WV: "West Virginia",
  WI: "Wisconsin", WY: "Wyoming" };

/* "Is your state covered?" in the hero: answers at once, and picks the state for the check below */
function heroStates(sources) {
  const sel = $("#hero-state"), msg = $("#hero-state-msg");
  sel.innerHTML += Object.entries(US).sort((a, b) => a[1].localeCompare(b[1])).map(([c, n]) => `<option value="${c}">${esc(n)}</option>`).join("");
  sel.addEventListener("change", () => {
    const c = sel.value;
    msg.className = "";
    if (!c) { msg.textContent = ""; return; }
    if (sources[c]) {
      msg.className = "yes";
      msg.textContent = `✓ ${US[c]} is covered${SCOPE[c] ? ` (${SCOPE[c]} only)` : ""}. Check your handbook against its rules below.`;
      if (!state.demo) { state.chosen = new Set([c]); renderChips(); requestLink(); }  // the state you picked, ready below
    } else {
      msg.className = "no";
      msg.textContent = `${US[c]} isn't covered yet. Email ${REQUEST_EMAIL} to ask about it.`;
    }
  });
}
const params = new URLSearchParams(location.search);
const state = { states: [], chosen: new Set(), effort: "low", file: null, pages: null, fixes: "", fixesName: "handbook-fixes",
  maxStates: 3, last: null, readSeq: 0 };
const getJson = async (path) => { const r = await fetch(path); if (!r.ok) throw new Error(`Couldn't load ${path}`); return r.json(); };
const stateName = (code) => CR.NAMES[code] || code;

/* The rulebook scan: each state's whole rulebook as a bar from page 1 to the last page, with each finding at its page. */
function scan(el, tracks, { loop = false, dur = 4.2 } = {}) {
  el.classList.toggle("loop", loop);
  el.style.setProperty("--dur", `${dur}s`);
  el.innerHTML = tracks.map((t, i) => {
    const pages = Math.max(2, t.pages || 2);
    const marks = (t.marks || []).filter((m) => m[1] !== "not_mentioned").map(([page, st]) => {
      const x = ((page - 1) / (pages - 1)) * 100;
      return `<i class="${st === "conflict" ? "bad" : ""}" style="left:${x.toFixed(2)}%;background:${COLORS[st] || "#555"};animation-delay:${((x / 100) * dur + i * 0.35).toFixed(2)}s" title="Page ${page}"></i>`;
    }).join("");
    return `<div><div class="track-label"><span><b>${esc(t.name)}</b> licensing rules</span><span>page 1 → ${pages}</span></div>
      <div class="track"><span class="sweep" style="animation-delay:${i * 0.35}s"></span>${marks}</div></div>`;
  }).join("") + (tracks.some((t) => t.marks && t.marks.length) ? `<div class="scan-legend">${["conflict", "missing", "partial", "covered"].map((k) => `<span><i style="background:${COLORS[k]}"></i>${LABELS[k]}</span>`).join("")}</div>` : "");
}

/* Hero card: the sample report's own finding for one sentence, state by state (verbatim from the report). */
function demo(rows, scores) {
  const states = Object.keys(scores);
  const row = rows.find((r) => states.every((s) => r.verdict[s] === "conflict") && /asleep|nap/i.test(r.quote))
    || rows.find((r) => states.every((s) => r.verdict[s] === "conflict")) || rows[0];
  if (!row) { $("#demo").hidden = true; return; }
  const order = states.filter((s) => row.detail[s]);
  const cut = (t, n) => (t.length > n ? t.slice(0, n - 1).replace(/\s+\S*$/, "") + "…" : t);
  const sentences = (t, n) => {  // whole sentences up to n characters (at least the first one)
    const parts = String(t || "").match(/[^.!?]+[.!?]+(\s|$)/g) || [String(t || "")];
    let out = parts[0].trim();
    for (const p of parts.slice(1)) { if ((out + " " + p.trim()).length > n) break; out += " " + p.trim(); }
    return out;
  };
  $("#demo-tabs").innerHTML = order.map((s) => `<button type="button" data-st="${s}" aria-pressed="false">${esc(scores[s].name)}</button>`).join("");
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let i = 0, timer = null;
  const show = (s) => {
    const d = row.detail[s];
    document.querySelectorAll("#demo-tabs button").forEach((t) => { t.classList.toggle("on", t.dataset.st === s); t.setAttribute("aria-pressed", String(t.dataset.st === s)); });
    $("#demo-page").textContent = `page ${row.page}`;
    $("#demo-hit").textContent = `“${cut(d.quote || row.quote, 150)}”`;
    ["#demo-hit", "#demo-rule", "#demo-fix"].forEach((k) => $(k).classList.remove("flag", "in"));
    $("#demo-rule").innerHTML = `<b>✕ Breaks ${esc(scores[s].name)} ${esc(d.section)}, page ${esc(d.page)} of the rules</b><q>${esc(cut(d.rule, 190))}</q><small>✓ Quote checked word for word against the official rules</small>`;
    $("#demo-fix").innerHTML = `<b>Suggested wording (AI draft)</b>${esc(sentences(d.fix || d.why, 190))}`;
    setTimeout(() => $("#demo-hit").classList.add("flag"), still ? 0 : 500);
    setTimeout(() => $("#demo-rule").classList.add("in"), still ? 0 : 1300);
    setTimeout(() => $("#demo-fix").classList.add("in"), still ? 0 : 2300);
  };
  show(order[0]);
  const stop = () => { clearInterval(timer); timer = null; const p = $("#demo-pause"); if (p) p.remove(); };
  if (!still) {
    timer = setInterval(() => show(order[++i % order.length]), 9000);
    $("#demo-tabs").insertAdjacentHTML("beforeend", '<button type="button" id="demo-pause" class="demo-pause" aria-label="Stop the example from changing">❚❚</button>');
  }
  $("#demo-tabs").addEventListener("click", (ev) => {  // a state button, or pause, stops the rotation
    if (ev.target.closest("#demo-pause")) { stop(); return; }
    const b = ev.target.closest("button[data-st]");
    if (!b) return;
    stop();
    show(b.dataset.st);
  });
}

const PHOTO = [[/asleep|nap|crib|sleep|bouncer|swing|car seat/i, "nap-room.jpg"], [/lunch|dessert|food|meal|snack|eat/i, "kids-table.jpg"],
  [/trip|walk|park|library|bus|outside|outdoor/i, "park.jpg"], [/screen|tv|television|tablet|video/i, "screen-time.jpg"],
  [/pet|animal|visitor/i, "visiting-dog.jpg"], [/medic|medicine/i, "teachers.jpg"], [/ratio|teacher cares|class|Pre-K|years? 1 to/i, "classroom.jpg"]];
// Photos used nowhere else on the page come first, so the same photo never shows twice.
const POOL = ["park.jpg", "screen-time.jpg", "visiting-dog.jpg", "nap-room.jpg", "kids-table.jpg"];
const photoFor = (text, used) => {
  const fit = PHOTO.filter(([re]) => re.test(text)).map(([, f]) => f);
  const pick = [...fit, ...POOL].find((f) => !used.has(f)) || POOL[0];
  used.add(pick);
  return pick;
};

/* "One handbook, every state": sentences where the states disagree. Abuse reporting is left out: other state laws
   govern it, so "no conflict in the licensing rules" there could read as "this is fine". */
function differ(rows, scores) {
  const states = Object.keys(scores);
  const mixed = (r) => new Set(states.map((s) => r.verdict[s])).size > 1;
  const usable = (r) => r.quote.split(/\s+/).length >= 8 && !CR.isTableRow(r.quote) && !/abus|neglect|maltreat/i.test(r.quote);
  const picked = rows.filter(usable).sort((a, b) => mixed(b) - mixed(a)).slice(0, 3);
  const used = new Set([...document.querySelectorAll("img")].map((i) => i.getAttribute("src").split("/").pop()));
  $("#differ-rows").innerHTML = picked.map((r) => `<div class="drow reveal"><img src="static/media/${photoFor(r.quote, used)}" alt="" loading="lazy">
    <div><q>${esc(r.quote.length > 170 ? r.quote.slice(0, 167) + "…" : r.quote)}</q><span class="pg">Sample handbook, page ${esc(r.page)}</span></div>
    <div class="verdicts">${states.map((s) => r.verdict[s] === "conflict"
      ? `<div class="verdict bad"><div class="st">${esc(scores[s].name)}</div><div class="v">Breaks</div><div class="sec">${esc(r.sections[s] || "")}</div></div>`
      : `<div class="verdict ok"><div class="st">${esc(scores[s].name)}</div><div class="v">No broken rule found</div><div class="sec">licensing rules only</div></div>`).join("")}</div></div>`).join("");
  observe();
}

/* The handbook page, marked up: conflicting sentences highlighted, with the rules beside them (sample page 4). */
function markup(results, pages, pageNo) {
  const raw = (pages.find(([n]) => n === pageNo) || [0, ""])[1];
  const blocks = [];
  for (const line of raw.split("\n").map((l) => l.trim()).filter(Boolean)) {
    const heading = line.length < 42 && !/[.,:;]$/.test(line) && /^[A-Z]/.test(line);
    if (heading) blocks.push({ h: line });
    else if (blocks.length && !blocks[blocks.length - 1].h) blocks[blocks.length - 1].p += " " + line;
    else blocks.push({ p: line });
  }
  const notes = [];
  for (const [st, r] of Object.entries(results)) {
    for (const f of r.findings) {
      if (f.handbook_page !== pageNo || !["conflict", "partial"].includes(f.status) || !f.handbook_quote) continue;
      const key = f.handbook_quote.toLowerCase().split(/\W+/).slice(0, 7).join(" ");
      let n = notes.find((x) => x.key === key);
      if (!n) notes.push(n = { key, quote: f.handbook_quote, status: f.status, states: {}, why: f.explanation });
      if (f.status === "conflict") { n.status = "conflict"; n.why = n.why || f.explanation; }
      n.states[st] = n.states[st] || f.section;
    }
  }
  const conflicts = notes.filter((n) => n.status === "conflict");
  const pattern = (ws) => new RegExp(ws.map((w) => esc(w).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\W+"));
  let num = 0;
  const html = blocks.map((b) => {
    if (b.h) return `<h4>${esc(b.h)}</h4>`;
    const text = esc(b.p);
    // Find every note in this paragraph (the whole verified quote, or its first 14 words if punctuation differs),
    // then mark them in reading order so the footnote numbers run 1, 2, 3 down the page.
    const hits = [];
    for (const n of notes) {
      if (n.placed) continue;
      const all = n.quote.split(/\s+/).filter(Boolean);
      const m = text.match(pattern(all)) || text.match(pattern(all.slice(0, 14)));
      if (m) hits.push({ n, start: m.index, end: m.index + m[0].length });
    }
    hits.sort((a, b) => a.start - b.start);
    let out = "", at = 0;
    for (const h of hits) {
      if (h.start < at) continue;  // overlaps the previous mark
      h.n.placed = true;
      const label = h.n.status === "conflict" ? `<sup>${(h.n.num = ++num)}</sup>` : "";
      out += text.slice(at, h.start) + `<mark class="${h.n.status}" title="${esc(Object.keys(h.n.states).map((s) => stateName(s) + " " + h.n.states[s]).join(" · "))}">${text.slice(h.start, h.end)}${label}</mark>`;
      at = h.end;
    }
    return `<p>${out + text.slice(at)}</p>`;
  }).join("");
  const margin = conflicts.filter((n) => n.num).sort((a, b) => a.num - b.num).map((n) => `<div class="note"><b>${n.num}. ${esc(n.why || "Breaks a rule")}</b>
    <div class="chips-sm">${Object.entries(n.states).map(([s, sec]) => `<span>${esc(stateName(s))} ${esc(sec)}</span>`).join("")}</div></div>`).join("");
  const legend = `<div class="mk-legend"><span><mark class="conflict">Red</mark> breaks a rule</span><span><mark class="partial">Yellow</mark> covers a required policy only in part</span></div>`;
  $("#markup-page").innerHTML = `<div class="sheet"><div class="paper-head"><span>Little Acorns Family Handbook</span><span>page ${pageNo}</span></div>${html}${legend}</div><div class="margin">${margin || '<p class="small">No conflicts on this page.</p>'}</div>`;
}

/* From finding to fix: the handbook sentence and the first sentence of the suggested wording. */
function pairs(rows, scores) {
  const first = (t) => (String(t || "").match(/^.*?[.!?](\s|$)/) || [String(t || "")])[0].trim();
  const picked = rows.filter((r) => Object.values(r.detail).some((d) => d.fix) && !CR.isTableRow(r.quote)).slice(0, 3);
  $("#pairs").innerHTML = picked.map((r) => {
    const s = Object.keys(r.detail).find((k) => r.detail[k].fix);
    return `<div class="pair reveal"><div class="from">“${esc(r.quote.length > 120 ? r.quote.slice(0, 117) + "…" : r.quote)}”</div><span class="arrow" aria-hidden="true">→</span><div class="to">${esc(first(r.detail[s].fix))}<div class="small">Suggested for ${esc(scores[s].name)} · ${esc(r.detail[s].section)}</div></div></div>`;
  }).join("");
  observe();
}

/* scroll reveals, statement lines lit by scroll position, scans that start when seen */
let io;
function observe() {
  io = io || new IntersectionObserver((entries) => entries.forEach((e) => {
    if (!e.isIntersecting) return;
    e.target.classList.add(e.target.classList.contains("scan") ? "go" : "in");
    io.unobserve(e.target);
  }), { threshold: 0.15 });
  document.querySelectorAll(".reveal:not(.in), .scan:not(.go)").forEach((el) => io.observe(el));
}
function lightStatements() {
  const mid = innerHeight * 0.62;
  document.querySelectorAll(".lit").forEach((el) => el.classList.toggle("on", el.getBoundingClientRect().top < mid));
}
addEventListener("scroll", lightStatements, { passive: true });

/* the hero video: only on wide screens, never with reduced motion or data saver */
function heroVideo() {
  const v = $("#hero-video");
  const save = navigator.connection && navigator.connection.saveData;
  const site = /(^|\.)backpr\.com$/.test(location.hostname);  // the clip is licensed for the website only
  if (!v || !site || save || innerWidth < 900 || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  v.src = "static/media/hero-paperwork.mp4";
  v.addEventListener("canplay", () => { v.classList.add("on"); v.play().catch(() => {}); }, { once: true });
  v.load();
}

function showReport(html, fixes, head, note = "", summary = "") {
  if (summary) $("#report-summary").textContent = summary;
  $("#report-head").innerHTML = head;
  $("#report").innerHTML = (note ? `<div class="ci-run ci-warn">${note}</div>` : "") + html;
  state.fixes = fixes || "";
  $("#actions").hidden = !state.fixes;
  const box = $("#backpr-box");  // removed on the Space
  if (box) box.hidden = !state.fixes;
}

/* the email that asks for a code: the address is always visible too, because mailto links fail silently on webmail */
function requestLink() {
  const chosen = [...state.chosen].map(stateName).join(", ");
  const body = `Hi BackPR team,\n\nI'd like a free CareRules access code.\n\nCenter name:\nState(s): ${chosen}\nMy role:\n\n` +
    "Also send me information about BackPR's registration and tuition software (yes/no):\n\nThank you!";
  const href = `mailto:${REQUEST_EMAIL}?subject=${encodeURIComponent("CareRules: free access code")}&body=${encodeURIComponent(body)}`;
  $("#request").href = href;
  $("#request-inline").href = href;
}

/* access codes: given out on request; a judge's link carries one as ?code= */
async function checkCode() {
  const code = $("#code").value.trim();
  if (!code) { $("#code").classList.remove("ok"); return null; }
  try {
    const r = await fetch(`${API}/code?code=${encodeURIComponent(code)}`);
    let s = {};
    try { s = await r.json(); } catch (e) { throw new Error("The checking service had a problem. Please try again in a minute."); }
    if (!r.ok) throw new Error(s.error || "The checking service had a problem. Please try again in a minute.");
    $("#code").classList.toggle("ok", s.valid);
    if (s.valid) {
      try { localStorage.setItem("carerules-code", code); } catch (e) { /* private mode */ }
      state.maxStates = s.max_states;
      $("#code-status").textContent = s.paused ? "Code accepted, but live checks are paused right now. The sample reports still work."
        : `Code accepted. You have ${s.left_today} check${s.left_today === 1 ? "" : "s"} left today (up to ${s.max_states} state${s.max_states === 1 ? "" : "s"} per check).`;
      $("#states-max").textContent = s.max_states;
    } else {
      $("#code-status").textContent = `That code isn't valid. Check for typos, or email ${REQUEST_EMAIL} for one.`;
    }
    return s;
  } catch (e) {
    $("#code-status").textContent = friendly(e, "Couldn't reach the checking service. Please try again in a moment.");
    return null;
  }
}

/* exactly which rules each chosen state is checked against */
function ruleSources() {
  const list = state.states.filter((s) => state.chosen.has(s.state));
  $("#rule-sources").hidden = !list.length;
  $("#rule-sources").innerHTML = list.map((s) => `<li><b>${esc(stateName(s.state))}:</b> checked against <a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>, downloaded ${esc(new Date(`${s.retrieved}T12:00:00`).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" }))}.</li>`).join("");
}

function renderChips() {
  $("#state-chips").innerHTML = state.states.map((s) => {
    const on = state.chosen.has(s.state);
    return `<button type="button" class="chip${on ? " on" : ""}" aria-pressed="${on}" data-code="${s.state}" title="${esc(s.short || "")} · ${s.pdf_pages} pages">${esc(stateName(s.state))}${SCOPE[s.state] ? ` <small>(${SCOPE[s.state]})</small>` : ""}</button>`;
  }).join("");
  ruleSources();
}

async function init() {
  const sources = await CR.sources();
  state.states = Object.values(sources).sort((a, b) => stateName(a.state).localeCompare(stateName(b.state)));
  const wanted = (params.get("state") || "").toUpperCase().split(",").filter((s) => sources[s]);
  wanted.forEach((s) => state.chosen.add(s));
  renderChips();
  requestLink();
  heroStates(sources);
  const fromUrl = params.get("code");
  let saved = "";
  try { saved = localStorage.getItem("carerules-code") || ""; } catch (e) { /* private mode */ }
  if (fromUrl || saved) {
    $("#code").value = fromUrl || saved;
    checkCode().then((s) => {
      if (!s || !s.valid) return;  // a valid code: say what to do next instead of how to get one
      $("#code-first").innerHTML = `<p><b>Your access code is ready.</b> Add your parent handbook below, pick your state, and press Check. No handbook handy? Try a <a href="#test-handbook">sample handbook</a>.</p>`;
      $("#code-first").classList.add("welcome");
    });
  }
  if (location.hash === "#states") $("#states").open = true;
  if (location.hash === "#test-handbook") { $("#test-handbook").open = true; $("#test-handbook").scrollIntoView(); }

  const [sample, pages] = await Promise.all([getJson("samples/little-acorns.audit-high.json"), getJson("samples/little-acorns-pages.json")]);
  const light = await CR.light(sample.results);
  scan($("#hero-scan"), Object.values(light.scores).map((s) => ({ name: s.name, pages: s.pages, marks: s.marks })), { dur: 5 });
  demo(light.rows, light.scores);
  differ(light.rows, light.scores);
  markup(sample.results, pages, 4);
  pairs(light.rows, light.scores);
  $("#scoreboard").innerHTML = await CR.scoreCards(sample.results);

  state.sample = [await CR.report(sample.results, sample.name, sample.pages), CR.fixesMarkdown(sample.results, sample.name),
    `<span class="tag">Sample report</span><h2>Little Acorns Early Learning</h2><p class="sub">A fictional nonprofit with centers in Texas, North Carolina, and Oregon, and one shared parent handbook with some mistakes planted in it. <a href="samples/little-acorns-handbook.pdf" target="_blank" rel="noopener">Read the handbook (PDF)</a>.</p>`,
    "", "See the sample report: one handbook, checked for Texas, North Carolina and Oregon"];
  showReport(...state.sample);
  state.fixesName = "little-acorns-fixes";
  if (/hf\.space$/.test(location.hostname)) document.querySelectorAll("[data-promo]").forEach((el) => el.remove());  // keep the Space about the project
  observe();
  lightStatements();
  heroVideo();

  const examples = await getJson("samples/eval-results/index.json");
  $("#example-states").innerHTML = examples.map((x) => `<button type="button" class="chip" data-example="${x.code}" aria-pressed="false">${esc(x.name)}</button>`).join("");
  state.examples = Object.fromEntries(examples.map((x) => [x.code, x]));
  $("#test-states").innerHTML = examples.map((x) => `<option value="${x.code}">${esc(x.name)} — ${esc(x.title)}</option>`).join("");
}

/* the answer key under a sample report: what was planted, and whether the check found it */
function answerKey(key) {
  const yes = (ok) => (ok ? '<span class="ak-yes">✓ found</span>' : '<span class="ak-no">✕ not found</span>');
  return `<div class="answer-key"><h3 class="ci-h">Answer key</h3><p class="ci-dim">What we changed in this handbook before checking it, and whether the check caught it.</p>
    <h4 class="ci-h4">Sentences we changed to break a rule (${key.conflicts.length})</h4><ul>${key.conflicts.map((c) =>
      `<li>${yes(c.found)} “${esc(c.planted)}”<div class="ci-dim">${esc(c.why)}</div></li>`).join("")}</ul>
    <h4 class="ci-h4">Required policies removed (${key.removals.length})</h4><ul>${key.removals.map((r) =>
      `<li>${yes(["missing", "partial"].includes(r.status))} ${esc(r.requirement)} <span class="ci-dim">(marked ${esc(r.status || "not found")})</span></li>`).join("")}</ul></div>`;
}

/* reading the file as soon as it's chosen, so problems show before the check */
/* plain words for what file readers and networks throw */
function friendly(err, fallback) {
  const m = String((err && err.message) || "");
  if (/password/i.test(m)) return "This PDF is password-protected. Save a copy without a password and try again.";
  if (/Invalid PDF|PDF structure|Missing PDF|bad XRef/i.test(m)) return "This PDF couldn't be read. Try saving it again, or use the Word version.";
  if (/Failed to fetch|NetworkError|Load failed|network/i.test(m)) return "Couldn't reach the checking service. Check your internet connection and try again.";
  if (/Unexpected token|JSON/i.test(m)) return "The checking service had a problem. Please try again in a minute.";
  return m || fallback;
}

async function setFile(f, demo = null) {
  const seq = ++state.readSeq;  // a slower read of an earlier file must never replace a newer choice
  state.file = null; state.pages = null; state.fileError = ""; state.demo = demo;  // demo: a sample handbook's state
  $("#file-info").hidden = false;
  if (!f) return;
  $("#drop-text").innerHTML = `<b>${esc(f.name)}</b><br><small>${(f.size / 1024).toFixed(0)} KB · click to change</small>`;
  if (f.size > MAX_FILE) { $("#file-info").textContent = state.fileError = "That file is over 12 MB. Try a smaller copy, or the Word version."; return; }
  $("#file-info").textContent = "Reading the file…";
  try {
    const pages = await CR.readFile(f, await loadLibs(f));
    if (seq !== state.readSeq) return;
    const words = pages.reduce((a, [, t]) => a + t.split(/\s+/).filter(Boolean).length, 0);
    const empty = pages.filter(([, t]) => t.trim().split(/\s+/).length < 15).length;
    const chars = pages.reduce((a, [, t]) => a + t.length, 0);
    state.file = f; state.pages = pages;
    $("#file-info").textContent = `Read ${pages.length} page${pages.length === 1 ? "" : "s"}, about ${words.toLocaleString("en-US")} words.` +
      (empty ? ` ${empty} page${empty === 1 ? " has" : "s have"} little or no text (scanned pages can't be read).` : "") +
      (chars >= MAX_TEXT ? " This handbook is long, so only about the first 60,000 words will be checked." : "");
  } catch (err) {
    if (seq !== state.readSeq) return;
    $("#file-info").textContent = state.fileError = friendly(err, "Couldn't read this file. Try a PDF, Word (.docx) or text copy.");
  }
}

async function loadLibs(file) {
  const ext = (file.name.match(/\.[^.]+$/) || [""])[0].toLowerCase();
  const libs = {};
  if (ext === ".pdf") {
    libs.pdfjs = await import(LIBS.pdfjs);
    libs.pdfjs.GlobalWorkerOptions.workerSrc = LIBS.pdfWorker;
  } else if (ext === ".docx") {
    if (!window.mammoth) await new Promise((ok, fail) => {  // pinned by hash: a changed file on the CDN is refused
      const s = Object.assign(document.createElement("script"), { src: LIBS.mammoth, integrity: LIBS.mammothSri, crossOrigin: "anonymous", onload: ok, onerror: fail });
      document.head.append(s);
    });
    libs.mammoth = window.mammoth;
  }
  return libs;
}

function copyText(text, btn) {
  const done = () => { btn.textContent = "Copied"; setTimeout(() => (btn.textContent = "Copy"), 1500); };
  const fallback = () => {  // older browsers and pages without clipboard permission
    const t = Object.assign(document.createElement("textarea"), { value: text });
    document.body.append(t); t.select();
    try { document.execCommand("copy"); done(); } catch (e) { btn.textContent = "Press Ctrl+C"; }
    t.remove();
  };
  if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, fallback); else fallback();
}

/* inputs */
document.addEventListener("click", async (ev) => {
  const chip = ev.target.closest(".chip[data-code]");
  if (chip) {
    const c = chip.dataset.code;
    if (state.chosen.has(c)) state.chosen.delete(c);
    else if (state.chosen.size < state.maxStates) state.chosen.add(c);
    else help(`You can check up to ${state.maxStates} states at once.`, false);
    chip.classList.toggle("on", state.chosen.has(c));
    chip.setAttribute("aria-pressed", String(state.chosen.has(c)));
    requestLink();
    ruleSources();
  }
  const seg = ev.target.closest("#effort button");
  if (seg) {
    state.effort = seg.dataset.v;
    document.querySelectorAll("#effort button").forEach((b) => { b.classList.toggle("on", b === seg); b.setAttribute("aria-pressed", String(b === seg)); });
  }
  const copy = ev.target.closest("[data-copy]");
  if (copy) copyText(copy.dataset.copy, copy);
  if (ev.target.closest('a[href="#states"]')) $("#states").open = true;
  if (ev.target.closest('a[href="#terms"]')) $("#terms").open = true;
  if (ev.target.closest('a[href="#sample"]') && !state.running) $("#report-box").open = true;
  if (ev.target.closest('a[href="#test-handbook"]')) $("#test-handbook").open = true;
  const ex = ev.target.closest("[data-example]");
  if (ex) {
    document.querySelectorAll("[data-example]").forEach((b) => { b.classList.toggle("on", b === ex); b.setAttribute("aria-pressed", String(b === ex)); });
    const x = state.examples[ex.dataset.example];
    $("#example-report").innerHTML = '<p class="sub">Loading…</p>';
    const [r, key] = await Promise.all([getJson(`samples/eval-results/${x.code}.json`), getJson(`samples/eval-results/${x.code}.key.json`)]);
    $("#example-report").innerHTML = await CR.report({ [x.code]: r }, `${x.title}, made up with planted mistakes`, x.pages, "part") + answerKey(key);
  }
});

/* "Plant your own mistake": a compliant test handbook to edit and check */
$("#test-load").addEventListener("click", async () => {
  const code = $("#test-states").value;
  if (!code) return;  // the list is still loading
  const text = await fetch(`samples/eval/${code}/clean.md`).then((r) => r.text());
  $("#test-text").value = text;
  $("#test-edit").hidden = false;
  state.chosen = new Set([code]);
  renderChips(); requestLink();
});
/* One click: read the edited sample handbook and start the live check at once (no code, its own state, Standard). */
$("#test-use").addEventListener("click", async () => {
  if (state.running) return;  // a running check keeps its file
  const code = $("#test-states").value;
  $("#test-use").disabled = true;
  await setFile(new File([$("#test-text").value], `sample-handbook-${code}.md`, { type: "text/markdown" }), code);
  $("#test-use").disabled = false;
  state.chosen = new Set([code]); renderChips(); requestLink();
  if (!state.pages) { help(state.fileError || "Couldn't read the edited handbook. Load it again and retry."); return; }
  runCheck();
});

document.querySelectorAll(".choice").forEach((b) => b.addEventListener("click", () => {
  if (b.getAttribute("aria-disabled") === "true") return;
  document.querySelectorAll(".choice").forEach((c) => {
    c.classList.toggle("right", c.dataset.k === "b"); c.classList.toggle("dim", c.dataset.k !== "b");
    c.classList.toggle("picked", c === b); c.setAttribute("aria-disabled", "true");
  });
  $("#reveal-title").textContent = b.dataset.k === "b" ? "Right: it's B." : `You picked ${b.dataset.k.toUpperCase()}. It's B.`;
  $("#reveal-note").textContent = b.dataset.k === "b" ? "" : "Easy to miss, because the limit for four-year-olds is different in each state.";
  $("#reveal").hidden = false;
  $("#reveal").focus();
}));
$("#code").addEventListener("change", checkCode);
$("#code").addEventListener("input", () => {  // clearing the box clears the old verdict
  if ($("#code").value.trim()) return;
  $("#code").classList.remove("ok");
  $("#code-status").textContent = "Paste the code from our email.";
});

const drop = $("#drop"), input = $("#file");
input.addEventListener("change", () => setFile(input.files[0]));
["dragenter", "dragover"].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (ev) => { if (ev.dataTransfer.files[0]) setFile(ev.dataTransfer.files[0]); });

const help = (text, bad = true) => { $("#go-help").textContent = text; $("#go-help").classList.toggle("bad", !!text && bad); };

async function runCheck() {
  if (state.running) return;
  if (!state.pages) { help(state.fileError || "Add your parent handbook first."); drop.classList.add("over"); setTimeout(() => drop.classList.remove("over"), 900); return; }
  if (!state.chosen.size) { help("Pick your state first."); return; }
  let code = $("#code").value.trim(), status;
  const demo = !!state.demo;  // a sample handbook: no code needed (a typed code isn't spent on it), its own state, Standard
  if (!code && !demo) { $("#code").focus(); help(`Live checks need a free access code: email ${REQUEST_EMAIL}. Or try a sample handbook, no code needed.`); return; }
  if (demo) {
    code = "DEMO"; status = { max_states: 1 };
  } else {
    status = await checkCode();
    if (!status || !status.valid) { help($("#code-status").textContent); return; }
    if (status.paused) { help("Live checks are paused right now. The sample reports still work."); return; }
  }
  help("");
  const effort = demo ? "low" : state.effort;
  const chosen = demo ? [state.demo] : [...state.chosen].slice(0, status.max_states);
  const info = state.states.filter((s) => chosen.includes(s.state));
  // A retry of the same file, states and effort keeps its check id, so it doesn't use up another check.
  const file = state.file, pages = state.pages;  // a file chosen during the run must not change this check
  const same = `${file.name}|${file.size}|${file.lastModified}|${chosen.join(",")}|${effort}`;
  if (!state.last || state.last.key !== same) state.last = { key: same, id: `${Date.now()}-${Math.random().toString(36).slice(2, 10)}` };
  const check = state.last.id;
  state.running = true;
  $("#go").disabled = true;
  $("#progress").hidden = false;
  $("#report-head").innerHTML = ""; $("#report").innerHTML = ""; $("#actions").hidden = true;
  if ($("#backpr-box")) $("#backpr-box").hidden = true;
  $("#report-box").open = true;
  $("#report-summary").textContent = `Your report: ${file.name}`;
  input.disabled = true; drop.classList.add("busy");
  $("#sample").scrollIntoView({ behavior: "smooth" });
  scan($("#run-scan"), info.map((s) => ({ name: stateName(s.state), pages: s.pdf_pages, marks: [] })), { loop: true, dur: 3 });
  $("#run-scan").classList.add("go");
  const steps = ["Reading your handbook…", ...info.map((s) => `Reading the ${stateName(s.state)} rules that apply…`), "Comparing every policy with the rules…", "Checking every quote word for word…", "Writing suggested wording…"];
  let i = 0;
  $("#progress-text").textContent = steps[0];
  const timer = setInterval(() => { i = Math.min(i + 1, steps.length - 1); $("#progress-text").textContent = steps[i]; }, 6000);
  const callBeam = async (prompt, effort, retry = false) => {
    let res;
    try { res = await fetch(`${API}/beam`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code, check, effort, prompt, retry }) }); }
    catch (e) { throw new Error(friendly(e, "Couldn't reach the checking service. Please try again.")); }
    let data = {};
    try { data = await res.json(); } catch (e) { /* not JSON */ }
    if (!res.ok) throw new Error(data.error || "The check failed. Please try again; a failed try doesn't use up your check.");
    return data;
  };
  try {
    const { results, errors } = await CR.audit(pages, chosen, effort, callBeam);
    if (!Object.keys(results).length) throw new Error(Object.values(errors)[0] || "The check failed. Please try again.");
    const notes = [];
    if (demo) notes.push(`A live check of a sample handbook against ${esc(stateName(chosen[0]))}'s rules. To check your own handbook, email ${REQUEST_EMAIL} for a free access code.`);
    else if (chosen.length < state.chosen.size) notes.push(`Your code covers ${status.max_states} states per check, so only the first ${status.max_states} were checked.`);
    for (const [s, msg] of Object.entries(errors)) notes.push(`${esc(stateName(s))} couldn't be checked: ${esc(msg)} Press Check again to retry; it won't use up another check.`);
    if (CR.suspicious(pages)) notes.push("Your handbook contains text that reads like instructions to an AI. CareRules ignores it, but read these findings with extra care.");
    const base = file.name.replace(/\.[^.]+$/, "");
    state.fixesName = `${base}-fixes`;
    const unit = /\.pdf$/i.test(file.name) ? "page" : "part";  // Word and text files have no fixed pages
    showReport(await CR.report(results, file.name, pages.length, unit), CR.fixesMarkdown(results, file.name, unit),
      `<span class="tag">Your report</span><h2>${esc(file.name)}</h2>`, notes.join("<br>"), `Your report: ${file.name}`);
  } catch (err) {  // put the sample report back, with the error on top
    showReport(...state.sample);
    state.fixesName = "little-acorns-fixes";
    $("#report").insertAdjacentHTML("afterbegin", `<div class="error" role="alert">${esc(friendly(err, "The check failed. Please try again."))} <button type="button" class="ci-copy" id="retry">Try again</button></div>`);
  } finally {
    clearInterval(timer);
    state.running = false;
    input.disabled = false; drop.classList.remove("busy");
    $("#progress").hidden = true; $("#go").disabled = false;
    checkCode();
  }
}
$("#go").addEventListener("click", runCheck);
document.addEventListener("click", (ev) => { if (ev.target.id === "retry") $("#go").click(); });

const save = (blob, name) => {
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
$("#dl").addEventListener("click", () => save(new Blob([state.fixes.replace(/^#+ /gm, "")], { type: "text/plain" }), `${state.fixesName}.txt`));
$("#dl-word").addEventListener("click", () => {  // Word opens simple HTML saved as .doc
  const html = state.fixes.split("\n").map((l) => (l.startsWith("# ") ? `<h1>${esc(l.slice(2))}</h1>` : l.startsWith("## ") ? `<h2>${esc(l.slice(3))}</h2>`
    : l.startsWith("### ") ? `<h3>${esc(l.slice(4))}</h3>` : l === "---" ? "<hr>" : l ? `<p>${esc(l)}</p>` : "")).join("\n");
  save(new Blob([`<html><head><meta charset="utf-8"></head><body style="font-family:Calibri,Arial,sans-serif">${html}</body></html>`], { type: "application/msword" }), `${state.fixesName}.doc`);
});
$("#print").addEventListener("click", () => { $("#report-box").open = true; document.querySelectorAll("#report details").forEach((d) => (d.open = true)); window.print(); });

init().catch((err) => { $("#report").innerHTML = `<div class="error" role="alert">Couldn't load: ${esc(err.message)}</div>`; });
