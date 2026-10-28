"""Render Handbook Inspector results as HTML for the Space (and as Markdown for the downloadable fix list)."""
from __future__ import annotations

import html
import math

from .audit import cross_state, statements
from .corpus import is_pdf, sources

NAMES = {"AL": "Alabama", "AR": "Arkansas", "AZ": "Arizona", "CA": "California", "CO": "Colorado",
         "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "IA": "Iowa", "IL": "Illinois",
         "MA": "Massachusetts", "MI": "Michigan", "MO": "Missouri", "MS": "Mississippi", "NC": "North Carolina",
         "ND": "North Dakota", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "OH": "Ohio",
         "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "SC": "South Carolina", "TX": "Texas",
         "VA": "Virginia", "WA": "Washington"}
COLORS = {"conflict": "#ff5d6c", "missing": "#f5a524", "partial": "#ffe186", "covered": "#3ddc97",
          "not_mentioned": "#52525b", "unverified": "#a78bfa"}
LABELS = {"conflict": "Conflicts with the rules", "missing": "Missing", "partial": "Incomplete", "covered": "Covered",
          "not_mentioned": "Not mentioned (allowed)", "unverified": "Couldn't confirm: check by hand"}


def e(x: object) -> str:
    return html.escape(str(x if x is not None else ""))


def ring(score: int, size: int = 92) -> str:
    r, c = 38, 2 * math.pi * 38
    color = "#3ddc97" if score >= 80 else "#ffe186" if score >= 50 else "#ff5d6c"
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 92 92" role="img" aria-label="Score {score} of 100">'
            f'<circle cx="46" cy="46" r="{r}" fill="none" stroke="currentColor" stroke-opacity=".12" stroke-width="8"/>'
            f'<circle cx="46" cy="46" r="{r}" fill="none" stroke="{color}" stroke-width="8" stroke-linecap="round" '
            f'stroke-dasharray="{c * score / 100:.1f} {c:.1f}" transform="rotate(-90 46 46)"/>'
            f'<text x="46" y="52" text-anchor="middle" font-size="24" font-weight="700" fill="currentColor">{score}</text></svg>')


def score_cards(results: dict) -> str:
    cards = []
    for st, r in results.items():
        c = r["counts"]
        line = " · ".join(f'<span style="color:{COLORS[k]}">{n} {lbl}</span>' for k, lbl, n in (
            ("conflict", "conflicts", c["conflict_statements"]), ("missing", "missing", c["missing"]),
            ("partial", "incomplete", c["partial"])) if n)
        cards.append(f'<div class="ci-card">{ring(r["score"])}<div><div class="ci-state">{e(NAMES.get(st, st))}</div>'
                     f'<div class="ci-dim">{e(sources().get(st, {}).get("short", ""))} · {r["required"]} required policies</div>'
                     f'<div class="ci-line">{line or "No problems found"}</div></div></div>')
    return f'<div class="ci-cards">{"".join(cards)}</div>'


def matrix(results: dict) -> str:
    rows = cross_state(results)
    if not rows or len(results) < 2:
        return ""
    states = list(results)
    head = "".join(f"<th>{e(NAMES.get(s, s))}</th>" for s in states)
    body = []
    for row in rows:
        cells = []
        for s in states:
            f = row["states"].get(s)
            cells.append(f'<td class="ci-bad" title="{e(f["requirement"])}">✕ <span>{e(f["section"])}</span></td>' if f
                         else '<td class="ci-ok">✓ <span>no conflict found</span></td>')
        body.append(f'<tr><td class="ci-q">“{e(row["handbook_quote"][:150])}”<div class="ci-dim">Handbook p. {row["handbook_page"]}</div></td>{"".join(cells)}</tr>')
    return (f'<h3 class="ci-h">One handbook, {len(states)} states</h3><p class="ci-dim">The same sentence can be fine in '
            f'one state and break the rules in another.</p><div class="ci-scroll"><table class="ci-matrix"><tr><th>'
            f'Your handbook says</th>{head}</tr>{"".join(body)}</table></div>')


