"""Step 1 of the Handbook Inspector: Beam reads a state's whole rulebook once and compiles what a licensed center's
written policies and parent handbook must cover, plus the core rules a handbook states and can get wrong. Every item
carries a quote that is checked word for word against the rulebook; items whose quote isn't found are dropped.

    python3 -I scripts/checklist.py TX [NC ...]   writes data/checklists/<STATE>.json"""
from __future__ import annotations

import json
import re

from . import beam
from .corpus import ROOT, find_quote, sources
from .grade import parse_json

OUT = ROOT / "data" / "checklists"
TOPICS = ("enrollment and admission", "fees and payment", "hours and closings", "arrival, release and authorized pickup",
          "late pickup and absences", "discipline and guidance (prohibited practices)", "staff-to-child ratios",
          "illness and exclusion", "medication", "immunizations and health records", "injuries and incidents",
          "emergencies and evacuation", "safe sleep and rest", "meals, food and allergies", "field trips and transport",
          "abuse and neglect reporting", "parent access and communication", "complaints and licensing contact",
          "confidentiality and records", "withdrawal and termination of care")


def prompt(state: str) -> str:
    title = sources().get(state, {}).get("title", state)
    return (
        f"You are building the checklist a licensing inspector would use to review the written policies and parent "
        f"handbook of a licensed child care center under the rulebook above ({title}).\n\n"
        "List every requirement in this rulebook that a center's written policies, operational policies or parent "
        "handbook must contain, or that must be given or explained to parents in writing. Then add the core rules that "
        "handbooks commonly state and can get wrong, even if the rulebook doesn't say they must be in the handbook "
        "(for example ratios by age, prohibited discipline, who may pick up a child, when a sick child must go home, "
        "medication permission). Cover these topics where the rulebook addresses them: " + "; ".join(TOPICS) + ".\n\n"
        "For each item give: id (short slug), topic (one of the topics above), kind (\"must_include\" if the rulebook "
        "requires it in written policies/handbook or in writing to parents, \"rule\" otherwise), requirement (one plain "
        "sentence a director understands: what the handbook must say or must not contradict), section (as printed), "
        "page (the [page N] marker), quote (copied exactly from the rulebook, 8 to 60 words, that proves the item). "
        "Only include items for centers (not family homes) unless the rule applies to both. Aim for 30 to 70 items; "
        "don't invent requirements. Reply with only a JSON array of the items."
    )


def _rows(rep: beam.Reply) -> list[dict]:
    got = parse_json(rep.content)
    return [r for r in got if isinstance(r, dict)] if isinstance(got, list) else []


def build(state: str, effort: str = "low") -> dict:
    """One pass to draft the checklist, then our checker verifies every quote; Beam gets one repair turn for the
    quotes that failed. The long rulebook is sent at most twice."""
    from .run import book  # local import: run.py builds the rulebook context

    msgs = [{"role": "user", "content": f"{book(state)}\n\n{prompt(state)}"}]
    first = beam.chat(msgs, effort=effort, max_tokens=24576)
    replies = [first]
    if first.finish == "length":  # a runaway reply (seen for OK and PA at temperature 0): retry once at Beam's default 0.7
        first = beam.chat(msgs, effort=effort, max_tokens=24576, temperature=0.7)
        replies.append(first)
    rows = _rows(first)
    failed = [r for r in rows if r.get("requirement") and not find_quote(state, str(r.get("quote", "")))]
    if failed:
        msgs += [{"role": "assistant", "content": first.content, "reasoning_content": first.reasoning},
                 {"role": "user", "content": "These quotes are not word for word in the rulebook. For each, copy the "
                  "exact text from the rulebook page (8 to 60 words) or drop the item if you can't. Reply with only a "
                  "JSON array of the corrected items, same fields.\n" + json.dumps(failed, ensure_ascii=False)}]
        fix = beam.chat(msgs, effort=effort, max_tokens=32768)
        replies.append(fix)
        fixed = {str(r.get("id")): r for r in _rows(fix)}
        rows = [fixed.get(str(r.get("id")), r) if r in failed else r for r in rows]
    items, dropped, seen = [], [], set()
    for r in rows:
        if not r.get("requirement"):
            continue
        page = find_quote(state, str(r.get("quote", "")))
        slug = re.sub(r"[^a-z0-9]+", "_", str(r.get("id") or r["requirement"]).lower()).strip("_")[:48] or "item"
        while slug in seen:
            slug += "_2"
        seen.add(slug)
        item = {"id": slug, "topic": r.get("topic", ""), "kind": r.get("kind", "rule"),
                "requirement": str(r["requirement"]).strip(), "section": str(r.get("section", "")).strip(),
                "page": page or r.get("page"), "quote": str(r.get("quote", "")).strip()}
        (items if page else dropped).append(item)
    items.sort(key=lambda x: (int(x["page"]) if str(x["page"]).isdigit() else 9999))
    out = {"state": state, "rulebook": sources().get(state, {}).get("title", ""), "items": items,
           "dropped_unverified": dropped, "turns": len(replies),
           "cost": round(sum(r.cost for r in replies), 4), "tokens_in": sum(r.tokens_in for r in replies),
           "tokens_out": sum(r.tokens_out for r in replies), "effort": effort, "model": beam.MODEL}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{state}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out
