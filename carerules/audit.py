"""Step 2 of the Handbook Inspector: audit a center's handbook against a state's rules.

Beam reads the state's whole rulebook, the state checklist (from checklist.py) and the handbook in one context, and
returns a status for every checklist item plus any other conflict it finds. Then every quote is checked here, word
for word: handbook quotes against the handbook, rule quotes against the rulebook. A finding whose quote isn't found
is never shown as fact: it becomes "check manually", and an unproven conflict is dropped."""
from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from . import beam
from .corpus import GUIDANCE_NAME, ROOT, Index, build_index, find_row, find_rule, match, norm, page_url, pages, sources
from .grade import parse_json

CHECKLISTS = ROOT / "data" / "checklists"
STATUSES = ("covered", "partial", "missing", "conflict", "not_mentioned")
CONFLICT_PENALTY = 5
_NOT_THERE = "but the words it quoted don't appear in your handbook exactly as written (it may have joined two lines, such as two rows of a table)."
HANDBOOK_NOTE = {"conflict": f"Beam flagged this as a conflict, {_NOT_THERE}", "partial": f"Beam flagged this as incomplete, {_NOT_THERE}",
                 "covered": f"Beam marked this as covered, {_NOT_THERE}"}


def checklist(state: str) -> list[dict]:
    path = CHECKLISTS / f"{state}.json"
    return json.loads(path.read_text())["items"] if path.exists() else []


def available_states() -> list[str]:
    return sorted(p.stem for p in CHECKLISTS.glob("*.json"))


CONTEXT = os.environ.get("CARERULES_CONTEXT", "focused")  # "focused" (default; 2.4x cheaper on the planted-defect test) or "full"
MAX_CONTEXT_CHARS = 140_000  # about 35k tokens of rulebook pages in focused mode
_INDEX: dict[str, Index] = {}


def focused_pages(state: str, items: list[dict], handbook: list[tuple[int, str]]) -> list[int]:
    """The rulebook pages worth sending: every page a checklist item cites (and the next one, where rules run on),
    then the pages that best match each part of the handbook (BM25), until the size cap."""
    by_number = {p.number: p for p in pages(state)}
    chosen: list[int] = []
    for it in items:
        if str(it.get("page", "")).isdigit():
            for n in (int(it["page"]), int(it["page"]) + 1):
                if n in by_number and n not in chosen:
                    chosen.append(n)
    index = _INDEX.setdefault(state, Index([state]))
    for _, text in handbook:
        for chunk in (text[i:i + 1500] for i in range(0, len(text), 1500)):
            for _, p in index.search(chunk, k=2):
                if p.number not in chosen:
                    chosen.append(p.number)
    out, size = [], 0
    for n in chosen:  # checklist pages first, then retrieved pages, until the cap
        size += len(by_number[n].text)
        if size > MAX_CONTEXT_CHARS:
            break
        out.append(n)
    return sorted(out)


def rulebook_context(state: str, items: list[dict], handbook: list[tuple[int, str]]) -> str:
    from .run import book  # run.py builds the full rulebook context

    if CONTEXT == "full":
        return book(state)
    src = sources().get(state, {})
    keep = set(focused_pages(state, items, handbook))
    body = "\n".join(f"[{state} page {p.number}]\n{p.text.strip()}" for p in pages(state) if p.number in keep)
    return (f"=== RULEBOOK {state}: {src.get('title', state)} — the {len(keep)} pages relevant to this handbook, out of "
            f"{src.get('pdf_pages', '?')} (page numbers are the official document's) ===\n{body}")


