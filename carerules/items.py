"""Benchmark items: the answer key (data/gold), inspection scenarios built from it, and trap questions."""
from __future__ import annotations

import json
import random
import re

from .corpus import ROOT, norm, pages

GOLD = ROOT / "data" / "gold"


def states() -> list[str]:
    """The benchmark covers the states that have an answer key (the Inspector covers more)."""
    return sorted(p.stem for p in GOLD.glob("*.jsonl"))


def gold() -> list[dict]:
    out = []
    for path in sorted(GOLD.glob("*.jsonl")):
        out += [j for j in map(json.loads, filter(str.strip, path.read_text().splitlines())) if j.get("status") != "not_found"]
    return out


def scenarios(items: list[dict], seed: int = 7) -> list[dict]:
    """Yes/no inspection questions: one classroom of 4-year-olds, K caregivers, N children, right at the limit."""
    rng = random.Random(seed)
    by = {(i["state"], i["topic"]): i for i in items}
    out = []
    for st in states():
        r, g = by.get((st, "ratio_4yo")), by.get((st, "group_4yo"))
        if not r or r["answer_type"] != "number":
            continue
        ratio = int(float(r["answer"]))
        cap = int(float(g["answer"])) if g and g["answer_type"] == "number" else None
        for k, over in ((2, False), (2, True), (3, rng.choice([False, True]))):
            n = k * ratio + (1 if over else 0)
            if cap and n > cap and not over:
                n = cap  # stay inside the group cap so "yes" is really yes
            ok = n <= k * ratio and (cap is None or n <= cap)
            facility = re.sub(r"^.*?\b(in|at) (a|an) ", "", r["question"]).split(",")[0].split("?")[0][:120]
            out.append({
                "id": f"{st}-inspect_{k}_{n}", "state": st, "topic": "inspection", "answer_type": "yes_no",
                "answer": "yes" if ok else "no",
                "question": (f"Inspection check, {facility}: one classroom has {n} four-year-old children and {k} "
                             f"qualified caregivers, all present, during regular daytime activities (not nap, not a "
                             f"field trip). Does this classroom meet the rulebook's staff-to-child ratio"
                             f"{' and maximum group size' if cap else ''}? Answer yes or no first."),
                "quote": r["quote"], "page": r["page"], "section": r["section"],
                "notes": f"Built from {r['id']}{' and ' + g['id'] if g else ''}: 1:{ratio}" + (f", group {cap}" if cap else ""),
            })
    return out


def traps(seed: int = 11) -> list[dict]:
    """Questions about rule numbers that don't exist in the rulebook. The right answer is to say so."""
    rng = random.Random(seed)
    out = []
    for st in states():
        text = " ".join(norm(p.text) for p in pages(st))
        made = 0
        for _ in range(200):
            n = f"{rng.randint(10, 99)}.{rng.randint(100, 999)}"
            if n.replace(".", "") not in text.replace(" ", "") and norm(n) not in text:
                out.append({"id": f"{st}-trap_{n}", "state": st, "topic": "trap", "trap": True, "answer_type": "short_text",
                            "answer": "Not in this rulebook",
                            "question": f"What does section {n} of {st}'s childcare licensing rulebook require about staff-to-child ratios during swimming?",
                            "quote": "", "page": 0, "section": n})
                made += 1
                if made == 2:
                    break
    return out


def all_items() -> list[dict]:
    g = gold()
    return g + scenarios(g) + traps()
