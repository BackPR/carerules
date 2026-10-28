"""Measure the Handbook Inspector on fictional handbooks with known, planted defects.

For each samples/eval/<STATE>/ with clean.md (a compliant handbook) and defects.json (5 sentences swapped for
versions that break a rule, 3 required policies deleted), build defective.md, audit both versions, and score:
  - planted conflicts flagged: a conflict finding whose handbook quote overlaps the planted sentence
  - deleted policies caught: that checklist item marked missing (or partial)
  - false alarms: conflicts claimed in the clean handbook, and conflicts in the defective one away from any plant
Usage: python3 -I scripts/eval_inspector.py [--effort low] [STATES...]"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CARERULES_BUDGET", "13")
from carerules import audit  # noqa: E402
from carerules.corpus import build_index, match  # noqa: E402
from carerules.document import read  # noqa: E402

EVAL, OUT = ROOT / "samples" / "eval", ROOT / "results" / "inspector"


def overlaps(a, b) -> bool:
    return bool(a and b) and a[0] < b[1] and b[0] < a[1]


def run(state: str, effort: str) -> dict:
    d = EVAL / state
    clean = (d / "clean.md").read_text()
    defects = json.loads((d / "defects.json").read_text())
    bad = clean
    for c in defects["conflicts"]:
        assert bad.count(c["original"]) == 1, (state, c["original"][:50])
        bad = bad.replace(c["original"], c["planted"])
    for r in defects["removals"]:
        assert bad.count(r["text"]) == 1, (state, r["text"][:50])
        bad = bad.replace(r["text"], "")
    (d / "defective.md").write_text(bad)
    OUT.mkdir(parents=True, exist_ok=True)
    out = {"state": state, "effort": effort}
    for name in ("clean", "defective"):
        path = OUT / f"{state}-{name}-{effort}-{audit.CONTEXT}.json"
        if path.exists():
            out[name] = json.loads(path.read_text())
            continue
        pages = read(d / f"{name}.md")
        t0 = time.time()
        res = audit.audit_with_fallback(state, pages, effort, None)
        res["wall_seconds"] = round(time.time() - t0, 1)
        path.write_text(json.dumps(res, indent=1))
        out[name] = res
    pages = read(d / "defective.md")
    index = build_index(pages)
    spans = [(c, match(index, c["planted"])) for c in defects["conflicts"]]
    found = out["defective"]["findings"]
    conflicts = [f for f in found if f["status"] == "conflict" and f.get("span")]
    caught, on_item = [], []
    for c, m in spans:
        span = [m[1], m[2]] if m else None
        hits = [f for f in conflicts if overlaps(f["span"], span)]
        caught.append(bool(hits))
        on_item.append(any(f["id"] == c["item_id"] for f in hits))
    by_id = {f["id"]: f for f in found}
    removed = [by_id.get(r["item_id"], {}).get("status") for r in defects["removals"]]
    planted_spans = [[m[1], m[2]] for _, m in spans if m]
    stray = audit.statements([f for f in conflicts if not any(overlaps(f["span"], s) for s in planted_spans)])
    clean_conflicts = audit.statements(out["clean"]["findings"])
    return {
        "state": state, "effort": effort,
        "planted": len(spans), "planted_flagged": sum(caught), "planted_on_right_item": sum(on_item),
        "removed": len(removed), "removed_missing": sum(s == "missing" for s in removed),
        "removed_missing_or_partial": sum(s in ("missing", "partial") for s in removed),
        "clean_false_conflicts": len(clean_conflicts), "defective_other_conflicts": len(stray),
        "clean_score": out["clean"]["score"], "defective_score": out["defective"]["score"],
        "cost": round(out["clean"]["cost"] + out["defective"]["cost"], 4),
        "seconds": [out["clean"].get("wall_seconds"), out["defective"].get("wall_seconds")],
        "missed": [c["planted"] for (c, _), ok in zip(spans, caught) if not ok],
        "clean_conflict_quotes": [g[0]["handbook_quote"][:160] for g in clean_conflicts],
        "other_conflict_quotes": [g[0]["handbook_quote"][:160] for g in stray],
    }


if __name__ == "__main__":
    effort = sys.argv[sys.argv.index("--effort") + 1] if "--effort" in sys.argv else "low"
    states = [a for a in sys.argv[1:] if a.isupper() and len(a) == 2] or sorted(
        p.name for p in EVAL.iterdir() if (p / "defects.json").exists())
    rows = []
    for st in states:
        try:
            rows.append(run(st, effort))
            r = rows[-1]
            print(f"{st}: planted {r['planted_flagged']}/{r['planted']} (right item {r['planted_on_right_item']}), "
                  f"removed {r['removed_missing']}/{r['removed']} missing ({r['removed_missing_or_partial']} incl. partial), "
                  f"clean false conflicts {r['clean_false_conflicts']}, scores {r['clean_score']}->{r['defective_score']}, ${r['cost']}",
                  file=sys.stderr)
        except Exception as err:
            print(f"{st}: ERROR {err}", file=sys.stderr)
    prev = OUT / f"summary-{effort}-{audit.CONTEXT}.json"
    keep = {r["state"]: r for r in (json.loads(prev.read_text()) if prev.exists() else [])}
    keep.update({r["state"]: r for r in rows})
    prev.write_text(json.dumps(list(keep.values()), indent=1))
    tot = list(keep.values())
    if tot:
        p, pf = sum(r["planted"] for r in tot), sum(r["planted_flagged"] for r in tot)
        m, mm = sum(r["removed"] for r in tot), sum(r["removed_missing_or_partial"] for r in tot)
        print(f"ALL {len(tot)} states: planted conflicts flagged {pf}/{p}, deleted policies caught {mm}/{m}, "
              f"clean-handbook false conflicts {sum(r['clean_false_conflicts'] for r in tot)} "
              f"({sum(r['clean_false_conflicts'] for r in tot) / len(tot):.1f} per handbook), cost ${sum(r['cost'] for r in tot):.2f}",
              file=sys.stderr)