def rulebook_map(state: str, r: dict) -> str:
    """The whole rulebook as one bar from page 1 to the last page, with a mark at the page of every rule the
    handbook covers, misses or breaks. Marks that would overlap stack into lanes."""
    total = int(sources().get(state, {}).get("pdf_pages") or 1)
    items = sorted((f for f in r["findings"] if str(f.get("page", "")).isdigit()), key=lambda f: int(f["page"]))
    order = {"conflict": 0, "missing": 1, "partial": 2, "unverified": 3, "covered": 4, "not_mentioned": 5}
    lanes: list[float] = []
    marks = []
    for f in sorted(items, key=lambda f: (int(f["page"]), order[f["status"]])):
        x = 1 + 98 * (int(f["page"]) - 1) / max(1, total - 1)
        lane = next((i for i, last in enumerate(lanes) if x - last >= 1.1), len(lanes))
        if lane == len(lanes):
            lanes.append(x)
        lanes[lane] = x
        marks.append((x, lane, f))
    rows = max(1, len(lanes))
    h = 14 + rows * 9
    svg = [f'<svg viewBox="0 0 100 {h}" preserveAspectRatio="none" width="100%" height="{h * 4}" class="ci-timeline" role="img" '
           f'aria-label="{e(NAMES.get(state, state))} rulebook map">',
           f'<rect x="0" y="{h - 6}" width="100" height="2" rx="1" fill="currentColor" fill-opacity=".18"/>']
    for x, lane, f in marks:
        y = h - 10 - lane * 9
        svg.append(f'<rect x="{x - .45:.2f}" y="{y - 4}" width=".9" height="8" rx=".3" fill="{COLORS[f["status"]]}">'
                   f'<title>p. {e(f["page"])} · {e(f["section"])} · {e(LABELS[f["status"]])}: {e(f["requirement"])}</title></rect>')
    svg.append("</svg>")
    legend = "".join(f'<span><i style="background:{COLORS[k]}"></i>{LABELS[k]}</span>' for k in
                     ("conflict", "missing", "partial", "covered", "not_mentioned", "unverified"))
    return (f'<div class="ci-map"><div class="ci-dim">The whole {e(NAMES.get(state, state))} rulebook, page 1 to {total}. '
            f'Each mark is a rule your handbook should cover, at its page. Hover for details.</div>{"".join(svg)}'
            f'<div class="ci-axis"><span>p. 1</span><span>p. {total}</span></div><div class="ci-legend">{legend}</div></div>')


def rule_block(f: dict, state: str) -> str:
    label = f"open page {e(f['page'])}" if is_pdf(state) else "open the official source"
    link = f' <a href="{e(f["rule_url"])}" target="_blank" rel="noopener">{label}</a>' if f.get("rule_url") else ""
    return (f'<div class="ci-quote ci-rule"><b>{e(NAMES.get(state, state))} {e(f["section"])} ✅ checked word for word{link}</b>'
            f'“{e(f["quote"])}”</div>')


def card(f: dict, state: str, also: list[dict] | None = None) -> str:
    color = COLORS[f["status"]]
    parts = [f'<div class="ci-finding" style="border-left-color:{color}"><div class="ci-tag" style="color:{color}">'
             f'{e(LABELS[f["status"]])}</div><div class="ci-req">{e(f["requirement"])}</div>']
    if f.get("handbook_quote"):
        parts.append(f'<div class="ci-quote"><b>Your handbook, p. {f["handbook_page"]}</b>“{e(f["handbook_quote"])}”</div>')
    if f.get("quote"):
        parts.append(rule_block(f, state))
    for other in also or []:
        if other.get("quote") and other["quote"] != f.get("quote"):
            parts.append(rule_block(other, state))
    if f.get("explanation"):
        parts.append(f'<p class="ci-why">{e(f["explanation"])}</p>')
    fix = f.get("fix") or next((o["fix"] for o in also or [] if o.get("fix")), "")
    if fix:
        parts.append(f'<div class="ci-fix"><div class="ci-fixhead">Suggested fix (edit before you use it)'
                     f'<button class="ci-copy" data-copy="{e(fix)}">Copy</button></div>{e(fix)}</div>')
    return "".join(parts) + "</div>"


def findings(state: str, r: dict) -> str:
    out = []
    groups = statements(r["findings"])  # one card per handbook passage, listing every rule it breaks
    if groups:
        out.append(f'<h4 class="ci-h4">{LABELS["conflict"]} ({len(groups)})</h4>'
                   + "".join(card(max(g, key=lambda f: len(f["handbook_quote"])), state, g) for g in groups))
    for status in ("missing", "partial", "unverified"):
        group = [f for f in r["findings"] if f["status"] == status]
        if group:
            out.append(f'<h4 class="ci-h4">{LABELS[status]} ({len(group)})</h4>' + "".join(card(f, state) for f in group))
    covered = [f for f in r["findings"] if f["status"] == "covered"]
    if covered:
        out.append(f'<details><summary class="ci-h4">Covered ({len(covered)})</summary>'
                   + "".join(card(f, state) for f in covered) + "</details>")
    return "".join(out)


def report(results: dict, handbook_name: str, handbook_pages: int) -> str:
    tokens = sum(r["tokens_in"] + r["tokens_out"] for r in results.values())
    secs = max(r["seconds"] for r in results.values())
    cost = sum(r["cost"] for r in results.values())
    head = (f'<div class="ci-run">Beam 1.0 read <b>{e(handbook_name)}</b> ({handbook_pages} pages) side by side with '
            f'{len(results)} complete state rulebook{"s" if len(results) > 1 else ""}: {tokens:,} tokens in {secs:.0f} seconds, '
            f'${cost:.2f}. Every quote below was checked word for word against its document.</div>')
    tabs = "".join(f'<details class="ci-state-block" {"open" if i == 0 else ""}><summary>{e(NAMES.get(s, s))}: '
                   f'{r["score"]}/100</summary>{rulebook_map(s, r)}{findings(s, r)}</details>'
                   for i, (s, r) in enumerate(results.items()))
    return f'<div class="ci">{head}{score_cards(results)}{matrix(results)}<h3 class="ci-h">Findings by state</h3>{tabs}</div>'


