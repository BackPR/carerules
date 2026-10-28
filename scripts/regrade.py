"""Re-grade every stored result with the current checker (after a checker fix, so all runs use the same rules)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from carerules.grade import grade  # noqa: E402
from carerules.items import all_items  # noqa: E402

items = {i["id"]: i for i in all_items()}
for path in sorted((Path(__file__).resolve().parent.parent / "results").glob("*-*.jsonl")):
    if path.name == "spend.jsonl":
        continue
    rows, changed = [], 0
    for line in path.read_text().splitlines():
        r = json.loads(line)
        g = grade(items[r["id"]], {"answer": r["answer"], "quote": r["quote"]})
        changed += any(r[k] != g[k] for k in ("correct", "cited", "verified"))
        r.update({k: g[k] for k in ("correct", "cited", "quote_page", "verified")})
        rows.append(r)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"{path.name}: {len(rows)} rows, {changed} changed")
