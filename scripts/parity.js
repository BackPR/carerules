/* The browser engine (static/engine.js) must judge Beam's answers exactly like the Python package. Reads the cases
   written by scripts/parity.py, re-assembles each saved answer in JS and prints every difference. */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
const CR = require(path.join(ROOT, "static/engine.js"));
CR.data.loader = async (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const KEYS = ["id", "status", "handbook_quote", "handbook_page", "quote", "page", "section", "note"];
(async () => {
  const cases = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  let bad = 0;
  const crypto = require("crypto");
  for (const c of cases) {
    if (c.reader !== undefined) {  // the browser's text reader against Python's
      const same = JSON.stringify(CR.chunk(c.reader)) === JSON.stringify(c.expected_pages);
      bad += !same;
      console.log(`${c.name}: ${same ? "same" : "pages differ"}`);
      continue;
    }
    if (c.python_block !== undefined) {  // JS block = Python block, and its hash is the one the Worker accepts
      const p = await CR.prompt("TX", (await CR.checklist("TX")).slice(0, 60), [[1, "x"]]);
      const block = p.slice(p.lastIndexOf("\n\nYou are a careful licensing inspector.") + 2);
      const sha = crypto.createHash("sha256").update(block).digest("hex");
      const ok = block === c.python_block && c.worker.includes(`INSTRUCTIONS_SHA = "${sha}"`);
      bad += !ok;
      console.log(`instructions: ${ok ? "same, and the Worker accepts them" : "DIFFER (update INSTRUCTIONS_SHA in worker/src/index.ts to " + sha + ")"}`);
      continue;
    }
    if (c.expect_error !== undefined) {  // unreadable answers must fail in both engines
      let fails = false;
      try { await CR.assemble(c.state, c.pages, c.raw, { finish: "stop" }); } catch (e) { fails = true; }
      bad += fails !== c.expect_error;
      console.log(`${c.name}: ${fails === c.expect_error ? "same" : `JS ${fails ? "fails" : "accepts"}, Python ${c.expect_error ? "fails" : "accepts"}`}`);
      continue;
    }
    const js = await CR.assemble(c.state, c.pages, c.raw, { finish: "stop" });
    const py = c.expected;
    const diffs = [];
    if (js.score !== py.score) diffs.push(`score ${js.score} vs ${py.score}`);
    if (js.findings.length !== py.findings.length) diffs.push(`findings ${js.findings.length} vs ${py.findings.length}`);
    js.findings.forEach((f, i) => {
      const g = py.findings[i] || {};
      for (const k of KEYS) if (String(f[k] ?? "") !== String(g[k] ?? "")) diffs.push(`${f.id}.${k}: ${JSON.stringify(f[k])} vs ${JSON.stringify(g[k])}`);
    });
    bad += diffs.length > 0;
    console.log(`${c.name}: ${diffs.length ? diffs.length + " differences" : "same"}`);
    diffs.slice(0, 5).forEach((d) => console.log("   ", d.slice(0, 300)));
  }
  console.log(bad ? `${bad} of ${cases.length} differ` : `all ${cases.length} identical`);
  process.exit(bad ? 1 : 0);
})();
