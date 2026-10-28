"""Beam as a licensing inspector: it searches the official rulebook, reads pages, checks its quote word for word
with a tool, then answers. `inspect()` yields each step so a UI can show the work as it happens."""
from __future__ import annotations

import json
from typing import Iterator

from . import beam
from .corpus import BENCH_GAP, Index, find_quote, pages, states
from .grade import parse_json

RULES = ("Answer from the official rulebook text only. Give the answer first (a number, or yes/no, when the question "
         "asks for one). Then give a quote copied exactly from the rulebook that backs the answer: at least one full "
         "sentence, or a table's heading plus the row you used (8 to 60 words; you may join separate pieces in reading "
         "order with ...). Then the rule's section number and the PDF page. If the rulebook doesn't answer the "
         "question, or the question asks about a section that doesn't exist, answer \"Not in this rulebook\" with an "
         "empty quote. Never invent or paraphrase a quote.")

CLOSED_RULES = ("No rulebook is provided. Answer from what you know about this state's childcare licensing rules. Give "
                "the answer first (a number, or yes/no, when the question asks for one). If you can, quote the rule's "
                "exact words (8 to 60 words) and give its section number; if you aren't sure of the exact words, leave "
                "the quote empty rather than guess. If you don't know, answer \"I don't know\".")

SYSTEM = ("You are a careful childcare licensing inspector. You answer questions about one US state's childcare "
          "licensing rules using tools over the official rulebook. Search, read the pages you need, and check your "
          "quote with check_quote before you answer; if it isn't found, fix it from the page text. " + RULES +
          ' Finish with only a JSON object: {"answer": ..., "explanation": ..., "quote": ..., "section": ..., "page": ...}. '
          "Keep the explanation to 1-3 plain sentences.")

TOOLS = [
    {"type": "function", "function": {"name": "search_rules", "description": "Search one state's official childcare rulebook. Returns the best-matching pages with a snippet.",
     "parameters": {"type": "object", "properties": {"state": {"type": "string"}, "query": {"type": "string"}}, "required": ["state", "query"]}}},
    {"type": "function", "function": {"name": "read_page", "description": "Read one page of a state's rulebook.",
     "parameters": {"type": "object", "properties": {"state": {"type": "string"}, "page": {"type": "integer"}}, "required": ["state", "page"]}}},
    {"type": "function", "function": {"name": "check_quote", "description": "Check that a quote appears word for word in the state's rulebook. Returns the page, or found=false.",
     "parameters": {"type": "object", "properties": {"state": {"type": "string"}, "quote": {"type": "string"}}, "required": ["state", "quote"]}}},
]

_INDEX: Index | None = None


def index() -> Index:
    global _INDEX
    if _INDEX is None:
        _INDEX = Index()
    return _INDEX


def run_tool(name: str, args: dict) -> str:
    st = str(args.get("state", "")).upper()
    if st not in states():
        return json.dumps({"error": f"unknown state {st}; available: {states()}"})
    if name == "search_rules":
        hits = index().search(str(args.get("query", "")), state=st, k=5)
        return json.dumps([{"page": p.number, "snippet": " ".join(p.text.split())[:700]} for _, p in hits])
    if name == "read_page":
        try:
            n = int(args.get("page", 0))
        except (TypeError, ValueError):
            n = 0
        page = next((p for p in pages(st) if p.number == n), None)
        return page.text[:8000] if page else json.dumps({"error": "no such page"})
    if name == "check_quote":
        page = find_quote(st, str(args.get("quote", "")), BENCH_GAP)
        return json.dumps({"found": page is not None, "page": page})
    return json.dumps({"error": "unknown tool"})


def inspect(state: str, question: str, effort: str = "low", api_key: str | None = None,
            max_turns: int = 14) -> Iterator[dict]:
    """Yields {"type": "tool", ...} for each tool call, then one {"type": "final", "answer": {...}, ...}."""
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"State: {state}\nQuestion: {question}"}]
    cost = tokens_in = tokens_out = 0
    finish = ""
    for turn in range(max_turns):
        rep = beam.chat(msgs, effort=effort, tools=TOOLS, api_key=api_key)
        cost, tokens_in, tokens_out, finish = cost + rep.cost, tokens_in + rep.tokens_in, tokens_out + rep.tokens_out, rep.finish
        if not rep.tool_calls:
            got = parse_json(rep.content)
            ans = got if isinstance(got, dict) else {"answer": rep.content.strip()}
            yield {"type": "final", "answer": ans, "turns": turn + 1, "cost": cost, "tokens_in": tokens_in,
                   "tokens_out": tokens_out, "finish": finish, "reasoning": rep.reasoning[-4000:]}
            return
        # Beam's server wants each earlier turn's reasoning sent back with it.
        msgs.append({"role": "assistant", "content": rep.content or "", "reasoning_content": rep.reasoning,
                     "tool_calls": rep.tool_calls})
        for call in rep.tool_calls:
            fn = call.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            out = run_tool(fn.get("name", ""), args)
            yield {"type": "tool", "name": fn.get("name"), "args": args, "result": out, "cost": cost}
            msgs.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": out})
    yield {"type": "final", "answer": {"answer": ""}, "turns": max_turns, "cost": cost, "tokens_in": tokens_in,
           "tokens_out": tokens_out, "finish": "max_turns", "reasoning": ""}
