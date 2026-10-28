"""Entry point: python3 -I scripts/report.py writes results/summary.json and results/summary.md."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from carerules.report import RESULTS, build  # noqa: E402

s = build()
(RESULTS / "summary.json").write_text(json.dumps(s, indent=1))
(RESULTS / "summary.md").write_text(s["markdown"] + "\n")
print(s["markdown"])
