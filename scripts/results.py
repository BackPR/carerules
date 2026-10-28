"""Write results/RESULTS.md from the saved summaries (no Beam call), so the published numbers always match the data:
the planted-defect test, whole rulebook vs relevant pages, and the 428-question benchmark.
Usage: python3 -I scripts/results.py (after scripts/eval_inspector.py and scripts/report.py)"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
NAMES = {"CA": "California", "FL": "Florida", "IL": "Illinois", "NC": "North Carolina", "NJ": "New Jersey",
         "OR": "Oregon", "PA": "Pennsylvania", "TX": "Texas"}
focused = {r["state"]: r for r in json.loads((RES / "inspector/summary-low-focused.json").read_text())}
full = {r["state"]: r for r in json.loads((RES / "inspector/summary-low-full.json").read_text())}


def total(rows, key):
    return sum(r[key] for r in rows)


def tokens_in(state, mode):
    return json.loads((RES / f"inspector/{state}-defective-low-{mode}.json").read_text())["tokens_in"]


rows = rows_all = [focused[s] for s in sorted(focused, key=lambda s: NAMES[s])]
out = ["### Handbook Inspector: planted-defect test (Beam 1.0, low effort, relevant rule pages)", "",
       "Eight realistic, fictional handbooks (one per state, about 2,500 words each) were written to cover every required "
       "policy. Then 5 sentences were swapped for versions that break a specific rule, and 3 required policies were "
       "deleted. Each handbook was checked in both versions. Planted mistakes are easier to find than real ones.", "",
       "| State | Planted conflicts flagged | Deleted policies caught | Conflicts claimed on the compliant handbook | "
       "Score: compliant → planted | Cost (both checks) |", "|---|---|---|---|---|---|"]
for r in rows:
    out.append(f"| {NAMES[r['state']]} | {r['planted_flagged']}/{r['planted']} | {r['removed_missing_or_partial']}/{r['removed']} | "
               f"{r['clean_false_conflicts']} | {r['clean_score']} → {r['defective_score']} | ${r['cost']:.3f} |")
out.append(f"| **All {len(rows)}** | **{total(rows, 'planted_flagged')}/{total(rows, 'planted')}** "
           f"({total(rows, 'planted_on_right_item')} on the exact checklist item) | "
           f"**{total(rows, 'removed_missing_or_partial')}/{total(rows, 'removed')}** | **{total(rows, 'clean_false_conflicts')}** "
           f"in {len(rows)} handbooks | | **${total(rows, 'cost'):.2f}** for {2 * len(rows)} checks |")
out += ["", "Of the 3 conflicts claimed on compliant handbooks, 2 were real gaps the handbook writer missed (Florida: an "
        "allergy list posted where parents can see it, which the rule forbids; California: the 15-minute infant sleep "
        "check must also record breathing, signs of distress and sleep position) and 1 was a misreading (New Jersey: the "
        "two-staff-in-the-building rule read as a nap-room ratio). California's compliant score is lower because its "
        "rules also cover programs this handbook doesn't run (school-age and mildly ill care).", "",
        "Each planted defect maps to an item on the state's checklist, so this test measures the inspection, not whether the "
        "checklist is complete. Checklist items whose quote failed verification were dropped and are listed in each "
        "checklist's `dropped_unverified` (for example two of Virginia's ratio and group-size items).", ""]

both = sorted(full, key=lambda s: NAMES[s])
f_rows, u_rows = [focused[s] for s in both], [full[s] for s in both]
ratio = [tokens_in(s, "full") / tokens_in(s, "focused") for s in both]
out += [f"### Whole rulebook or relevant pages? ({len(both)} states, same handbooks)", "",
        "Beam 1.0 can read a state's whole rulebook in one call. The live tool sends the checklist's pages plus the pages "
        "that best match the handbook instead, because on this test it found the same planted mistakes for less than half "
        "the cost. With the whole rulebook it claimed no conflicts on the compliant handbooks: it avoided the New Jersey "
        "misreading, but it also missed the real Florida gap (an allergy list posted where parents can see it).", "",
        "| Context sent to Beam | Planted conflicts flagged | Deleted policies caught | Conflicts claimed on compliant handbooks | Cost |",
        "|---|---|---|---|---|",
        f"| Whole rulebook | {total(u_rows, 'planted_flagged')}/{total(u_rows, 'planted')} | "
        f"{total(u_rows, 'removed_missing_or_partial')}/{total(u_rows, 'removed')} | {total(u_rows, 'clean_false_conflicts')} | ${total(u_rows, 'cost'):.2f} |",
        f"| Relevant pages (live tool) | {total(f_rows, 'planted_flagged')}/{total(f_rows, 'planted')} | "
        f"{total(f_rows, 'removed_missing_or_partial')}/{total(f_rows, 'removed')} | {total(f_rows, 'clean_false_conflicts')} | ${total(f_rows, 'cost'):.2f} |",
        "", f"Relevant pages used {min(ratio):.1f} to {max(ratio):.1f} times fewer input tokens per state "
        f"({', '.join(f'{NAMES[s]} {r:.1f}x' for s, r in zip(both, ratio))}).", ""]

high_path = RES / "inspector/summary-high-focused.json"
if high_path.exists():  # the same test at high reasoning effort ("Extra thorough")
    high = {r["state"]: r for r in json.loads(high_path.read_text())}
    both_h = sorted(set(high) & set(focused), key=lambda s: NAMES[s])
    h_rows, l_rows = [high[s] for s in both_h], [focused[s] for s in both_h]
    sec = lambda rows: sum(max(x for x in r["seconds"] if x) for r in rows) / len(rows)  # noqa: E731
    out += [f"### Reasoning effort: Standard (low) vs Extra thorough (high), {len(both_h)} states", "",
            "| Effort | Planted conflicts flagged | Deleted policies caught | Conflicts claimed on compliant handbooks | Cost | Slowest check, average |",
            "|---|---|---|---|---|---|",
            f"| Standard (low) | {total(l_rows, 'planted_flagged')}/{total(l_rows, 'planted')} | {total(l_rows, 'removed_missing_or_partial')}/{total(l_rows, 'removed')} | "
            f"{total(l_rows, 'clean_false_conflicts')} | ${total(l_rows, 'cost'):.2f} | {sec(l_rows):.0f} s |",
            f"| Extra thorough (high) | {total(h_rows, 'planted_flagged')}/{total(h_rows, 'planted')} | {total(h_rows, 'removed_missing_or_partial')}/{total(h_rows, 'removed')} | "
            f"{total(h_rows, 'clean_false_conflicts')} | ${total(h_rows, 'cost'):.2f} | {sec(h_rows):.0f} s |", "",
            "Both efforts found every planted mistake. On the compliant handbooks we read each claimed conflict by hand. Standard's 3: "
            "2 real (Florida's allergy list, California's sleep-check log) and 1 misreading (New Jersey). Extra thorough's 6: 3 real "
            "(California's sleep-check log; Illinois's \"Tdap ... vaccination or immunity\", where the rule says no test replaces Tdap; "
            "Oregon's center is open 11 hours, so preschoolers need 90 minutes of active play, not 60), 2 misreadings (New Jersey "
            "again, and Illinois rest time, which follows Section 407.350) and 1 debatable (California infant sleep position). So "
            "Extra thorough found two real problems Standard missed, raised more false alarms and cost more; the live tool "
            "defaults to Standard.", ""]

real_path = RES / "real-handbook.json"
if real_path.exists():  # one real, published handbook, findings judged by hand
    real = json.loads(real_path.read_text())
    from collections import Counter
    v = Counter(f["verdict"] for f in real["findings"])
    out += ["### One real handbook", "", real["what"], "",
            f"Result: score {real['score']}/100, {len(real['findings'])} findings, {real['tokens_in']:,} tokens in, {real['seconds']:.0f} seconds, ${real['cost']:.2f}. "
            "Our reading of each finding: " + ", ".join(
                f"{v[k]} {'depend on facts outside the handbook' if k.startswith('depends') and v[k] > 1 else k}"
                for k in ("correct", "reasonable", "worth checking", "depends on facts outside the handbook", "debatable", "misreading")
                if v[k]) + ".", "",
            "| Finding | Rule | Our reading |", "|---|---|---|"]
    out += [f"| {f['status'].replace('conflict', 'breaks a rule').replace('partial', 'incomplete').replace('unverified', 'check by hand')}: {f['requirement']} | "
            f"{f['rule'].split(', ', 1)[1] if f['rule'].startswith('rule on page') else f['rule']} | "
            f"**{f['verdict']}**: {f['why']} |" for f in real["findings"]]
    out += [""]

qa = json.loads((RES / "summary.json").read_text())
rows = {m: [json.loads(l) for l in (RES / f"{m}-low.jsonl").read_text().splitlines()] for m in ("closed", "doc", "agent")}
quoted = {m: [r for r in v if (r.get("quote") or "").strip()] for m, v in rows.items()}
miss = {m: [r for r in v if not r.get("cited")] for m, v in quoted.items()}
doc_digits = sum(any(c.isdigit() for c in r["quote"]) for r in miss["doc"])
doc_stitched = sum("..." in r["quote"] or "…" in r["quote"] for r in miss["doc"])
out += ["### Whole rulebook vs memory vs search: 428 questions on 15 states' rules", "",
        "The same questions in three setups: no rulebook (memory only), each state's whole rulebook in one context, and an "
        "agent that searches the rulebook, reads pages and checks its own quotes.", "", qa["markdown"], "",
        "Right answer: matches the answer key. Right, with a real quote: the answer is right and its quote appears word for "
        "word in the official rules (for a number, the quote must contain it).", "",
        f"Quotes not in the rulebook counts the answers that gave a quote: {len(quoted['closed'])} of 428 from memory (asked for "
        f"no quote without the rules; none of the {len(miss['closed'])} appears in the rules), {len(quoted['doc'])} with the whole rulebook "
        f"({len(miss['doc'])} didn't match; {doc_digits} of those contain numbers, mostly table rows, and {doc_stitched} stitch "
        f"table cells together with \"...\"), and {len(quoted['agent'])} for the agent ({len(miss['agent'])} didn't match).", "",
        "Whole rulebook: each state's questions were asked together, up to 25 per call, so per-question tokens and cost are "
        "that call's share. All runs here use low reasoning effort (\"Standard\"); the sample report on the page used high "
        "(\"Extra thorough\").", ""]
(RES / "RESULTS.md").write_text("\n".join(out))
# The Space card shows the totals, not the per-state rows (those stay in RESULTS.md and the dataset).
first = out.index("| State | Planted conflicts flagged | Deleted policies caught | Conflicts claimed on the compliant handbook | "
                  "Score: compliant → planted | Cost (both checks) |")
last = next(i for i in range(first, len(out)) if out[i].startswith("| **All"))
short = out[:first] + [f"Across all {len(rows_all)} states: **{total(rows_all, 'planted_flagged')}/{total(rows_all, 'planted')}** planted "
                       f"conflicts flagged ({total(rows_all, 'planted_on_right_item')} on the exact checklist item), "
                       f"**{total(rows_all, 'removed_missing_or_partial')}/{total(rows_all, 'removed')}** deleted policies caught, "
                       f"**{total(rows_all, 'clean_false_conflicts')}** conflicts claimed on the compliant handbooks, "
                       f"${total(rows_all, 'cost'):.2f} for {2 * len(rows_all)} checks. Per-state results: "
                       "[RESULTS.md in the dataset](https://huggingface.co/datasets/backpr/carerules/blob/main/results/RESULTS.md)."] + out[last + 1:]
(RES / "RESULTS-short.md").write_text("\n".join(short))
print("\n".join(out))
