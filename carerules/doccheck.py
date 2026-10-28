"""Setup 5, "whole rulebook + quote check": one state's whole rulebook in context, that state's questions asked
together, and one tool, check_quote. Beam drafts every answer, checks all its quotes in one turn (parallel tool
calls), fixes the ones that aren't found, then gives the final answers. Few turns, so the long context is sent
only a few times."""
from __future__ import annotations

import json

from . import beam
from .agent import RULES, TOOLS, run_tool
from .grade import parse_json

CHECK_TOOL = [t for t in TOOLS if t["function"]["name"] == "check_quote"]

INSTRUCTIONS = (RULES + " Before you answer, check every quote with check_quote (you can check many at once). If a quote "
                "isn't found, copy it again exactly from the page text and check it again. When all your quotes are "
                "checked, reply with only a JSON array, one object per question: "
                '{"id": ..., "answer": ..., "quote": ..., "section": ..., "page": ...}.')


def ask(context: str, qs: list[dict], effort: str, max_turns: int = 5) -> tuple[list[dict], list[beam.Reply], list]:
    listing = "\n".join(f"{q['id']} ({q['state']}): {q['question']}" for q in qs)
    msgs = [{"role": "user", "content": f"{context}\n\n{INSTRUCTIONS}\n\nQuestions:\n{listing}"}]
    max_tokens = min(98304, max(beam.BUDGET[effort], 1500 * len(qs) + beam.BUDGET[effort]))
    replies, trace = [], []
    for _ in range(max_turns):
        rep = beam.chat(msgs, effort=effort, tools=CHECK_TOOL, max_tokens=max_tokens)
        replies.append(rep)
        if not rep.tool_calls:
            got = parse_json(rep.content)
            rows = got if isinstance(got, list) else (got.get("answers", []) if isinstance(got, dict) else [])
            return [r for r in rows if isinstance(r, dict)], replies, trace
        msgs.append({"role": "assistant", "content": rep.content or "", "reasoning_content": rep.reasoning,
                     "tool_calls": rep.tool_calls})
        for call in rep.tool_calls:
            fn = call.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            out = run_tool(fn.get("name", ""), args)
            trace.append({"tool": fn.get("name"), "args": args, "result": out[:200]})
            msgs.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": out})
    msgs.append({"role": "user", "content": "Stop checking now and reply with only the JSON array of final answers."})
    rep = beam.chat(msgs, effort=effort, max_tokens=max_tokens)
    replies.append(rep)
    got = parse_json(rep.content)
    rows = got if isinstance(got, list) else []
    return [r for r in rows if isinstance(r, dict)], replies, trace
