"""Entry point: python3 -I scripts/run.py <mode> --effort low|high [...] (see carerules/run.py)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("CARERULES_BUDGET", "13")  # hard cap in USD across all benchmark runs; override to change
from carerules.run import main  # noqa: E402

# results/HOLD lists setups not to run yet, one "mode effort" per line (e.g. "stack low"); the run skips them.
hold = Path(__file__).resolve().parent.parent / "results" / "HOLD"
args = [a for a in sys.argv[1:] if not a.startswith("-")]
effort = sys.argv[sys.argv.index("--effort") + 1] if "--effort" in sys.argv else "low"
if args and hold.exists() and f"{args[0]} {effort}" in hold.read_text().split("\n"):
    print(f"held: {args[0]} {effort}", file=sys.stderr)
    sys.exit(0)
main()