def _prompt(state: str, items: list[dict], handbook: list[tuple[int, str]]) -> str:
    name = sources().get(state, {}).get("title", state)
    listing = "\n".join(f"- {i['id']} [{i['kind']}] {i['requirement']} ({i['section']}, page {i['page']}): \"{i['quote']}\""
                        for i in items)
    doc = "\n".join(f"[Handbook page {n}]\n{t.strip()}" for n, t in handbook)
    return (
        f"{rulebook_context(state, items, handbook)}\n\n=== CHECKLIST for {name} ===\n{listing}\n\n=== THE CENTER'S HANDBOOK ===\n{doc}\n\n"
        "You are a careful licensing inspector. Audit the handbook against the checklist and the rulebook above.\n"
        "For EVERY checklist item, give a status:\n"
        "- covered: the handbook clearly addresses it and agrees with the rule\n"
        "- partial: it addresses it but leaves out something the rule requires\n"
        "- conflict: the handbook says something the rule forbids or contradicts (for example a number the rule "
        "doesn't allow, or permission the rule requires in writing given verbally)\n"
        "Call something a conflict only if the exact rule words you give as rule_quote show it, and write the "
        "explanation from those words alone: if a rule allows several ways (for example in writing, electronically, "
        "or by phone for one dose), say which condition the handbook misses, never that an allowed way is forbidden.\n"
        "Apply only rules for the kind of program the handbook describes. Rules that apply only to special programs "
        "(for example a state-funded pre-K program, get-well or sick care, night care, or family child care homes) "
        "don't apply unless the handbook says the center runs one; a room merely named \"Pre-K\" isn't one.\n"
        "- missing: a [must_include] item the handbook doesn't address at all\n"
        "- not_mentioned: a [rule] item the handbook doesn't mention (that's allowed)\n"
        "Then look for any OTHER statement in the handbook that contradicts the rulebook.\n\n"
        "Quotes must be copied exactly (8 to 60 words): handbook_quote from the handbook, rule_quote from the "
        "rulebook. For missing and partial items and every conflict, write a fix: a paragraph the center can paste into "
        "its handbook, in plain, warm language, that meets the rule without adding requirements the rule doesn't "
        "have. Use [brackets] for details only the center knows (times, names, phone numbers).\n\n"
        "Keep it short: for covered items give only id, status and handbook_quote; for not_mentioned items only id "
        "and status. Explanations and fixes are only for partial, missing and conflict items.\n\n"
        'Reply with only a JSON object: {"items": [{"id", "status", "handbook_quote", "handbook_page", '
        '"rule_quote" (for a conflict: the exact rulebook words the handbook breaks, such as the table row with the '
        'number; else empty), "rule_section" (the section that rule_quote comes from, as printed), '
        '"explanation" (one plain sentence), "fix"}], "extra_conflicts": [{"title", "handbook_quote", '
        '"handbook_page", "rule_quote", "section", "page", "explanation", "fix"}], "summary" (two sentences)}.'
    )


CHUNK = 60  # checklist items per Beam call; long checklists (California has 182) are split so answers fit


def audit_state(state: str, handbook: list[tuple[int, str]], effort: str = "low", api_key: str | None = None) -> dict:
    items = checklist(state)
    if not items:
        raise ValueError(f"No checklist for {state} yet.")
    chunks = [items[i:i + CHUNK] for i in range(0, len(items), CHUNK)]
    budget = 24576 if effort == "low" else 49152  # higher effort reasons longer before it answers (same caps as the Worker)

    def ask(part: list[dict], first: bool) -> beam.Reply:
        prompt = _prompt(state, part, handbook)
        if not first:  # other conflicts are looked for once, in the first part
            prompt += "\nFor this part, leave extra_conflicts empty."
        return beam.chat([{"role": "user", "content": prompt}], effort=effort, max_tokens=budget, api_key=api_key)

    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        replies = list(pool.map(lambda ip: ask(ip[1], ip[0] == 0), enumerate(chunks)))
    merged, finish = {"items": [], "extra_conflicts": [], "summary": ""}, "stop"
    for rep in replies:
        got = parse_json(rep.content)
        if rep.finish == "length" or not isinstance(got, dict) or not isinstance(got.get("items"), list) or not got["items"]:
            finish = "length"
            continue
        merged["items"] += got["items"]
        if isinstance(got.get("extra_conflicts"), list):
            merged["extra_conflicts"] += got["extra_conflicts"]
        merged["summary"] = merged["summary"] or str(got.get("summary") or "")
    meta = {"cost": round(sum(r.cost for r in replies), 4), "tokens_in": sum(r.tokens_in for r in replies),
            "tokens_out": sum(r.tokens_out for r in replies), "finish": finish,
            "seconds": max(r.seconds for r in replies), "effort": effort, "calls": len(replies)}
    return assemble(state, handbook, json.dumps(merged), meta)