def fixes_markdown(results: dict, handbook_name: str) -> str:
    lines = [f"# Suggested handbook fixes: {handbook_name}", "",
             "Drafted by Beam 1.0 from each state's official rulebook. Every rule quote was checked word for word. "
             "Review and edit before you use them; this is not legal advice.", ""]
    for st, r in results.items():
        lines += [f"## {NAMES.get(st, st)} (score {r['score']}/100)", ""]
        for f in r["findings"]:
            if f.get("fix"):
                lines += [f"### {f['requirement']}", f"Rule: {f['section']}, page {f['page']}: \"{f['quote']}\"", "",
                          f["fix"], ""]
    return "\n".join(lines)


CSS = """
.ci {font-size: 15px}
.ci-run {padding: .7rem .9rem; border-radius: 10px; background: var(--background-fill-secondary); margin-bottom: 1rem}
.ci-cards {display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: .8rem; margin-bottom: 1.2rem}
.ci-card {display: flex; gap: .9rem; align-items: center; padding: .9rem; border: 1px solid var(--border-color-primary); border-radius: 14px; background: var(--block-background-fill)}
.ci-state {font-size: 1.15rem; font-weight: 700}
.ci-dim {color: var(--body-text-color-subdued); font-size: .88em}
.ci-line {margin-top: .3rem; font-size: .92em; font-weight: 600}
.ci-h {margin: 1.4rem 0 .3rem; font-size: 1.2rem}
.ci-h4 {margin: 1rem 0 .4rem; font-size: 1rem; cursor: pointer}
.ci-scroll {overflow-x: auto}
.ci-matrix {border-collapse: collapse; width: 100%; min-width: 560px; border: none !important}
.ci-matrix th, .ci-matrix td {padding: .55rem .6rem; border: none !important; border-bottom: 1px solid var(--border-color-primary) !important; text-align: left; vertical-align: top; background: transparent !important}
.ci-matrix th {font-size: .85em; text-transform: uppercase; letter-spacing: .04em; color: var(--body-text-color-subdued)}
.ci-matrix td.ci-bad {color: #e5484d; font-weight: 700; white-space: nowrap}
.ci-matrix td.ci-ok {color: #22a06b; font-weight: 700; white-space: nowrap}
.ci-matrix td span {display: block; font-weight: 400; font-size: .82em; color: var(--body-text-color-subdued)}
.ci-q {font-family: ui-serif, Georgia, serif; max-width: 380px}
.ci-map {margin: .6rem 0 1rem}
.ci-timeline {display: block; margin: .5rem 0 .1rem; color: var(--body-text-color)}
.ci-axis {display: flex; justify-content: space-between; font-size: .75em; color: var(--body-text-color-subdued); margin-bottom: .4rem}
.ci-legend i {display: inline-block; width: 12px; height: 12px; border-radius: 3px}
.ci-legend {display: flex; flex-wrap: wrap; gap: .8rem; font-size: .8em; color: var(--body-text-color-subdued)}
.ci-legend span {display: inline-flex; align-items: center; gap: .3rem}
.ci-state-block {border: 1px solid var(--border-color-primary); border-radius: 12px; padding: .6rem .9rem; margin: .6rem 0}
.ci-state-block > summary {font-weight: 700; font-size: 1.05rem; cursor: pointer}
.ci-finding {border-left: 4px solid; padding: .7rem .9rem; margin: .6rem 0; border-radius: 8px; background: var(--block-background-fill)}
.ci-tag {font-size: .75em; font-weight: 800; text-transform: uppercase; letter-spacing: .04em}
.ci-req {font-weight: 650; margin: .15rem 0 .4rem}
.ci-quote {font-family: ui-serif, Georgia, serif; padding: .45rem .7rem; margin: .35rem 0; background: var(--background-fill-secondary); border-radius: 6px}
.ci-quote b {display: block; font-family: var(--font); font-size: .78em; color: var(--body-text-color-subdued); margin-bottom: .15rem}
.ci-rule b {color: #22a06b}
.ci-why {margin: .4rem 0}
.ci-fix {margin-top: .4rem; padding: .55rem .7rem; border: 1px dashed var(--border-color-primary); border-radius: 6px}
.ci-fixhead {display: flex; justify-content: space-between; align-items: center; font-size: .8em; font-weight: 700; color: var(--body-text-color-subdued); margin-bottom: .2rem}
.ci-copy {font-size: .85em; padding: .15rem .6rem; border-radius: 6px; border: 1px solid var(--border-color-primary); background: var(--button-secondary-background-fill); cursor: pointer}
"""

COPY_JS = """element.addEventListener('click', (ev) => {
  const b = ev.target.closest('[data-copy]');
  if (!b) return;
  navigator.clipboard.writeText(b.dataset.copy).then(() => { b.textContent = 'Copied'; setTimeout(() => b.textContent = 'Copy', 1500); });
});"""
