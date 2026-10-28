"""Check answer-key items: every quote must appear word for word in the state's official text, on the stated page,
and a number answer must appear in the quote. Usage: python3 -I scripts/check_items.py <items.jsonl> [...]"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from carerules.corpus import BENCH_GAP, find_quote, norm  # noqa: E402
from carerules.grade import numbers  # noqa: E402

REQUIRED = {"id", "state", "topic", "question", "answer", "answer_type", "quote", "page", "section"}
TYPES = {"number", "yes_no", "short_text"}


def number_in(answer: str, quote: str) -> bool:
    want = numbers(answer)
    return bool(want) and all(n in numbers(quote) for n in want)


def check(item: dict) -> list[str]:
    errs = [f"missing {k}" for k in REQUIRED - item.keys()]
    if errs:
        return errs
    if item["answer_type"] not in TYPES:
        errs.append(f"bad answer_type {item['answer_type']}")
    page = find_quote(item["state"], item["quote"], BENCH_GAP)
    if page is None:
        errs.append("quote not found word for word")
    elif abs(page - int(item["page"])) > 1:
        errs.append(f"quote found on page {page}, item says {item['page']}")
    if item["answer_type"] == "number" and not number_in(str(item["answer"]), item["quote"]):
        errs.append("number answer not in quote")
    if item["answer_type"] == "short_text" and not item.get("accept"):
        errs.append("short_text needs accept: list of key terms a right answer must contain")
    return errs


if __name__ == "__main__":
    bad = total = 0
    for path in sys.argv[1:]:
        for line in Path(path).read_text().splitlines():
            if not line.strip():
                continue
            item, total = json.loads(line), total + 1
            if item.get("status") == "not_found":
                continue
            errs = check(item)
            if errs:
                bad += 1
                print(f"FAIL {item.get('id')}: {'; '.join(errs)}")
    print(f"{total - bad}/{total} ok")
    sys.exit(1 if bad else 0)