def section_label(state: str, label: str, page: int) -> str:
    """Show a section number only if it really appears on the quote's page (or the page before); labels come from the
    model and aren't otherwise checked."""
    label = re.sub(r",?\s*\(?page\s*\d+\)?\s*$", "", str(label or ""), flags=re.I).strip()
    core = max(re.findall(r"\d[\d.\-]*\d", label), key=len, default="")
    near = " " + " ".join(norm(p.text) for p in pages(state) if p.number in (page, page - 1)).replace("§", " ") + " "
    if label and core and f" {norm(core)} " in near:  # whole numbers only: 746.201 must not match 746.1201
        return label
    return f"rule on page {page}"


def assemble(state: str, handbook: list[tuple[int, str]], content: str, meta: dict) -> dict:
    """Check every quote in Beam's reply and build the findings and score (no Beam call: reusable on saved replies)."""
    items = checklist(state)
    got = parse_json(content)
    if meta.get("finish") == "length" or not isinstance(got, dict) or not isinstance(got.get("items"), list) or not got["items"]:
        # A cut-off or unreadable reply must never be shown as a (zero) score.
        raise RuntimeError(f"Beam's answer for {state} was cut off or couldn't be read. Please try again.")
    hb = build_index(handbook)
    answers = {str(a.get("id")): a for a in got["items"] if isinstance(a, dict)}
    findings = []
    for it in items:
        a = answers.get(it["id"], {})
        status = a.get("status") if a.get("status") in STATUSES else ("missing" if it["kind"] == "must_include" else "not_mentioned")
        if status == "not_mentioned" and it["kind"] == "must_include":  # that status is only for optional rules
            status = "missing"
        hq = str(a.get("handbook_quote") or "").strip()
        m = match(hb, hq) if hq else None
        hpage, span = (m[0], [m[1], m[2]]) if m else (None, None)
        note = ""
        if status in ("covered", "partial", "conflict") and not hpage:
            # Beam pointed at the handbook but the words aren't there: never shown as fact
            note = HANDBOOK_NOTE[status] if hq else "Beam didn't quote your handbook for this."
            status = "unverified"
        rq = str(a.get("rule_quote") or "").strip()
        if status == "conflict":
            rule = find_rule(state, rq) if rq else None
            row = None if rule or not rq or not str(it["page"]).isdigit() else find_row(state, rq, int(it["page"]))
            if row:  # a table row, proven on the page of the checklist's own (verified) rule: show both
                rule = (row[0], f"{it['quote']} … {row[1]}", row[2])
            if not rule:  # a conflict has to name rule words that are really there
                status, note = "unverified", "Beam flagged this as a conflict, but the rule words it gave don't match the official text."
            elif rule[2]:
                status, note = "unverified", (f"Beam flagged this as a conflict, but the words it quoted are from "
                                              f"{GUIDANCE_NAME[state]}, which is guidance, not a rule.")
            elif row:
                it = {**it, "quote": rule[1], "page": rule[0]}
            else:  # the exact clause broken, proven word for word, replaces the checklist's general quote
                it = {**it, "quote": rule[1], "page": rule[0], "section": section_label(state, a.get("rule_section"), rule[0])}
        findings.append({**it, "status": status, "handbook_quote": hq if hpage else "", "handbook_page": hpage, "span": span,
                         "explanation": str(a.get("explanation") or "").strip(), "note": note,
                         "fix": str(a.get("fix") or "").strip() if status in ("missing", "partial", "conflict") else "",
                         "rule_url": page_url(state, it["page"]) if str(it["page"]).isdigit() else ""})
    extras = []
    for x in got["extra_conflicts"] if isinstance(got.get("extra_conflicts"), list) else []:
        if not isinstance(x, dict):
            continue
        m = match(hb, str(x.get("handbook_quote") or ""))
        rule = find_rule(state, str(x.get("rule_quote") or ""))
        if m and rule and not rule[2]:
            rpage = rule[0]  # an extra conflict needs both quotes proven, from a rule (not guidance), or it isn't shown
            extras.append({"id": "extra_" + str(len(extras) + 1), "topic": "other", "kind": "rule", "status": "conflict",
                           "requirement": str(x.get("title") or "Conflict with the rulebook"),
                           "section": section_label(state, x.get("section"), rpage), "page": rpage, "quote": rule[1],
                           "handbook_quote": str(x["handbook_quote"]).strip(), "handbook_page": m[0], "span": [m[1], m[2]],
                           "explanation": str(x.get("explanation") or "").strip(), "note": "", "fix": str(x.get("fix") or "").strip(),
                           "rule_url": page_url(state, rpage)})
    findings += extras
    return {"state": state, "rulebook": sources().get(state, {}).get("title", ""), "findings": findings,
            "summary": str(got.get("summary") or "").strip(), **score(findings), **meta, "raw": content}


