"""Rebuild every saved inspection from Beam's stored answer with the current checker (no Beam call, no cost):
the planted-defect runs in results/inspector, the example reports in samples/eval-results, and the sample report.
Run it after any change to quote checking or scoring, then scripts/eval_inspector.py to refresh the summaries.
Usage: python3 -I scripts/reassemble.py"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from carerules import audit  # noqa: E402
from carerules.document import read  # noqa: E402

META = ("cost", "tokens_in", "tokens_out", "finish", "seconds", "effort", "calls", "cached", "wall_seconds")


def rebuild(res: dict, pages: list) -> dict:
    meta = {k: res[k] for k in META if k in res}
    meta["finish"] = "stop"  # only answers that were read in full were saved
    out = audit.assemble(res["state"], pages, res["raw"], meta)
    out.update({k: res[k] for k in ("wall_seconds", "effort") if k in res})
    return out


for path in sorted((ROOT / "results/inspector").glob("[A-Z][A-Z]-*.json")):
    state, version = path.stem.split("-")[:2]
    res = json.loads(path.read_text())
    path.write_text(json.dumps(rebuild(res, read(ROOT / f"samples/eval/{state}/{version}.md")), indent=1))
    print("rebuilt", path.name)

for path in sorted((ROOT / "samples/eval-results").glob("[A-Z][A-Z].json")):  # the example reports: defective handbooks
    shutil.copy(ROOT / f"results/inspector/{path.stem}-defective-low-focused.json", path)
    print("copied", path.name)

sample_path = ROOT / "samples/little-acorns.audit-high.json"
sample = json.loads(sample_path.read_text())
pages = [tuple(p) for p in json.loads((ROOT / "samples/little-acorns-pages.json").read_text())]
sample["results"] = {s: rebuild(r, pages) for s, r in sample["results"].items()}
sample_path.write_text(json.dumps(sample, indent=1))
print("rebuilt the sample:", {s: r["score"] for s, r in sample["results"].items()})
