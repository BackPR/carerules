---
title: CareRules Handbook Inspector
emoji: 🧒
colorFrom: purple
colorTo: pink
sdk: static
app_file: index.html
pinned: true
license: apache-2.0
short_description: Does a daycare handbook match its state's licensing rules?
models:
  - reflection/Beam-1.0-501B-A23B
datasets:
  - backpr/carerules
tags:
  - beam
  - long-context
  - verification
  - legal
  - childcare
  - benchmark
  - compliance
  - rl-environment
---

# CareRules Handbook Inspector

**A child care center adds its parent handbook (the written policies it gives families at enrollment). Beam 1.0 checks it against the official licensing rules of each state the center runs in and returns the sentences that conflict with a rule, the required policies that are missing, and suggested wording. Plain code checks every quote word for word before it's shown.**

**Judges: [run a live check]({{JUDGES_LINK}})** (no code needed for the sample handbooks) · [Live page](https://care.backpr.com) · [Dataset](https://huggingface.co/datasets/backpr/carerules) · [Code](https://github.com/BackPR/carerules) · Individual entry by MohammadMahdi RezaAli, published by BackPR

![Does your parent handbook match your state's licensing rules?](https://huggingface.co/spaces/backpr/carerules-inspector/resolve/main/static/media/og.jpg)

## At a glance

- **A real task on real documents.** 22 states and DC, 1,819,794 tokens of official licensing rules. The same handbook sentence can be fine in North Carolina and break a rule in Texas, so one handbook is checked against several states at once, side by side.
- **How Beam is used.** Beam read each state's whole rulebook in one context to build a checklist of what a handbook must cover. Each check is one Beam call per state with that checklist, the relevant rule pages and the whole handbook; Beam names the exact clause a sentence conflicts with and drafts new wording.
- **Measured** (reasoning effort low, "Standard"): 40 of 40 planted conflicts and 24 of 24 deleted policies found across 8 states, $0.49 for 16 checks. On 428 rule questions, Beam went from 57.2% right from memory to 99.8% with the whole rulebook in context, but 20.6% of its quotes didn't match the rules word for word, which is why every quote here is checked.
- **Nothing unproven is shown as fact.** A finding whose quote can't be confirmed is shown as "check by hand", never as fact; so is a "rule" that turns out to be a state's guidance box. Quotes must start and end on whole words, and a "..." may not skip a "not".
- **Open.** Rules, checklists, test handbooks with answer keys, every run, and an RL environment whose reward comes from the same quote checker.

## Why Beam's long context matters

- **Checklists come from the whole rulebook.** State rules run from 21 to 377 pages (20k to 210k Beam tokens). Beam read each state's rulebook in one pass and listed what a handbook must cover: 27 to 231 requirements per state, each with a quote that code verified word for word.
- **Whole rulebook beats memory and search.** On 428 questions about 15 states' rules, Beam with each state's whole rulebook in context answered 99.8% right. From memory it got 57.2%; as an agent that searches the rulebook, reads pages and checks its own quotes, 85.5%, at 7 times the cost ($4.73 vs $0.65).
- **The live check builds on that.** Each check sends the checklist, the rule pages it cites plus the pages that best match the handbook, and the whole handbook: 22k to 49k tokens per call in our tests. Sending each whole rulebook (65k to 172k tokens) found the same planted mistakes at 2.4 times the cost, so the live tool sends the relevant pages.
- **Effort:** at high reasoning effort ("Extra thorough") Beam found the same 40/40 and 24/24 and two real problems in the compliant handbooks that low effort missed, but also more false alarms, for $0.84 vs $0.49 for 16 checks. The live tool defaults to low ("Standard"); the sample report used high.

![A sample report: the handbook page marked up, with the rules beside it](https://huggingface.co/spaces/backpr/carerules-inspector/resolve/main/static/media/report-shot.jpg)

## How Beam is used

1. **Checklists (once per state).** Beam reads each state's whole rulebook (up to 210k tokens) and lists what a center's written policies must cover, plus the core rules handbooks get wrong. Every item carries a quote verified against the official text.
2. **Inspection (per upload).** One Beam call per state: the checklist, the rulebook pages it cites plus the pages most relevant to the handbook, and the handbook. Beam returns a status for every checklist item, the exact rule clause broken, and a fix. Several states run in parallel; very long checklists are split.
3. **Verification.** Handbook quotes, rule quotes and section labels are checked mechanically; findings Beam can't prove become "check by hand" or are dropped.

## Results

{{RESULTS}}

## Try it in 2 minutes

1. **See a finished report:** open the sample report (one made-up handbook checked for Texas, North Carolina and Oregon) or any of the 8 sample reports, each with its answer key. They load instantly and cost nothing.
2. **Run a live check, no code needed:** under "No handbook handy? Try a sample handbook", load one of the eight sample handbooks, change a sentence or two so they break a rule (for example "no more than four babies" to "up to six babies" in the Texas one), and press Check. Beam checks it against that state's rules in about 10 to 60 seconds. A planted Texas infant-ratio mistake took 10 seconds and about 1 cent.
3. **Your own handbook** needs a free access code (one check a day, sent on request to hi@backpr.com). Checking the same file again is free.

This Space is a static page: the handbook is read, the rule pages are chosen and every quote is checked in your browser. A small Cloudflare Worker keeps the Beam token, checks the code, accepts only CareRules prompts, enforces spending limits and caches replies. The same page runs at [care.backpr.com](https://care.backpr.com).

## Limits

- **Not legal advice.** Reports are drafted by AI and checked by a computer, not reviewed by a lawyer. A quote that matches word for word proves the words are there, not that Beam read them correctly; read each finding and confirm changes with your licensing agency.
- **Licensing rules only.** Other laws (for example child abuse reporting laws) also apply. Rules were downloaded from official state sources on October 28, 2026 and change over time. Arkansas's rules cover out-of-school-time programs only. Family child care homes aren't covered.
- **Checklists were compiled by Beam** from each state's rules; every item's quote is verified, but no lawyer has reviewed the lists.
- **Real handbooks are harder** than the planted-defect test, and each planted mistake maps to a checklist item, so the test measures the inspection, not whether a checklist is complete. Scanned PDFs can't be read.
- **Privacy:** the handbook's text goes through the Worker and Hugging Face to Beam (hosted by Baseten); the answer is cached for 7 days. Use is subject to the [terms of use](https://care.backpr.com/#terms), which follow [Reflection's Usage Policy](https://reflection.ai/legal/usage-policy).

## Licenses and credits

Code: Apache 2.0. Our data (checklists, questions, test handbooks, results): CC BY 4.0. The state rule texts are official government documents under their publishers' terms, not ours, included so quotes can be checked word for word; photos come from Unsplash, fonts are under the SIL Open Font License, and the BackPR name and logo are trademarks. Details: [CREDITS.md](https://huggingface.co/spaces/backpr/carerules-inspector/blob/main/CREDITS.md).

Individual entry by MohammadMahdi RezaAli. Made by [BackPR](https://backpr.com).