ROW = 80  # normalized characters: quotes this short are table rows; adjacent rows of one table are one passage


def statements(findings: list[dict]) -> list[list[dict]]:
    """Group conflicting findings by the handbook passage they quote, so a sentence that breaks two rules (or two
    rows of one table) counts once. Quotes are one passage if they overlap, or if both are short table rows that
    sit next to each other."""
    hits = sorted((f for f in findings if f["status"] == "conflict" and f.get("span")), key=lambda f: f["span"][0])
    groups: list[list[dict]] = []
    for f in hits:
        if groups:
            end = max(g["span"][1] for g in groups[-1])
            last = groups[-1][-1]
            short = f["span"][1] - f["span"][0] <= ROW and last["span"][1] - last["span"][0] <= ROW
            if f["span"][0] < end or (short and f["span"][0] - end <= ROW):
                groups[-1].append(f)
                continue
        groups.append([f])
    return groups


def score(findings: list[dict]) -> dict:
    """Coverage of the required policies (covered 1, partial 0.5), minus 5 points per handbook statement that
    conflicts with the rules (a statement that breaks several rules counts once)."""
    must = [f for f in findings if f["kind"] == "must_include"]
    credit = sum(1 if f["status"] == "covered" else 0.5 if f["status"] == "partial" else 0 for f in must)
    passages = len(statements(findings))
    base = 100 * credit / len(must) if must else 100
    counts = {s: sum(f["status"] == s for f in findings) for s in (*STATUSES, "unverified")}
    counts["conflict_statements"] = passages
    return {"score": max(0, round(base - CONFLICT_PENALTY * passages)), "coverage": round(base),
            "required": len(must), "counts": counts}


def cross_state(results: dict) -> list[dict]:
    """Rows for the "one handbook, every state" view: each handbook passage that conflicts with at least one state's
    rules, and which states it conflicts with. Passages from different states are matched by overlapping spans."""
    every = [f | {"_state": s} for s, r in results.items() for f in r["findings"] if f["status"] == "conflict" and f.get("span")]
    rows = []
    for group in statements(every):
        by_state: dict[str, dict] = {}
        for f in group:
            by_state.setdefault(f["_state"], f)
        lead = max(group, key=lambda f: len(f["handbook_quote"]))
        rows.append({"handbook_quote": lead["handbook_quote"], "handbook_page": lead["handbook_page"],
                     "states": by_state, "verdict": {s: ("conflict" if s in by_state else "ok") for s in results}})
    return sorted(rows, key=lambda r: (-len(r["states"]), r["handbook_page"] or 0))


def audit_with_fallback(state: str, handbook: list[tuple[int, str]], effort: str, api_key: str | None) -> dict:
    """A high-effort answer can run out of room on long checklists; then retry once at low effort and say so."""
    try:
        return audit_state(state, handbook, effort, api_key)
    except RuntimeError:
        if effort == "low":
            raise
        result = audit_state(state, handbook, "low", api_key)
        result["effort"] = f"low (the {effort}-effort answer was cut off)"
        return result


def audit(handbook: list[tuple[int, str]], states: list[str], effort: str = "low", api_key: str | None = None) -> dict:
    """Audit one handbook against several states at once (one Beam call per state, in parallel)."""
    with ThreadPoolExecutor(max_workers=min(6, len(states))) as pool:
        results = list(pool.map(lambda s: audit_with_fallback(s, handbook, effort, api_key), states))
    return {r["state"]: r for r in results}
