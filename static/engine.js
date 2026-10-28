/* CareRules engine for the browser: the same quote checker, page search, prompts, verification, scoring and report
   as the Python package (carerules/corpus.py, audit.py, view.py), so the Space can run as a free static page. Beam is
   reached through a small Worker that holds the token and enforces access codes; every check of Beam's output runs
   here, against the official texts this page serves. Also loads in Node for parity tests (module.exports). */
(function (root) {
  "use strict";
  const CR = {};
  const BASE = (typeof location !== "undefined" ? "" : "") + "";
  CR.data = { base: "./", sources: null, cache: {} };

  /* ---------- text normalization and word-for-word matching (corpus.py) ---------- */
  const DASHES = /[‐‑‒–—―−­-]/g;
  // Texas prints a weight after each rule ("[Medium-High]"); it isn't part of the rule's words, so quotes may leave it out.
  const WEIGHT = /\[(?:low|medium|high)(?:[- ]?(?:low|medium|high))?\]/gi;
  CR.norm = (text) => (String(text || "").normalize("NFKC").replace(WEIGHT, " ").toLowerCase().replace(DASHES, "").match(/[a-z0-9§]+/g) || []).join(" ");
  CR.unweight = (text) => String(text || "").replace(WEIGHT, "").replace(/\s+([;,.])/g, "$1").replace(/ {2,}/g, " ").trim();
  const MAX_GAP = 300;  // normalized characters (about 60 words) a "..." may skip
  const SHORT_SKIP = 120, NEGATION = new Set(["not", "no", "never", "nor", "neither", "cannot", "t", "except", "unless", "without"]);

  /* One string per document with spaces removed ("9 – 13 years" must match "9-13 years"), page offsets, and where
     words start and end, so a quote must begin and end on whole words ("attended" never matches in "unattended"). */
  CR.buildIndex = (pages) => {
    const parts = [], offsets = [], starts = [], ends = [];
    let pos = 0;
    for (const [number, text] of pages) {
      offsets.push([pos, number]);
      for (const w of CR.norm(text).split(" ").filter(Boolean)) {
        starts.push(pos);
        if (w.startsWith("§") && w.length > 1) starts.push(pos + 1);  // "746.1601" may be quoted without its §
        pos += w.length;
        ends.push(pos);
        parts.push(w);
      }
    }
    const flags = (list) => { const a = new Uint8Array(pos + 2); for (const i of list) a[i] = 1; return a; };
    return { hay: parts.join(""), offsets, starts: flags(starts), ends: flags(ends) };
  };
  const pageAt = (index, i) => {
    let page = index.offsets.length ? index.offsets[0][1] : 1;
    for (const [begin, number] of index.offsets) { if (begin > i) break; page = number; }
    return page;
  };

  /* (page, start, end) where the quote appears word for word, or null. "..." skips text between fragments that
     appear in order within maxGap characters; a quote needs 6+ words with one fragment of 4+. */
  CR.match = (index, quote, maxGap = MAX_GAP) => {
    let frags = String(quote || "").split(/\.\.\.|…/).map(CR.norm).filter(Boolean);
    if (!frags.length) return null;
    const words = frags.map((f) => f.split(" ").length);
    if (words.reduce((a, b) => a + b, 0) < 6 || Math.max(...words) < 4) return null;
    frags = frags.map((f) => f.replace(/ /g, ""));
    const { hay, starts, ends } = index;
    const find = (f, at) => {  // next whole-word occurrence of f at or after `at`
      let i = hay.indexOf(f, at);
      while (i !== -1 && !(starts[i] && ends[i + f.length])) i = hay.indexOf(f, i + 1);
      return i;
    };
    const flips = (a, b) => {  // a short "..." skip must not drop a "not" (it would reverse the rule)
      if (b - a > SHORT_SKIP || maxGap > MAX_GAP) return false;
      const cuts = [];
      for (let j = a; j < b; j++) if (starts[j]) cuts.push(j);
      cuts.push(b);
      return cuts.slice(0, -1).some((x, i) => NEGATION.has(hay.slice(x, cuts[i + 1])));
    };
    let start = find(frags[0], 0);
    while (start !== -1) {
      let pos = start + frags[0].length, ok = true;
      for (const f of frags.slice(1)) {
        const nxt = find(f, pos);
        if (nxt === -1 || nxt - pos > maxGap || flips(pos, nxt)) { ok = false; break; }
        pos = nxt + f.length;
      }
      if (ok) return [pageAt(index, start), start, pos];
      start = find(frags[0], start + 1);
    }
    return null;
  };

  /* Like match, but when a quote runs past what the document says (two table rows joined into one quote), keep the
     longest leading or trailing part that does appear: at least 6 words and half the quote. [match, verified text] */
  CR.matchLoose = (index, quote) => {
    const m = CR.match(index, quote);
    if (m) return [m, quote];
    const words = String(quote || "").split(/\s+/).filter(Boolean);
    if (/\.\.\.|…/.test(quote) || words.length < 7) return null;
    for (let k = words.length - 1; k >= Math.max(6, Math.ceil(words.length / 2)); k--) {
      for (const part of [words.slice(0, k).join(" "), words.slice(-k).join(" ")]) {
        const got = CR.match(index, part);
        if (got) return [got, part.replace(/^[\s,;:]+|[\s,;:]+$/g, "")];
      }
    }
    return null;
  };

  /* ---------- BM25 over rulebook pages (corpus.Index) ---------- */
  class Index {
    constructor(pages, k1 = 1.2, b = 0.75) {
      this.docs = pages;
      this.toks = pages.map((p) => CR.norm(p.text).split(" ").filter(Boolean));
      this.tf = this.toks.map((t) => { const m = new Map(); for (const w of t) m.set(w, (m.get(w) || 0) + 1); return m; });
      this.avg = this.toks.reduce((a, t) => a + t.length, 0) / Math.max(1, this.toks.length);
      const df = new Map();
      for (const m of this.tf) for (const w of m.keys()) df.set(w, (df.get(w) || 0) + 1);
      const n = pages.length;
      this.idf = new Map([...df].map(([w, d]) => [w, Math.log(1 + (n - d + 0.5) / (d + 0.5))]));
      this.k1 = k1; this.b = b;
    }
    search(query, k = 5) {
      const q = CR.norm(query).split(" ").filter((w) => this.idf.has(w));
      const scored = [];
      this.docs.forEach((p, i) => {
        const tf = this.tf[i], dl = this.toks[i].length;
        let s = 0;
        for (const w of q) {
          const f = tf.get(w);
          if (f) s += this.idf.get(w) * f * (this.k1 + 1) / (f + this.k1 * (1 - this.b + this.b * dl / this.avg));
        }
        if (s > 0) scored.push([s, p]);
      });
      scored.sort((a, b) => b[0] - a[0]);
      return scored.slice(0, k);
    }
  }
  CR.Index = Index;

  /* ---------- data: sources, rulebook pages, checklists ---------- */
  const fetchText = async (path) => {
    if (CR.data.loader) return CR.data.loader(path);  // Node tests read local files
    const r = await fetch(CR.data.base + path);
    if (!r.ok) throw new Error(`Couldn't load ${path}`);
    return r.text();
  };
  CR.sources = async () => {
    if (!CR.data.sources) CR.data.sources = Object.fromEntries(JSON.parse(await fetchText("data/sources.json")).map((s) => [s.state, s]));
    return CR.data.sources;
  };
  CR.rulebook = async (state) => {
    const key = "rb:" + state;
    if (!CR.data.cache[key]) {
      const raw = await fetchText(`text/${state}.txt`);
      const pages = raw.split("\f").map((t, i) => ({ number: i + 1, text: t })).filter((p) => p.text.trim());
      const byNumber = new Map(pages.map((p) => [p.number, p]));
      CR.data.cache[key] = { pages, byNumber, index: null, normed: null };
    }
    return CR.data.cache[key];
  };
  CR.checklist = async (state) => {
    const key = "cl:" + state;
    if (!CR.data.cache[key]) CR.data.cache[key] = JSON.parse(await fetchText(`data/checklists/${state}.json`)).items;
    return CR.data.cache[key];
  };
  const normed = async (state) => {
    const rb = await CR.rulebook(state);
    if (!rb.normed) rb.normed = CR.buildIndex(rb.pages.map((p) => [p.number, p.text]));
    return rb;
  };
  CR.findQuote = async (state, quote) => {
    const m = CR.match((await normed(state)).normed, quote);
    return m ? m[0] : null;
  };

  /* Guidance inside a rulebook (Texas "Technical Assistance" boxes, California "Handbook" text) explains the rules
     but isn't one, so it never counts as the rule a handbook breaks. (corpus.is_guidance) */
  const GUIDANCE = { TX: [/^technical assistance\b/i, /^§\s?746\.\d+\./], CA: [/^handbook begins here/i, /^handbook ends here/i] };
  CR.GUIDANCE_NAME = { TX: 'a Texas "Technical Assistance" box', CA: "California's handbook (explanatory) text" };
  CR.isGuidance = async (state, start) => {
    if (!GUIDANCE[state]) return false;
    const rb = await normed(state);
    if (!rb.lines) {
      rb.lines = [];
      let pos = 0;
      for (const p of rb.pages) for (const line of p.text.split("\n")) { rb.lines.push([pos, line.trim()]); pos += CR.norm(line).replace(/ /g, "").length; }
    }
    const [opener, closer] = GUIDANCE[state], lines = rb.lines;
    let lo = 0, hi = lines.length - 1;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (lines[mid][0] <= start) lo = mid; else hi = mid - 1; }
    for (let i = lo; i > Math.max(-1, lo - 400); i--) {
      if (closer.test(lines[i][1])) return false;
      if (opener.test(lines[i][1])) return true;
    }
    return false;
  };
  /* [page, verified text, is guidance] for a rule quote, allowing the loose match above. (corpus.find_rule) */
  CR.findRule = async (state, quote) => {
    const got = CR.matchLoose((await normed(state)).normed, quote);
    if (!got) return null;
    const [[page, start], text] = got;
    return [page, text, await CR.isGuidance(state, start)];
  };
  /* A short table row ("0 – 11 months 4") proves itself only on the page of the rule it belongs to: whole words,
     at least 3, with a number, on `page` or the next one. (corpus.find_row) */
  CR.findRow = async (state, quote, page) => {
    const words = CR.norm(quote).split(" ").filter(Boolean);
    if (words.length < 3 || !words.some((w) => /^\d+$/.test(w))) return null;
    const idx = (await normed(state)).normed;
    const inRange = idx.offsets.filter(([, n]) => n === page || n === page + 1);
    if (!inRange.length) return null;
    const after = idx.offsets.find(([, n]) => n > page + 1);
    const lo = inRange[0][0], hi = after ? after[0] : idx.hay.length, f = words.join("");
    for (let i = idx.hay.indexOf(f, lo); i !== -1 && i + f.length <= hi; i = idx.hay.indexOf(f, i + 1)) {
      if (idx.starts[i] && idx.ends[i + f.length]) return [pageAt(idx, i), String(quote).trim(), await CR.isGuidance(state, i)];
    }
    return null;
  };
  CR.pageUrl = (src, page) => (!src || !src.url ? "" : (src.format || "pdf") === "pdf" ? `${src.url}#page=${page}` : src.url);

  /* ---------- focused context and prompt (audit.py) ---------- */
  const MAX_CONTEXT_CHARS = 140000, CHUNK = 60;
  CR.focusedPages = async (state, items, handbook) => {
    const rb = await CR.rulebook(state);
    const chosen = [];
    for (const it of items) {
      if (/^\d+$/.test(String(it.page ?? ""))) for (const n of [+it.page, +it.page + 1]) if (rb.byNumber.has(n) && !chosen.includes(n)) chosen.push(n);
    }
    if (!rb.index) rb.index = new Index(rb.pages);
    for (const [, text] of handbook) {
      for (let i = 0; i < text.length; i += 1500) {
        for (const [, p] of rb.index.search(text.slice(i, i + 1500), 2)) if (!chosen.includes(p.number)) chosen.push(p.number);
      }
    }
    const out = [];
    let size = 0;
    for (const n of chosen) { size += rb.byNumber.get(n).text.length; if (size > MAX_CONTEXT_CHARS) break; out.push(n); }
    return out.sort((a, b) => a - b);
  };

  CR.prompt = async (state, items, handbook) => {
    const src = (await CR.sources())[state] || {};
    const rb = await CR.rulebook(state);
    const keep = new Set(await CR.focusedPages(state, items, handbook));
    const body = rb.pages.filter((p) => keep.has(p.number)).map((p) => `[${state} page ${p.number}]\n${p.text.trim()}`).join("\n");
    const context = `=== RULEBOOK ${state}: ${src.title || state} — the ${keep.size} pages relevant to this handbook, out of ${src.pdf_pages ?? "?"} (page numbers are the official document's) ===\n${body}`;
    const listing = items.map((i) => `- ${i.id} [${i.kind}] ${i.requirement} (${i.section}, page ${i.page}): "${i.quote}"`).join("\n");
    const doc = handbook.map(([n, t]) => `[Handbook page ${n}]\n${t.trim()}`).join("\n");
    return `${context}\n\n=== CHECKLIST for ${src.title || state} ===\n${listing}\n\n=== THE CENTER'S HANDBOOK ===\n${doc}\n\n` +
      "You are a careful licensing inspector. Audit the handbook against the checklist and the rulebook above.\n" +
      "For EVERY checklist item, give a status:\n" +
      "- covered: the handbook clearly addresses it and agrees with the rule\n" +
      "- partial: it addresses it but leaves out something the rule requires\n" +
      "- conflict: the handbook says something the rule forbids or contradicts (for example a number the rule " +
      "doesn't allow, or permission the rule requires in writing given verbally)\n" +
      "Call something a conflict only if the exact rule words you give as rule_quote show it, and write the " +
      "explanation from those words alone: if a rule allows several ways (for example in writing, electronically, " +
      "or by phone for one dose), say which condition the handbook misses, never that an allowed way is forbidden.\n" +
      "Apply only rules for the kind of program the handbook describes. Rules that apply only to special programs " +
      "(for example a state-funded pre-K program, get-well or sick care, night care, or family child care homes) " +
      "don't apply unless the handbook says the center runs one; a room merely named \"Pre-K\" isn't one.\n" +
      "- missing: a [must_include] item the handbook doesn't address at all\n" +
      "- not_mentioned: a [rule] item the handbook doesn't mention (that's allowed)\n" +
      "Then look for any OTHER statement in the handbook that contradicts the rulebook.\n\n" +
      "Quotes must be copied exactly (8 to 60 words): handbook_quote from the handbook, rule_quote from the " +
      "rulebook. For missing and partial items and every conflict, write a fix: a paragraph the center can paste into " +
      "its handbook, in plain, warm language, that meets the rule without adding requirements the rule doesn't " +
      "have. Use [brackets] for details only the center knows (times, names, phone numbers).\n\n" +
      "Keep it short: for covered items give only id, status and handbook_quote; for not_mentioned items only id " +
      "and status. Explanations and fixes are only for partial, missing and conflict items.\n\n" +
      'Reply with only a JSON object: {"items": [{"id", "status", "handbook_quote", "handbook_page", ' +
      '"rule_quote" (for a conflict: the exact rulebook words the handbook breaks, such as the table row with the ' +
      'number; else empty), "rule_section" (the section that rule_quote comes from, as printed), ' +
      '"explanation" (one plain sentence), "fix"}], "extra_conflicts": [{"title", "handbook_quote", ' +
      '"handbook_page", "rule_quote", "section", "page", "explanation", "fix"}], "summary" (two sentences)}.';
  };

  /* ---------- reading Beam's reply (grade.parse_json) ---------- */
  CR.parseJson = (text) => {
    text = String(text || "").trim();
    try { return JSON.parse(text); } catch (e) { /* fall through */ }
    const blocks = [...text.matchAll(/```(?:json)?\s*([\s\S]*?)```/g)].map((m) => m[1]).reverse();
    for (const b of blocks) { try { return JSON.parse(b); } catch (e) { /* next */ } }
    const starts = [text.indexOf("{"), text.indexOf("[")].filter((i) => i !== -1).sort((a, b) => a - b);
    for (const start of starts) {
      const closer = text[start] === "{" ? "}" : "]";
      let end = text.lastIndexOf(closer);
      while (end > start) {
        try { return JSON.parse(text.slice(start, end + 1)); } catch (e) { end = text.lastIndexOf(closer, end - 1); }
      }
    }
    return null;
  };

  /* ---------- verification and scoring (audit.assemble, score, statements, cross_state) ---------- */
  const STATUSES = ["covered", "partial", "missing", "conflict", "not_mentioned"];
  const NOT_THERE = "but the words it quoted don't appear in your handbook exactly as written (it may have joined two lines, such as two rows of a table).";
  const HANDBOOK_NOTE = { conflict: `Beam flagged this as a conflict, ${NOT_THERE}`, partial: `Beam flagged this as incomplete, ${NOT_THERE}`,
    covered: `Beam marked this as covered, ${NOT_THERE}` };
  const CONFLICT_PENALTY = 5, ROW = 80;

  CR.sectionLabel = async (state, label, page) => {
    label = String(label || "").replace(/,?\s*\(?page\s*\d+\)?\s*$/i, "").trim();
    const nums = label.match(/\d[\d.\-]*\d/g) || [];
    const core = nums.reduce((a, b) => (b.length > a.length ? b : a), "");
    const rb = await CR.rulebook(state);
    const near = " " + rb.pages.filter((p) => p.number === page || p.number === page - 1).map((p) => CR.norm(p.text)).join(" ").replace(/§/g, " ") + " ";
    return label && core && near.includes(` ${CR.norm(core)} `) ? label : `rule on page ${page}`;
  };

  CR.statements = (findings) => {
    const hits = findings.filter((f) => f.status === "conflict" && f.span).sort((a, b) => a.span[0] - b.span[0]);
    const groups = [];
    for (const f of hits) {
      if (groups.length) {
        const g = groups[groups.length - 1];
        const end = Math.max(...g.map((x) => x.span[1]));
        const last = g[g.length - 1];
        const short = f.span[1] - f.span[0] <= ROW && last.span[1] - last.span[0] <= ROW;
        if (f.span[0] < end || (short && f.span[0] - end <= ROW)) { g.push(f); continue; }
      }
      groups.push([f]);
    }
    return groups;
  };

  const pyRound = (x) => { const r = Math.round(x); return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r; };  // Python's round()
  CR.score = (findings) => {
    const must = findings.filter((f) => f.kind === "must_include");
    const credit = must.reduce((a, f) => a + (f.status === "covered" ? 1 : f.status === "partial" ? 0.5 : 0), 0);
    const passages = CR.statements(findings).length;
    const base = must.length ? 100 * credit / must.length : 100;
    const counts = Object.fromEntries([...STATUSES, "unverified"].map((s) => [s, findings.filter((f) => f.status === s).length]));
    counts.conflict_statements = passages;
    return { score: Math.max(0, pyRound(base - CONFLICT_PENALTY * passages)), coverage: pyRound(base), required: must.length, counts };
  };

  CR.assemble = async (state, handbook, content, meta) => {
    const items = await CR.checklist(state);
    const src = (await CR.sources())[state] || {};
    const got = CR.parseJson(content);
    if (meta.finish === "length" || !got || typeof got !== "object" || Array.isArray(got) || !Array.isArray(got.items) || !got.items.length) {
      throw new Error(`Beam's answer for ${name(state)} was cut off or couldn't be read. Please try again.`);
    }
    const hb = CR.buildIndex(handbook);
    const answers = Object.fromEntries(got.items.filter((a) => a && typeof a === "object").map((a) => [String(a.id), a]));
    const findings = [];
    for (let it of items) {
      const a = answers[it.id] || {};
      let status = STATUSES.includes(a.status) ? a.status : it.kind === "must_include" ? "missing" : "not_mentioned";
      if (status === "not_mentioned" && it.kind === "must_include") status = "missing";
      const hq = String(a.handbook_quote || "").trim();
      const m = hq ? CR.match(hb, hq) : null;
      const hpage = m ? m[0] : null, span = m ? [m[1], m[2]] : null;
      let note = "";
      if (["covered", "partial", "conflict"].includes(status) && !hpage) {  // the words aren't there: never shown as fact
        note = hq ? HANDBOOK_NOTE[status] : "Beam didn't quote your handbook for this.";
        status = "unverified";
      }
      const rq = String(a.rule_quote || "").trim();
      if (status === "conflict") {
        let rule = rq ? await CR.findRule(state, rq) : null;
        const row = rule || !rq || !/^\d+$/.test(String(it.page)) ? null : await CR.findRow(state, rq, +it.page);
        if (row) rule = [row[0], `${it.quote} … ${row[1]}`, row[2]];  // a table row, proven on the checklist rule's page
        if (!rule) {  // a conflict has to name rule words that are really there
          status = "unverified"; note = "Beam flagged this as a conflict, but the rule words it gave don't match the official text.";
        } else if (rule[2]) {
          status = "unverified"; note = `Beam flagged this as a conflict, but the words it quoted are from ${CR.GUIDANCE_NAME[state]}, which is guidance, not a rule.`;
        } else if (row) {
          it = { ...it, quote: rule[1], page: rule[0] };
        } else {  // the exact clause broken, proven word for word, replaces the checklist's general quote
          it = { ...it, quote: rule[1], page: rule[0], section: await CR.sectionLabel(state, a.rule_section, rule[0]) };
        }
      }
      findings.push({ ...it, status, handbook_quote: hpage ? hq : "", handbook_page: hpage, span,
        explanation: String(a.explanation || "").trim(), note,
        fix: ["missing", "partial", "conflict"].includes(status) ? String(a.fix || "").trim() : "",
        rule_url: /^\d+$/.test(String(it.page)) ? CR.pageUrl(src, it.page) : "" });
    }
    const extras = [];
    for (const x of Array.isArray(got.extra_conflicts) ? got.extra_conflicts : []) {
      if (!x || typeof x !== "object") continue;
      const m = CR.match(hb, String(x.handbook_quote || ""));
      const rule = await CR.findRule(state, String(x.rule_quote || ""));
      if (m && rule && !rule[2]) {  // both quotes proven, from a rule (not guidance), or it isn't shown
        const rpage = rule[0];
        extras.push({ id: "extra_" + (extras.length + 1), topic: "other", kind: "rule", status: "conflict",
          requirement: String(x.title || "Conflict with the rulebook"), section: await CR.sectionLabel(state, x.section, rpage),
          page: rpage, quote: rule[1], handbook_quote: String(x.handbook_quote).trim(), handbook_page: m[0],
          span: [m[1], m[2]], explanation: String(x.explanation || "").trim(), note: "", fix: String(x.fix || "").trim(),
          rule_url: CR.pageUrl(src, rpage) });
      }
    }
    findings.push(...extras);
    return { state, rulebook: src.title || "", findings, summary: String(got.summary || "").trim(), ...CR.score(findings), ...meta, raw: content };
  };

  CR.crossState = (results) => {
    const every = [];
    for (const [s, r] of Object.entries(results)) for (const f of r.findings) if (f.status === "conflict" && f.span) every.push({ ...f, _state: s });
    const rows = CR.statements(every).map((group) => {
      const byState = {};
      for (const f of group) if (!byState[f._state]) byState[f._state] = f;
      const lead = group.reduce((a, f) => (f.handbook_quote.length > a.handbook_quote.length ? f : a), group[0]);
      return { handbook_quote: lead.handbook_quote, handbook_page: lead.handbook_page, states: byState,
        verdict: Object.fromEntries(Object.keys(results).map((s) => [s, byState[s] ? "conflict" : "ok"])) };
    });
    return rows.sort((a, b) => (Object.keys(b.states).length - Object.keys(a.states).length) || ((a.handbook_page || 0) - (b.handbook_page || 0)));
  };

  /* ---------- running a check: one Beam call per state (split when the checklist is long) ---------- */
  CR.auditState = async (state, handbook, effort, callBeam) => {
    const items = await CR.checklist(state);
    const chunks = [];
    for (let i = 0; i < items.length; i += CHUNK) chunks.push(items.slice(i, i + CHUNK));
    const replies = await Promise.all(chunks.map(async (part, i) => {
      let prompt = await CR.prompt(state, part, handbook);
      if (i > 0) prompt += "\nFor this part, leave extra_conflicts empty.";
      return callBeam(prompt, effort);
    }));
    const merged = { items: [], extra_conflicts: [], summary: "" };
    let finish = "stop";
    for (const rep of replies) {
      const got = CR.parseJson(rep.content);
      if (rep.finish === "length" || !got || typeof got !== "object" || !Array.isArray(got.items) || !got.items.length) { finish = "length"; continue; }
      merged.items.push(...got.items);
      if (Array.isArray(got.extra_conflicts)) merged.extra_conflicts.push(...got.extra_conflicts);
      merged.summary = merged.summary || String(got.summary || "");
    }
    const meta = { cost: +replies.reduce((a, r) => a + (r.cost || 0), 0).toFixed(4),
      tokens_in: replies.reduce((a, r) => a + (r.tokens_in || 0), 0), tokens_out: replies.reduce((a, r) => a + (r.tokens_out || 0), 0),
      finish, seconds: Math.max(...replies.map((r) => r.seconds || 0)), effort, calls: replies.length,
      cached: replies.every((r) => r.cached) };
    return CR.assemble(state, handbook, JSON.stringify(merged), meta);
  };

  /* Every state at once; one state failing doesn't lose the others. Returns {results, errors} by state. */
  CR.audit = async (handbook, states, effort, callBeam) => {
    const one = async (s) => {
      try { return await CR.auditState(s, handbook, effort, callBeam); }
      catch (err) {
        if (!/cut off|couldn't be read/i.test(err.message)) throw err;  // only a cut-off or unreadable answer is retried
        // One more try at low effort, asking Beam to sample instead of repeating the same runaway answer.
        const r = await CR.auditState(s, handbook, "low", (prompt, eff) => callBeam(prompt, eff, true));
        if (effort !== "low") r.effort = `low (the ${effort}-effort answer was cut off)`;
        return r;
      }
    };
    const settled = await Promise.allSettled(states.map(one));
    const results = {}, errors = {};
    settled.forEach((x, i) => { if (x.status === "fulfilled") results[states[i]] = x.value; else errors[states[i]] = x.reason.message || String(x.reason); });
    return { results, errors };
  };

  /* ---------- reading an uploaded handbook into pages (document.py) ---------- */
  const MAX_CHARS = 240000;
  CR.chunk = (text, size = 3000) => {
    const pages = [];
    let cur = "";
    for (const para of text.split(/\n\s*\n/)) {
      if (cur && cur.length + para.length > size) { pages.push(cur); cur = ""; }
      cur += para.trim() + "\n\n";
    }
    if (cur.trim()) pages.push(cur);
    return pages.map((t, i) => [i + 1, t]);
  };
  CR.readFile = async (file, libs) => {
    const ext = (file.name.match(/\.[^.]+$/) || [""])[0].toLowerCase();
    let pages;
    if (ext === ".pdf") {
      const pdf = await libs.pdfjs.getDocument({ data: await file.arrayBuffer() }).promise;
      pages = [];
      for (let i = 1; i <= pdf.numPages; i++) {
        const content = await (await pdf.getPage(i)).getTextContent();
        pages.push([i, content.items.map((x) => x.str + (x.hasEOL ? "\n" : " ")).join("")]);
      }
    } else if (ext === ".docx") {
      pages = CR.chunk((await libs.mammoth.extractRawText({ arrayBuffer: await file.arrayBuffer() })).value);
    } else if (ext === ".txt" || ext === ".md") {
      pages = CR.chunk(await file.text());
    } else {
      throw new Error("Upload a PDF, Word (.docx) or text file.");
    }
    const out = [];
    let total = 0;
    for (const [n, t] of pages) {
      if (total >= MAX_CHARS) break;
      const text = t.slice(0, MAX_CHARS - total);
      total += text.length;
      out.push([n, text]);
    }
    if (out.reduce((a, [, t]) => a + t.split(/\s+/).filter(Boolean).length, 0) < 150) {
      throw new Error("Couldn't read enough text from this file. If it's a scanned PDF, upload the Word version.");
    }
    return out;
  };

  /* ---------- the report (view.py) ---------- */
  const NAMES = { AL: "Alabama", AR: "Arkansas", AZ: "Arizona", CA: "California", CO: "Colorado", DC: "District of Columbia",
    FL: "Florida", GA: "Georgia", IA: "Iowa", IL: "Illinois", MA: "Massachusetts", MI: "Michigan", MO: "Missouri",
    MS: "Mississippi", NC: "North Carolina", ND: "North Dakota", NJ: "New Jersey", NM: "New Mexico", NY: "New York",
    OH: "Ohio", OK: "Oklahoma", OR: "Oregon", PA: "Pennsylvania", SC: "South Carolina", TX: "Texas", VA: "Virginia", WA: "Washington" };
  const COLORS = { conflict: "#ff5d6c", missing: "#f5a524", partial: "#ffe186", covered: "#3ddc97", not_mentioned: "#71717a", unverified: "#a78bfa" };
  const LABELS = { conflict: "Breaks a rule", missing: "Missing", partial: "Incomplete", covered: "Covered",
    not_mentioned: "Not mentioned (not required)", unverified: "Couldn't confirm: check by hand" };
  CR.NAMES = NAMES; CR.COLORS = COLORS;
  const e = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;" }[c]));
  const name = (s) => NAMES[s] || s;

  const ring = (score) => {
    const r = 38, c = 2 * Math.PI * 38;
    const color = score >= 80 ? "#3ddc97" : score >= 50 ? "#ffe186" : "#ff5d6c";
    return `<svg width="92" height="92" viewBox="0 0 92 92" role="img" aria-label="Score ${score} of 100">` +
      `<circle cx="46" cy="46" r="${r}" fill="none" stroke="currentColor" stroke-opacity=".12" stroke-width="8"/>` +
      `<circle cx="46" cy="46" r="${r}" fill="none" stroke="${color}" stroke-width="8" stroke-linecap="round" ` +
      `stroke-dasharray="${(c * score / 100).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 46 46)"/>` +
      `<text x="46" y="49" text-anchor="middle" font-size="24" font-weight="700" fill="currentColor">${score}</text>` +
      `<text x="46" y="64" text-anchor="middle" font-size="11" fill="currentColor" fill-opacity=".6">/100</text></svg>`;
  };

  /* Score cards: the score, then the two things it's made of, so the numbers add up on their face. */
  const scoreCards = (results, src) => `<div class="ci-cards">${Object.entries(results).map(([st, r]) => {
    const c = r.counts, must = r.findings.filter((f) => f.kind === "must_include");
    const n = (s) => must.filter((f) => f.status === s).length;
    const plural = (k, one, many) => `${k} ${k === 1 ? one : many}`;
    const req = [["covered", "covered", n("covered")], ["partial", "incomplete", n("partial")], ["missing", "missing", n("missing")],
      ["conflict", "break a rule", n("conflict")], ["unverified", "to check", n("unverified")]]
      .filter(([s, , k]) => k || ["covered", "partial", "missing"].includes(s)).map(([s, l, k]) => `<span style="color:${COLORS[s]}">${k} ${l}</span>`).join(" · ");
    const other = [["conflict", plural(c.conflict_statements, "sentence breaks a rule", "sentences break a rule")], ["unverified", `${c.unverified} to check by hand`]]
      .filter(([s]) => (s === "conflict" ? c.conflict_statements : c.unverified)).map(([s, l]) => `<span style="color:${COLORS[s]}">${l}</span>`).join(" · ");
    return `<div class="ci-card">${ring(r.score)}<div><div class="ci-state">${e(name(st))}</div>` +
      `<div class="ci-dim">Score out of 100 · ${e((src[st] || {}).short || "")}</div>` +
      `<div class="ci-line">Required policies (${r.required}): ${req || "none"}</div>` +
      `<div class="ci-line">${other || '<span style="color:' + COLORS.covered + '">No sentence breaks a rule</span>'}</div></div></div>`;
  }).join("")}</div>`;

  const matrix = (results) => {
    const rows = CR.crossState(results), states = Object.keys(results);
    if (!rows.length || states.length < 2) return "";
    const head = states.map((s) => `<th>${e(name(s))}</th>`).join("");
    const body = rows.map((row) => `<tr><td class="ci-q">${CR.isTableRow(row.handbook_quote) ? "Table row: " : ""}“${e(row.handbook_quote.slice(0, 150))}${row.handbook_quote.length > 150 ? "…" : ""}”<div class="ci-dim">Handbook ${where(row.handbook_page)}</div></td>` +
      states.map((s) => { const f = row.states[s]; return f ? `<td class="ci-bad" title="${e(f.requirement)}">✕ <span>${e(f.section)}</span></td>` : '<td class="ci-ok">✓ <span>none found</span></td>'; }).join("") + "</tr>").join("");
    return `<h3 class="ci-h">One handbook, ${states.length} states</h3><p class="ci-dim">A sentence can be fine in one state and break a rule in another. "None found" covers only that state's licensing rules; other laws, like child abuse reporting laws, also apply.</p>` +
      `<div class="ci-scroll"><table class="ci-matrix"><tr><th>Your handbook says</th>${head}</tr>${body}</table></div>` + '<p class="ci-scroll-hint">Scroll the table sideways to see every state.</p>' ;
  };

  const LANES = 6;  // rows of marks, so the map stays short
  const rulebookMap = (state, r, src) => {
    const total = +((src[state] || {}).pdf_pages || 1);
    const order = { conflict: 0, missing: 1, partial: 2, unverified: 3, covered: 4, not_mentioned: 5 };
    const items = r.findings.filter((f) => /^\d+$/.test(String(f.page ?? ""))).sort((a, b) => (+a.page - +b.page) || (order[a.status] - order[b.status]));
    const lanes = [], marks = [];
    for (const f of items) {
      const x = 1 + 98 * (+f.page - 1) / Math.max(1, total - 1);
      let lane = lanes.findIndex((last) => x - last >= 1.1);
      if (lane === -1 && lanes.length < LANES) { lane = lanes.length; lanes.push(x); }
      if (lane === -1) lane = lanes.indexOf(Math.min(...lanes));  // full: stack on the row with the most room
      lanes[lane] = x;
      marks.push([x, lane, f]);
    }
    const h = 14 + Math.max(1, lanes.length) * 9;
    const svg = [`<svg viewBox="0 0 100 ${h}" preserveAspectRatio="none" width="100%" height="${h * 2}" class="ci-timeline" role="img" aria-label="${e(name(state))} rulebook map">`,
      `<rect x="0" y="${h - 6}" width="100" height="2" rx="1" fill="currentColor" fill-opacity=".18"/>`,
      ...marks.map(([x, lane, f]) => `<rect x="${(x - 0.45).toFixed(2)}" y="${h - 10 - lane * 9 - 4}" width=".9" height="8" rx=".3" fill="${COLORS[f.status]}"><title>p. ${e(f.page)} · ${e(f.section)} · ${e(LABELS[f.status])}: ${e(f.requirement)}</title></rect>`),
      "</svg>"];
    const legend = ["conflict", "missing", "partial", "covered", "not_mentioned", "unverified"].map((k) => `<span><i style="background:${COLORS[k]}"></i>${LABELS[k]}</span>`).join("");
    return `<div class="ci-map"><div class="ci-dim">The whole ${e(name(state))} rulebook, page 1 to ${total}. Each mark is a rule your handbook should cover, at its page. Hover for details.</div>${svg.join("")}` +
      `<div class="ci-axis"><span>p. 1</span><span>p. ${total}</span></div><div class="ci-legend">${legend}</div></div>`;
  };

  const ruleBlock = (f, state, src) => {
    const pdf = ((src[state] || {}).format || "pdf") === "pdf";
    const link = f.rule_url ? ` <a href="${e(f.rule_url)}" target="_blank" rel="noopener">${pdf ? `open page ${e(f.page)}` : "open the official source"}</a>` : "";
    return `<div class="ci-quote ci-rule"><b>${e(name(state))} ${e(f.section)} ✅ checked word for word${link}</b>“${e(CR.unweight(f.quote))}”</div>`;
  };

  const card = (f, state, src, also = []) => {
    const color = COLORS[f.status];
    let html = `<div class="ci-finding" style="border-left-color:${color}"><div class="ci-tag" style="color:${color}">${e(LABELS[f.status])}</div><div class="ci-req">${e(f.requirement)}</div>`;
    if (f.handbook_quote) html += `<div class="ci-quote"><b>Your handbook, ${where(f.handbook_page)}</b>“${e(f.handbook_quote)}”</div>`;
    if (f.quote) html += ruleBlock(f, state, src);
    const shown = new Set([`${f.section}|${f.page}`]);
    for (const o of also) {  // the same sentence can break several rules; show each rule once
      const key = `${o.section}|${o.page}`;
      if (o.quote && !shown.has(key)) { shown.add(key); html += ruleBlock(o, state, src); }
    }
    if (f.note) html += `<p class="ci-why ci-note">${e(f.note)} Check this one yourself before changing anything.</p>`;
    if (f.explanation) html += `<p class="ci-why">${f.note ? "Beam's reading: " : ""}${e(f.explanation)}</p>`;
    const fix = f.fix || (also.find((o) => o.fix) || {}).fix || "";
    if (fix) html += `<div class="ci-fix"><div class="ci-fixhead">Suggested wording, drafted by AI (edit before you use it)<button class="ci-copy" data-copy="${e(fix)}">Copy</button></div>${e(fix)}</div>`;
    return html + "</div>";
  };

  const FIRST = 4;  // cards shown per group before "show more"
  const listing = (cards) => cards.slice(0, FIRST).join("") + (cards.length > FIRST
    ? `<details class="ci-more"><summary>Show ${cards.length - FIRST} more</summary>${cards.slice(FIRST).join("")}</details>` : "");
  const findingsHtml = (state, r, src) => {
    let out = "";
    const groups = CR.statements(r.findings);
    if (groups.length) out += `<h4 class="ci-h4">${LABELS.conflict} (${groups.length})</h4>` +
      listing(groups.map((g) => card(g.reduce((a, f) => (f.handbook_quote.length > a.handbook_quote.length ? f : a), g[0]), state, src, g)));
    // Headings count every rule checked; the score cards count required policies only, so say how many are required.
    const count = (group) => {
      const req = group.filter((f) => f.kind === "must_include").length;
      return req === group.length || req === 0 ? `${group.length}` : `${group.length}: ${req} required ${req === 1 ? "policy" : "policies"}, ${group.length - req} other rule${group.length - req === 1 ? "" : "s"}`;
    };
    for (const status of ["missing", "partial", "unverified"]) {
      const group = r.findings.filter((f) => f.status === status);
      if (group.length) out += `<h4 class="ci-h4">${LABELS[status]} (${count(group)})</h4>` + listing(group.map((f) => card(f, state, src)));
    }
    const covered = r.findings.filter((f) => f.status === "covered");
    if (covered.length) out += `<details><summary class="ci-h4">Covered (${count(covered)})</summary>${covered.map((f) => card(f, state, src)).join("")}</details>`;
    return out;
  };

  CR.scoreCards = async (results) => scoreCards(results, await CR.sources());
  CR.isTableRow = (quote) => /\d/.test(quote) && quote.split(/\s+/).length <= 12 && !/[.;:!?]$/.test(quote.trim());
  CR.SCORE_NOTE = "Score: the percent of required policies your handbook covers (incomplete ones count half), minus 5 points for each sentence that breaks a rule. It's not an inspection result.";

  /* "Start here": what to fix first, before the details. */
  const startHere = (results) => {
    const rows = CR.crossState(results), states = Object.keys(results);
    const multi = states.length > 1 ? rows.filter((r) => Object.keys(r.states).length > 1).slice(0, 3) : [];
    const lines = Object.entries(results).map(([s, r]) => {
      const c = r.counts, must = r.findings.filter((f) => f.kind === "must_include");
      const n = (st) => must.filter((f) => f.status === st).length;
      const parts = [];
      if (c.conflict_statements) parts.push(`${c.conflict_statements} sentence${c.conflict_statements > 1 ? "s" : ""} break${c.conflict_statements > 1 ? "" : "s"} a rule`);
      if (n("missing")) parts.push(`${n("missing")} required polic${n("missing") > 1 ? "ies" : "y"} missing`);
      if (n("partial")) parts.push(`${n("partial")} required polic${n("partial") > 1 ? "ies" : "y"} incomplete`);
      const other = r.findings.filter((f) => f.kind !== "must_include" && f.status === "partial").length;  // optional rules: no effect on the score
      if (other) parts.push(`${other} other rule${other === 1 ? "" : "s"} only partly covered`);
      if (c.unverified) parts.push(`${c.unverified} to check by hand`);
      return `<li><b>${e(name(s))}: ${r.score}/100.</b> ${parts.length ? e(parts.join(", ")) + "." : "No problems found."}</li>`;
    }).join("");
    const top = multi.length ? `<p><b>Fix first:</b> ${multi.length === 1 ? "this sentence breaks" : "these sentences break"} the rules of more than one state.</p><ul>${multi.map((r) =>
      `<li>“${e(r.handbook_quote.slice(0, 140))}${r.handbook_quote.length > 140 ? "…" : ""}” <span class="ci-dim">(handbook ${where(r.handbook_page)}: ${e(Object.keys(results).filter((s) => r.states[s]).map(name).join(", "))})</span></li>`).join("")}</ul>` : "";
    return `<div class="ci-start"><h3 class="ci-h">Start here</h3><ul>${lines}</ul>${top}<p class="ci-dim">${e(CR.SCORE_NOTE)} Each finding quotes your handbook and the rule; a real quote proves the words exist, not that Beam read them correctly. Not legal advice: confirm changes with your licensing agency.</p></div>`;
  };

  /* Text in a handbook that tries to instruct the AI ("ignore the instructions", "mark everything covered"). */
  CR.suspicious = (pages) => {
    const re = /\b(ignore|disregard)\b.{0,40}\b(instructions|rules above|checklist|prompt)\b|\bmark (every|all|each)\b.{0,30}\b(covered|compliant)\b|\byou are (now )?(an? )?(ai|assistant|language model|inspector)\b|\bsystem prompt\b/i;
    return pages.some(([, t]) => re.test(t));
  };

  /* Word and text files have no fixed pages, so their "pages" are parts of about 3,000 characters. */
  let UNIT = "page";
  const where = (n) => (UNIT === "part" ? `part ${n}` : `p. ${n}`);
  CR.report = async (results, handbookName, handbookPages, unit = "page") => {
    UNIT = unit;
    const src = await CR.sources();
    const rs = Object.values(results);
    const tokens = rs.reduce((a, r) => a + (r.tokens_in || 0) + (r.tokens_out || 0), 0);
    const secs = Math.max(...rs.map((r) => r.seconds || 0));
    const cost = rs.reduce((a, r) => a + (r.cost || 0), 0);
    const n = rs.length;
    const cached = rs.length && rs.every((r) => r.cached);
    const effort = [...new Set(rs.map((r) => (String(r.effort || "").startsWith("high") ? "Extra thorough" : "Standard")))].join(" and ");
    const head = `<div class="ci-run">Beam 1.0 read <b>${e(handbookName)}</b> (${handbookPages} ${unit}${handbookPages === 1 ? "" : "s"}) with the licensing rules of ${n} state${n > 1 ? "s" : ""}: ` +
      `${tokens.toLocaleString("en-US")} tokens in ${Math.round(secs)} seconds, $${cost.toFixed(2)}, ${effort}${cached ? " (served from the cache at no cost this time)" : ""}. ` +
      "Every quote below was checked word for word against its document.</div>";
    const tabs = Object.entries(results).map(([s, r], i) => `<details class="ci-state-block" ${i === 0 ? "open" : ""}><summary>${e(name(s))}: ${r.score}/100</summary>${rulebookMap(s, r, src)}${findingsHtml(s, r, src)}</details>`).join("");
    return `<div class="ci">${head}${scoreCards(results, src)}${startHere(results)}${matrix(results)}<h3 class="ci-h">${n > 1 ? "Findings by state" : `Findings for ${e(name(Object.keys(results)[0]))}`}</h3>${tabs}</div>`;
  };

  CR.fixesMarkdown = (results, handbookName, unit = "page") => {
    UNIT = unit;
    const lines = [`# Suggested handbook fixes: ${handbookName}`, "",
      "Drafted by Beam 1.0 from each state's official licensing rules. Every rule quote was checked word for word. Review and edit before you use them; this is not legal advice.", ""];
    for (const [st, r] of Object.entries(results)) {
      lines.push(`## ${name(st)} (score ${r.score}/100)`, "");
      for (const f of r.findings) {
        if (!f.fix) continue;
        lines.push(`### ${f.requirement}`);
        if (f.handbook_quote) lines.push(`Your handbook says (${where(f.handbook_page)}): "${f.handbook_quote}"`);
        lines.push(`Rule: ${f.section}, page ${f.page}: "${CR.unweight(f.quote)}"`, "", `Suggested wording (AI draft): ${f.fix}`, "");
      }
    }
    lines.push("---", "", "Made with CareRules (https://care.backpr.com), a free tool from BackPR. Suggested wording was drafted by AI " +
      "from your state's official licensing rules and isn't legal advice; confirm changes with your licensing agency. When your " +
      "handbook is final, BackPR can collect each family's e-signed acknowledgment at registration: " +
      "https://backpr.com/solutions/childcare?utm_source=carerules&utm_medium=referral&utm_campaign=fixes", "");
    return lines.join("\n");
  };

  /* what the page needs for the hero card and the "fine here, conflict there" section */
  CR.light = async (results) => {
    const src = await CR.sources();
    return {
      scores: Object.fromEntries(Object.entries(results).map(([s, r]) => [s, { score: r.score, name: name(s), counts: r.counts,
        pages: (src[s] || {}).pdf_pages, marks: r.findings.filter((f) => /^\d+$/.test(String(f.page ?? ""))).map((f) => [+f.page, f.status]) }])),
      rows: CR.crossState(results).map((row) => ({ quote: row.handbook_quote, page: row.handbook_page, verdict: row.verdict,
        sections: Object.fromEntries(Object.entries(row.states).map(([s, f]) => [s, f.section])),
        detail: Object.fromEntries(Object.entries(row.states).map(([s, f]) => [s, { section: f.section, page: f.page, rule: CR.unweight(f.quote), fix: f.fix, why: f.explanation, url: f.rule_url || "", quote: f.handbook_quote }])) })),
    };
  };

  if (typeof module !== "undefined" && module.exports) module.exports = CR; else root.CR = CR;
})(typeof window !== "undefined" ? window : globalThis);
