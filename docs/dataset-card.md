---
license: cc-by-4.0
language:
  - en
pretty_name: "CareRules: child care handbooks checked against state licensing rules"
size_categories:
  - n<1K
task_categories:
  - question-answering
  - text-classification
tags:
  - long-context
  - legal
  - verification
  - benchmark
  - rl-environment
  - beam
configs:
  - config_name: qa_items
    data_files: data/items.jsonl
    default: true
---

# CareRules

Data behind the [CareRules Handbook Inspector](https://huggingface.co/spaces/backpr/carerules-inspector): a child care center uploads its parent handbook, and Beam 1.0 checks it against each state's official licensing rules, using a checklist Beam compiled from the complete rulebook. Every quote it shows (from the handbook and from the rules) is checked word for word by a plain program first.

US child care centers are licensed by their state, and each state's rules run from 20 to more than 370 pages. A wrong answer from a model looks exactly like a right one, so everything here is built so a program can check it.

## Results

{{RESULTS}}

## What's in this dataset

| Path | What it is |
|---|---|
| `rulebooks/<STATE>.txt` | Text of each state's official child care center licensing rules, 22 states and DC, 1,819,794 tokens counted with Beam's tokenizer (Arkansas: out-of-school-time facilities). For PDF sources, pages are separated by form feeds, so page N is page N of the PDF. |
| `rulebooks/sources.json` | Title, official URL, download date (October 28, 2026), format, SHA-256 of the PDF, page and exact token counts. |
| `checklists/<STATE>.json` | What a center's written policies and handbook must cover in that state, plus the core rules handbooks get wrong. Compiled by Beam from the whole rulebook; every item's quote is verified word for word, and items whose quote failed were dropped (listed in `dropped_unverified`). Sizes range from 27 items (Texas, built first with an earlier multi-turn version of the checklist step) to 231 (Missouri, whose rules also cover group homes). |
| `handbook_eval/<STATE>/` | The planted-defect test: `clean.md` (a fictional, compliant handbook), `defects.json` (5 rule-breaking sentences and 3 deleted policies, each tied to a checklist item and its rule), `defective.md` (the clean handbook with the defects applied). |
| `results/inspector/` | Every inspector run on those handbooks: findings, quotes, scores, tokens and cost. |
| `data/items.jsonl` | 428 questions on 15 states' rules with a checked answer key: 356 rule lookups (answer, verified quote, page, section), 42 inspection checks and 30 questions about made-up section numbers. |
| `results/*-low.jsonl` | Every Beam answer to those questions in three setups, graded, with tokens and cost. |

## How the inspector uses Beam

1. **Checklists, once per state.** Beam reads the state's whole rulebook in one context (up to about 210k tokens) and lists the requirements, each with a quote that is then verified.
2. **Inspection, per upload.** One Beam call per state with the checklist, the rulebook pages it cites plus the pages most relevant to the handbook (BM25), and the handbook. Beam returns a status for every checklist item, the exact rule clause a conflicting sentence breaks, and suggested wording. Very long checklists are split across parallel calls.
3. **Verification.** Handbook quotes are checked against the handbook, rule quotes against the official text, and section numbers against the rule's page. A finding that can't be proven is shown as "check by hand" or not at all.

Sending only the relevant pages instead of the whole rulebook used 2 to 5.5 times fewer input tokens per state and cost 2.4 times less on the planted-defect test, with the same planted mistakes found (see the comparison table above).

## How quotes are checked

A quote passes if it appears in the document word for word, ignoring case, punctuation, hyphens, spaces, line breaks and Texas's printed rule weights ("[Medium-High]"). It must start and end on whole words ("attended" never matches inside "unattended"), and needs at least 6 words with one fragment of 4 or more, so a bare table cell can't pass on its own. In the inspector, "..." may skip at most about 60 words between fragments, and a short skip may not drop a negation ("not", "never", "unless"...). A short table row ("0 – 11 months 4") counts only on the page of the checklist rule it belongs to. A conflict whose rule words come from a state's guidance (Texas "Technical Assistance" boxes, California "Handbook" text) is shown as "check by hand", not as a broken rule. The question benchmark keeps its published rules (fragments within 3,000 characters). Number answers must contain the number.

## Use as an RL environment

`carerules/env.py` in the [code repository](https://github.com/BackPR/carerules) (`from carerules.env import tasks, reward`) gives one task per question and a reward from the same checker: 1.0 for a right answer with a real quote that backs it, 0.3 for a right answer without one, 0 for a wrong answer, and −0.5 for any quote that isn't in the rules.

## Limits

- The question answer key and the eval handbooks were written with AI help and checked mechanically; ratio and group-size answers were also compared with BackPR's separately researched state summaries (one disagreement, which showed BackPR's summary was wrong and is now fixed). Not a lawyer's review.
- Quote checks prove a quote is real, not that the model read it correctly. In development, Beam once called text-message permission for medicine forbidden in Texas, where the rule allows electronic permission and limits phone permission to one dose; the prompt now requires each conflict to follow from the exact rule words quoted.
- Rules change; these are the versions downloaded on October 28, 2026. Some sources mix rules with guidance or cover several program types; Word and web sources have no fixed pages, so their "pages" are about 3,000-character chunks.
- 22 states and DC (Arkansas's rules are for out-of-school-time facilities): Hawaii's PDF is a scanned image, and New York, Ohio, Massachusetts, Arizona, Maine, New Hampshire and Tennessee blocked automated downloads; other states weren't attempted yet.
- Not legal advice. The handbooks are fictional.

## License and credits

Checklists, questions, eval handbooks and results: CC BY 4.0; code: Apache 2.0. The rule texts in `rulebooks/` are official government documents, each downloaded once from the official URL in `rulebooks/sources.json`; their publishers' terms apply, not CC BY (Pennsylvania, for example, prints a copyright notice on its rule pages). Please don't use them to train models, and check each source's terms before reusing them. Rights holders: email hi@backpr.com or open a discussion and we'll remove the text. Full list: `CREDITS.md`. Rulebook links come from [BackPR's open data](https://huggingface.co/datasets/backpr/us-youth-program-data) (CC BY 4.0). Model: [Beam 1.0](https://huggingface.co/reflection/Beam-1.0-501B-A23B) by Reflection. Individual entry by MohammadMahdi RezaAli to the Build with Beam challenge. Made by [BackPR](https://backpr.com).
