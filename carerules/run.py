"""Run Beam on CareRules in one of four setups and grade every answer.

  closed  no rulebook: Beam answers from memory (shows how often it invents quotes)
  doc     one state's whole rulebook in context, that state's questions asked together
  stack   many states' rulebooks in one context (up to about 1M tokens), questions from all of them
  agent   Beam gets tools: search the rulebook, read a page, check a quote word for word; one question at a time

python3 -I -m carerules.run <mode> --effort low|high [--states TX,NC] [--limit N] [--dry]"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict

from . import agent, beam
from .agent import CLOSED_RULES, RULES
from .corpus import ROOT, pages, sources, states
from .grade import grade, parse_json
from .items import all_items

RESULTS = ROOT / "results"

def book(state: str) -> str:
    src = sources().get(state, {})
    head = f"=== RULEBOOK {state}: {src.get('title', state)} ===\n"
    return head + "\n".join(f"[{state} page {p.number}]\n{p.text.strip()}" for p in pages(state))


def ask_batch(context: str, qs: list[dict], effort: str, rules: str = RULES) -> tuple[list[dict], beam.Reply]:
    listing = "\n".join(f"{q['id']} ({q['state']}): {q['question']}" for q in qs)
    prompt = (f"{context}\n\n{rules}\n\nQuestions:\n{listing}\n\nReply with only a JSON array, one object per "
              f'question: {{"id": ..., "answer": ..., "quote": ..., "section": ..., "page": ...}}.')
    max_tokens = max(beam.BUDGET[effort], 1500 * len(qs) + beam.BUDGET[effort])
    rep = beam.chat([{"role": "user", "content": prompt}], effort=effort, max_tokens=min(max_tokens, 98304))
    got = parse_json(rep.content)
    rows = got if isinstance(got, list) else (got.get("answers", []) if isinstance(got, dict) else [])
    return [r for r in rows if isinstance(r, dict)], rep


def ask_agent(q: dict, effort: str) -> tuple[dict, dict, list]:
    trace, final = [], {}
    for step in agent.inspect(q["state"], q["question"], effort):
        if step["type"] == "tool":
            trace.append({"tool": step["name"], "args": step["args"], "result": step["result"][:300]})
        else:
            final = step
    return final.get("answer", {}), final, trace


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["closed", "doc", "stack", "agent"])
    ap.add_argument("--effort", default="low", choices=list(beam.BUDGET))
    ap.add_argument("--states", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--stack-tokens", type=int, default=900_000, help="most rulebook tokens per stack-mode context (limit 1,048,576)")
    ap.add_argument("--dry", action="store_true", help="print the plan and estimated cost, call nothing")
    a = ap.parse_args()

    items = all_items()
    if a.states:
        keep = set(a.states.upper().split(","))
        items = [i for i in items if i["state"] in keep]
    if a.limit:
        items = items[: a.limit]
    by_state = defaultdict(list)
    for i in items:
        by_state[i["state"]].append(i)

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{a.mode}-{a.effort}.jsonl"
    done = {json.loads(l)["id"] for l in out.read_text().splitlines()} if out.exists() else set()
    todo = [i for i in items if i["id"] not in done]
    # Exact Beam token counts (data/sources.json, from Beam's tokenizer.json), else about 4 characters per token.
    approx = {s: sources().get(s, {}).get("beam_tokens") or sum(len(p.text) for p in pages(s)) // 4 for s in states()}
    print(f"{a.mode}/{a.effort}: {len(todo)} items to run ({len(done)} already done)", file=sys.stderr)

    def save(rows: list[dict]) -> None:
        with out.open("a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def record(q: dict, ans: dict, reps: list[beam.Reply], share: float = 1.0, trace: list | None = None) -> dict:
        g = grade(q, ans)
        g.update({"mode": a.mode, "effort": a.effort, "state": q["state"], "topic": q["topic"],
                  "cost": round(sum(r.cost for r in reps) * share, 6),
                  "tokens_in": int(sum(r.tokens_in for r in reps) * share), "tokens_out": int(sum(r.tokens_out for r in reps) * share),
                  "finish": [r.finish for r in reps][-1:], "turns": len(reps), "tools": trace or []})
        return g

    if a.dry:
        if a.mode == "doc":
            est = sum(approx[s] * -(-len(v) // a.batch) for s, v in by_state.items())
        elif a.mode == "stack":
            est = a.stack_tokens * -(-len(todo) // a.batch)
        elif a.mode == "agent":
            est = 40_000 * len(todo)
        else:
            est = 400 * len(todo)
        print(f"~{est/1e6:.1f}M input tokens, about ${est * beam.PRICE_IN / 1e6:.2f} before output", file=sys.stderr)
        return

    if a.mode == "closed":
        for st, qs in by_state.items():
            for k in range(0, len(qs), a.batch):
                chunk = [q for q in qs[k:k + a.batch] if q["id"] not in done]
                if not chunk:
                    continue
                rows, rep = ask_batch("", chunk, a.effort, rules=CLOSED_RULES)
                found = {str(r.get("id")): r for r in rows}
                save([record(q, found.get(q["id"]), [rep], 1 / len(chunk)) for q in chunk])
    elif a.mode == "doc":
        for st, qs in by_state.items():
            ctx = book(st)
            for k in range(0, len(qs), a.batch):
                chunk = [q for q in qs[k:k + a.batch] if q["id"] not in done]
                if not chunk:
                    continue
                rows, rep = ask_batch(ctx, chunk, a.effort)
                found = {str(r.get("id")): r for r in rows}
                save([record(q, found.get(q["id"]), [rep], 1 / len(chunk)) for q in chunk])
                print(st, rep.finish, rep.tokens_in, rep.tokens_out, f"${rep.cost:.3f}", file=sys.stderr)
    elif a.mode == "stack":
        order = sorted(states(), key=lambda s: approx[s])
        groups, cur, size = [], [], 0
        for s in order:  # pack states into contexts of about stack_tokens each
            if cur and size + approx[s] > a.stack_tokens:
                groups.append(cur)
                cur, size = [], 0
            cur.append(s)
            size += approx[s]
        groups.append(cur)
        for grp in groups:
            ctx = "\n\n".join(book(s) for s in grp)
            qs = [q for s in grp for q in by_state.get(s, []) if q["id"] not in done]
            for k in range(0, len(qs), a.batch):
                chunk = qs[k:k + a.batch]
                rows, rep = ask_batch(ctx, chunk, a.effort)
                found = {str(r.get("id")): r for r in rows}
                save([record(q, found.get(q["id"]), [rep], 1 / len(chunk)) for q in chunk])
                print(grp, rep.finish, rep.tokens_in, rep.tokens_out, f"${rep.cost:.3f}", file=sys.stderr)
    else:
        for q in todo:
            ans, final, trace = ask_agent(q, a.effort)
            g = grade(q, ans)
            g.update({"mode": a.mode, "effort": a.effort, "state": q["state"], "topic": q["topic"],
                      "cost": round(final.get("cost", 0), 6), "tokens_in": final.get("tokens_in", 0),
                      "tokens_out": final.get("tokens_out", 0), "finish": [final.get("finish")],
                      "turns": final.get("turns", 0), "tools": trace})
            save([g])
            print(q["id"], g["correct"], g["verified"], final.get("turns"), "turns", f"${final.get('cost', 0):.4f}", file=sys.stderr)
            time.sleep(0.2)

if __name__ == "__main__":
    main()
