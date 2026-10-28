"""Entry point: python3 -I scripts/checklist.py TX [NC ...] [--effort low]  (see carerules/checklist.py)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("CARERULES_BUDGET", "13")
from carerules.checklist import build  # noqa: E402

effort = sys.argv[sys.argv.index("--effort") + 1] if "--effort" in sys.argv else "low"
for st in [a for a in sys.argv[1:] if a.isupper() and len(a) == 2]:
    out = build(st, effort)
    print(f"{st}: {len(out['items'])} items verified, {len(out['dropped_unverified'])} dropped, "
          f"{out['turns']} turns, ${out['cost']:.3f}", file=sys.stderr)
