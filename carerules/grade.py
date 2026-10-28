"""Grade an answer: is it right, and is its quote really in the official rulebook?"""
from __future__ import annotations

import json
import re

from .corpus import BENCH_GAP, find_quote, norm

ABSTAIN = re.compile(r"\b(not (?:found|addressed|covered|in (?:the|this) rulebook)|no such (?:rule|section)|"
                     r"does not (?:exist|appear|address|say)|cannot find|isn'?t in)\b", re.I)
_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                         "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
_SCALES = {"hundred": 100, "thousand": 1000}


def parse_json(text: str) -> dict | list | None:
    """Pull the JSON reply out of a model answer: the whole text, a fenced block, or the outermost object or array
    (whichever opens first), trying later starts if one doesn't parse."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for block in reversed(re.findall(r"```(?:json)?\s*(.*?)```", text, re.S)):
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            pass
    starts = sorted(i for i in (text.find("{"), text.find("[")) if i != -1)
    for start in starts:
        closer = "}" if text[start] == "{" else "]"
        end = text.rfind(closer)
        while end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                end = text.rfind(closer, start, end)
    return None


def numbers(text: str) -> list[float]:
    """Every number in the text, in reading order, whether written as digits or words.

    "twenty-five" -> 25, "one hundred twenty" -> 120, "thirty-six four-year-olds" -> 36, 4. A ratio written
    "1:18" or "1 to 18" counts as 18, the number of children per adult."""
    text = re.sub(r"\b1\s*(?::|to)\s*(\d+)", r"\1", text.lower().replace(",", ""))
    out: list[float] = []
    total = cur = 0
    seen = False

    def flush() -> None:
        nonlocal total, cur, seen
        if seen:
            out.append(float(total + cur))
        total, cur, seen = 0, 0, False

    for tok in re.findall(r"\d+(?:\.\d+)?|[a-z]+", text.replace("-", " ")):
        if tok[0].isdigit():
            flush()
            out.append(float(tok))
        elif tok in _UNITS or tok in _TENS:
            v, last = _UNITS.get(tok, _TENS.get(tok, 0)), cur % 100
            if seen and not (last == 0 or (last >= 20 and last % 10 == 0 and 0 < v < 10)):
                flush()
            cur, seen = cur + v, True
        elif tok in _SCALES and seen:
            cur = max(cur, 1) * _SCALES[tok]
            if _SCALES[tok] >= 1000:
                total, cur = total + cur, 0
        elif tok == "and" and seen:
            continue
        else:
            flush()
    flush()
    return out


def is_correct(item: dict, answer: str) -> bool:
    answer = str(answer or "")
    kind = item.get("answer_type")
    if item.get("trap"):
        return bool(ABSTAIN.search(answer))
    if kind == "number":
        # "One caregiver for every 10 children" means 10.
        answer = re.sub(r"^\W*(?:1|one|a|each)\s+(?:[a-z-]+\s+){0,5}?(?:per|for every|for each|for|to|supervises?)\s+", "", answer, flags=re.I)
        nums = numbers(answer)
        return bool(nums) and nums[0] == float(item["answer"])
    if kind == "yes_no":
        a = norm(answer).split()
        return bool(a) and a[0] == item["answer"]
    # Every term must appear; a term may list alternatives as "face up|on the back". Spaces and hyphens are ignored.
    a = norm(answer).replace(" ", "")
    terms = item.get("accept") or [item["answer"]]
    return all(any(norm(alt).replace(" ", "") in a for alt in str(t).split("|")) for t in terms)


def grade(item: dict, reply: dict | None) -> dict:
    """reply: {"answer": ..., "quote": ..., "page": ...}. Returns correct / cited / verified flags."""
    reply = reply if isinstance(reply, dict) else {}
    answer, quote = str(reply.get("answer", "")), str(reply.get("quote", "") or "")
    correct = is_correct(item, answer)
    page = find_quote(item["state"], quote, BENCH_GAP) if quote.strip() else None
    cited = page is not None
    # A right answer counts as verified only if its quote is real and backs it (a number must appear in the quote).
    backs = cited and (item.get("answer_type") != "number" or float(item["answer"]) in numbers(quote))
    return {"id": item["id"], "correct": correct, "cited": cited, "quote_page": page,
            "verified": bool(correct and (item.get("trap") or backs)), "answer": answer[:300], "quote": quote[:600]}
