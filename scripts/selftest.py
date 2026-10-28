"""Grade the answer key against itself: a perfect reply must count as right and verified for every item,
and an invented quote must never count. Run before spending anything on Beam."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from carerules.grade import grade  # noqa: E402
from carerules.items import all_items  # noqa: E402

items = all_items()
bad = 0
for it in items:
    perfect = {"answer": it["answer"], "quote": it.get("quote", "")}
    g = grade(it, perfect)
    if not (g["correct"] and g["verified"]):
        bad += 1
        print("PERFECT FAILS", it["id"], g["correct"], g["cited"], g["verified"], repr(it["answer"])[:80], it.get("accept"))
    if not it.get("trap"):
        fake = grade(it, {"answer": it["answer"], "quote": "The licensee shall comply with every rule in this chapter at all times."})
        if fake["verified"]:
            bad += 1
            print("FAKE QUOTE PASSES", it["id"])
kinds = {}
for it in items:
    k = "trap" if it.get("trap") else it["topic"] if it["topic"] == "inspection" else "lookup"
    kinds[k] = kinds.get(k, 0) + 1
print(f"{len(items)} items {kinds}; {bad} problems")
sys.exit(1 if bad else 0)
