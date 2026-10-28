# CareRules

**Does a child care center's parent handbook break its state's licensing rules?** Upload the handbook; Beam 1.0 reads it with each state's official licensing rules and returns a score, the sentences that break a rule, the required policies that are missing, and new wording to paste in. Every quote, from the handbook and from the rules, is checked word for word by a plain program before it's shown; anything it can't confirm is marked "check by hand".

- **Try it:** the [Hugging Face Space](https://huggingface.co/spaces/backpr/carerules-inspector) or [care.backpr.com](https://care.backpr.com). Sample handbooks can be checked live with no code.
- **Data, checklists, eval handbooks and every run:** [backpr/carerules](https://huggingface.co/datasets/backpr/carerules)
- **Model:** [Beam 1.0](https://huggingface.co/reflection/Beam-1.0-501B-A23B) by Reflection, through Hugging Face Inference Providers

22 states and DC, 1,819,794 tokens of official rules (Beam's tokenizer), downloaded from official state sources on October 28, 2026. Arkansas's rules cover out-of-school-time facilities only.

## Results

{{RESULTS}}

## Layout

| Path | What it is |
|---|---|
| `static/` | The page: `engine.js` reads the handbook, picks the rule pages (BM25), builds the prompt, checks every quote and section, scores and renders the report, all in the browser; `app.js` runs the page. Served as a free static Hugging Face Space. |
| `worker/` | The only server part: a Cloudflare Worker that keeps the Beam token secret, checks access codes, accepts only inspection prompts, keeps spending inside hard dollar limits (a Durable Object, so parallel calls can't slip past them) and caches replies for 7 days. |
| `carerules/checklist.py` | Beam compiles each state's checklist from the whole rulebook; every quote verified |
| `carerules/audit.py` | The inspection: focused context (checklist pages + BM25 pages for the handbook), one Beam call per state (split when the checklist is long), then quote, clause and section verification and the score |
| `carerules/corpus.py` | Rulebook pages, the word-for-word quote checker (whole words, no negation-dropping "...", table rows only on their rule's page, guidance detection), BM25 |
| `carerules/document.py` | Reads PDF, Word and text handbooks into pages |
| `carerules/view.py` | The report (HTML) and the fix list (Markdown) |
| `carerules/run.py`, `grade.py`, `agent.py`, `env.py` | The 428-question benchmark: three setups reported (memory only, whole rulebook, agent; a fourth, several states' rules in one ~1M-token context, is built but not yet run), grading, the search/read/check agent, and the RL reward |
| `carerules/beam.py` | Minimal client for Beam through Hugging Face, with a hard spending cap |
| `data/` | Sources, checklists, the question answer key |
| `samples/` | The sample handbook and report, and the 8 planted-defect handbooks |

## Run it

```bash
python3 -I scripts/selftest.py                          # the question answer key graded against itself: 0 problems expected
python3 -I scripts/reassemble.py && python3 -I scripts/parity.py   # re-check every saved answer; browser engine = Python (needs Node)
HF_TOKEN=hf_... python3 -I scripts/eval_inspector.py TX # planted-defect test for one state (about 3 cents)
HF_TOKEN=hf_... CARERULES_CONTEXT=full python3 -I scripts/eval_inspector.py FL NC NJ OR TX  # whole-rulebook arm (about $0.56)
HF_TOKEN=hf_... python3 -I scripts/run.py doc --effort low # the 428 questions with the whole rulebook (about $0.65)
python3 -I scripts/report.py && python3 -I scripts/results.py  # rebuild the tables in results/RESULTS.md from saved runs
HF_TOKEN=hf_... python3 -I scripts/checklist.py TX      # rebuild a state's checklist (about 5 to 15 cents)
python3 -I scripts/stage.py && python3 -m http.server -d build/site   # the page locally
```

Benchmark scripts stop at `CARERULES_BUDGET` dollars (default 13), tracked in `results/spend.jsonl`. The Python package needs only the standard library; the page loads pdf.js and mammoth from cdnjs to read PDF and Word files.

## Limits

Quote checks prove a quote is real, not that it was read correctly; the answer key and eval handbooks were written with AI help and checked mechanically, not by a lawyer. Rules change. Not legal advice. Code: Apache 2.0 ([LICENSE](LICENSE)). Our data: CC BY 4.0. The state rule texts in `text/` are official government documents under their publishers' terms, not ours, and the photos, fonts and the BackPR name and logo have their own licenses: see [CREDITS.md](CREDITS.md). Individual entry by MohammadMahdi RezaAli to the Build with Beam challenge. Made by [BackPR](https://backpr.com).
