"""Summarize results/*.jsonl into results/summary.json (with an HTML table for the Space) and results/summary.md."""
from __future__ import annotations

import html
import json
from collections import defaultdict

from .corpus import ROOT

RESULTS = ROOT / "results"
MODES = {"closed": "No rulebook (memory only)", "doc": "Whole state rulebook in context",
         "stack": "Many rulebooks in one ~1M-token context", "agent": "Agent: search, read, check quote",
         "doccheck": "Whole rulebook + quote check tool"}
KINDS = {"lookup": "Rule lookups", "inspection": "Scenario questions", "trap": "Made-up section numbers"}


def kind(row: dict) -> str:
    return "trap" if row["topic"] == "trap" else "inspection" if row["topic"] == "inspection" else "lookup"


def load() -> list[dict]:
    rows = []
    for path in sorted(RESULTS.glob("*-*.jsonl")):
        rows += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return rows


def stats(rows: list[dict]) -> dict:
    n = len(rows)
    quoted = [r for r in rows if r.get("quote")]
    verified = sum(r["verified"] for r in rows)
    cost = sum(r.get("cost", 0) for r in rows)
    return {
        "n": n,
        "correct": round(sum(r["correct"] for r in rows) / n, 4) if n else 0,
        "verified": round(verified / n, 4) if n else 0,
        "fake_quotes": round(sum(not r["cited"] for r in quoted) / len(quoted), 4) if quoted else 0,
        "empty": round(sum(not r.get("answer") for r in rows) / n, 4) if n else 0,
        "cost": round(cost, 4),
        "cost_per_verified": round(cost / verified, 5) if verified else None,
        "tokens": int(sum(r.get("tokens_in", 0) + r.get("tokens_out", 0) for r in rows)),
    }


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def build() -> dict:
    rows = load()
    runs = defaultdict(list)
    for r in rows:
        runs[(r["mode"], r["effort"])].append(r)
    order = sorted(runs, key=lambda k: (list(MODES).index(k[0]), k[1] != "low", k[1]))
    table = []
    for key in order:
        rs = runs[key]
        entry = {"mode": key[0], "effort": key[1], "label": MODES[key[0]], **stats(rs),
                 "by_kind": {k: stats([r for r in rs if kind(r) == k]) for k in KINDS if any(kind(r) == k for r in rs)}}
        table.append(entry)
    out = {"runs": table, "items": len({r["id"] for r in rows})}
    out["html"] = to_html(table)
    out["markdown"] = to_md(table)
    return out


def to_html(table: list[dict]) -> str:
    if not table:
        return ""
    head = ("<table class='res'><tr><th>Setup</th><th>Effort</th><th>Questions</th><th>Right answer</th>"
            "<th>Right, with a real quote</th><th>Quotes not in the rulebook</th><th>Cost</th><th>Cost per verified answer</th></tr>")
    body = []
    for t in table:
        bar = f"<div class='bar' style='width:{max(2, int(100 * t['verified']))}%'></div>"
        cpv = f"${t['cost_per_verified']:.4f}" if t["cost_per_verified"] is not None else "–"
        body.append(f"<tr><td>{html.escape(t['label'])}</td><td>{t['effort']}</td><td>{t['n']}</td><td>{pct(t['correct'])}</td>"
                    f"<td>{pct(t['verified'])}{bar}</td><td>{pct(t['fake_quotes'])}</td><td>${t['cost']:.2f}</td><td>{cpv}</td></tr>")
    kinds = ["<h3>By question type (right, with a real quote)</h3><table class='res'><tr><th>Setup</th><th>Effort</th>"
             + "".join(f"<th>{v}</th>" for v in KINDS.values()) + "</tr>"]
    for t in table:
        cells = "".join(f"<td>{pct(t['by_kind'][k]['verified'])} <span class='dim'>({t['by_kind'][k]['n']})</span></td>"
                        if k in t["by_kind"] else "<td>–</td>" for k in KINDS)
        kinds.append(f"<tr><td>{html.escape(t['label'])}</td><td>{t['effort']}</td>{cells}</tr>")
    return head + "".join(body) + "</table>" + "".join(kinds) + "</table>"


def to_md(table: list[dict]) -> str:
    lines = ["| Setup | Effort | Questions | Right answer | Right, with a real quote | Quotes not in the rulebook | Cost |",
             "|---|---|---|---|---|---|---|"]
    for t in table:
        lines.append(f"| {t['label']} | {t['effort']} | {t['n']} | {pct(t['correct'])} | **{pct(t['verified'])}** | "
                     f"{pct(t['fake_quotes'])} | ${t['cost']:.2f} |")
    return "\n".join(lines)


if __name__ == "__main__":
    s = build()
    (RESULTS / "summary.json").write_text(json.dumps(s, indent=1))
    (RESULTS / "summary.md").write_text(s["markdown"] + "\n")
    print(s["markdown"])
