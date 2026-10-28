"""Check that the browser engine (static/engine.js) and the Python package judge Beam's saved answers the same way:
every finding's status, quotes, pages and section, and every score; that unreadable answers fail in both; that both
read text handbooks into the same pages; and that the Worker accepts the instructions both send. Needs Node.
Usage: python3 -I scripts/parity.py"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from carerules import audit  # noqa: E402
from carerules.document import read  # noqa: E402

cases = []
for path in sorted((ROOT / "results/inspector").glob("[A-Z][A-Z]-*.json")):
    state, version = path.stem.split("-")[:2]
    res = json.loads(path.read_text())
    cases.append({"name": path.stem, "state": state, "raw": res["raw"], "expected": res,
                  "pages": read(ROOT / f"samples/eval/{state}/{version}.md")})
sample = json.loads((ROOT / "samples/little-acorns.audit-high.json").read_text())
pages = json.loads((ROOT / "samples/little-acorns-pages.json").read_text())
for state, res in sample["results"].items():
    cases.append({"name": f"sample-{state}", "state": state, "raw": res["raw"], "expected": res, "pages": pages})
# Answers that can't be read must fail in both engines (never a zero score).
for i, odd in enumerate(['{"items": {}}', '{"items": "x"}', '{"items": []}', '[1, 2]', 'not json', '{"items": [{"id": "x"}], "extra_conflicts": {}}']):
    try:
        audit.assemble("TX", pages, odd, {"finish": "stop"})
        fails = False
    except RuntimeError:
        fails = True
    cases.append({"name": f"odd-answer-{i}", "state": "TX", "raw": odd, "pages": pages, "expect_error": fails})
# The browser reads text files into pages exactly like the Python reader.
for md in sorted((ROOT / "samples/eval").glob("*/clean.md")):
    cases.append({"name": f"reader-{md.parent.name}", "reader": md.read_text(), "expected_pages": read(md)})
# The fixed instructions both engines send, which the Worker accepts by hash.
items = audit.checklist("TX")
prompt = audit._prompt("TX", items[:60], pages)
cases.append({"name": "instructions", "python_block": prompt[prompt.rindex("\n\nYou are a careful licensing inspector.") + 2:],
              "worker": (ROOT / "worker/src/index.ts").read_text()})
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
    json.dump(cases, f)
sys.exit(subprocess.run(["node", str(ROOT / "scripts/parity.js"), f.name]).returncode)
