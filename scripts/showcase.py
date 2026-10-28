"""Record agent runs for the Space's "Showcase runs" tab (viewable with no sign-in and no cost).
Usage: python3 -I scripts/showcase.py [--effort low]"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from carerules import agent  # noqa: E402
from carerules.corpus import ROOT  # noqa: E402

CASES = [
    ("Ratio at the limit (Texas)", "TX", "One classroom has 2 caregivers and 36 four-year-olds. Is that allowed?"),
    ("Hot water at children's sinks (North Dakota)", "ND", "How hot can the water be at faucets children use?"),
    ("Can a 16-year-old count in ratio? (North Carolina)", "NC", "Can a 16-year-old teacher's aide count toward the staff-to-child ratio?"),
    ("Medication (Alabama)", "AL", "What do we need before giving a child medicine, and how long is it good for?"),
    ("Nap-time ratio (Mississippi)", "MS", "During rest time, how many staff have to stay in the room?"),
    ("Outdoor space (Colorado)", "CO", "How much outdoor play space do we need per child?"),
    ("Fire drills (New Jersey)", "NJ", "How often do we have to hold fire drills?"),
    ("A rule that doesn't exist (Texas)", "TX", "What does section 746.9137 say about swimming ratios?"),
]

ap = argparse.ArgumentParser()
ap.add_argument("--effort", default="low")
a = ap.parse_args()
out, total = [], 0.0
for label, state, question in CASES:
    steps, final = [], None
    for step in agent.inspect(state, question, effort=a.effort):
        if step["type"] == "tool":
            steps.append({k: step[k] for k in ("name", "args", "result")})
        else:
            final = {k: v for k, v in step.items() if k != "type"}
    total += final.get("cost", 0)
    out.append({"label": label, "state": state, "question": question, "effort": a.effort, "steps": steps, "final": final})
    print(label, final.get("answer", {}).get("answer", "")[:80], f"${final.get('cost', 0):.4f}", file=sys.stderr)
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results" / "showcase.json").write_text(json.dumps(out, indent=1))
print(f"saved {len(out)} runs, ${total:.3f}", file=sys.stderr)
