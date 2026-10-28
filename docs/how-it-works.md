### What this is

Childcare centers in the US are licensed by their state, and each state's rulebook runs from 20 to 370 pages. Directors, inspectors and parents ask the same questions every day: how many four-year-olds can one teacher supervise, how hot can the water be at the sinks, how long do we keep attendance records. A wrong answer from an AI looks exactly like a right one.

CareRules makes every answer checkable. Beam answers from the official rulebook and must quote the rule. A plain program (no AI) then checks that the quote appears word for word in the official text and links to the page, so a person can confirm it in seconds.

### How an answer is made

1. **Search.** Beam searches the state's rulebook (BM25 over every page of the official PDF text).
2. **Read.** It opens the pages it needs.
3. **Check.** Before answering, it checks its own quote with the same word-for-word checker and fixes it if it isn't found.
4. **Verify again.** The app checks the final quote independently and shows ✅ with a link to the PDF page, or ⛔ if the quote isn't in the rulebook.

The checker ignores case, punctuation, hyphens, spaces and line breaks, and allows "..." to skip text between fragments that appear in order. A quote needs at least 6 words, with one fragment of 4 or more, so a bare table cell can't pass. Nothing else is fuzzy.

### The benchmark

The answer key has the same 20 topics for each state (ratios, group sizes, staff age, director qualifications, training hours, indoor and outdoor space, hot water, medication, fire drills, records, safe sleep, injury reports, immunizations, CPR, crib spacing, license term) plus up to 5 harder questions per state (exceptions, nap-time and field-trip ratios, mixed ages). Every key answer has a word-for-word quote that passes the checker, and the rulebook's page and section. Two more kinds of questions are generated from the key:

- **Inspection checks:** "one classroom has 36 four-year-olds and 2 caregivers: does it meet the ratio and group size?", set right at the limit.
- **Made-up section numbers:** questions about rule numbers that don't exist. The right answer is to say so.

Beam is tested four ways:

| Setup | What Beam gets |
|---|---|
| No rulebook | The question only. Shows what it "knows", and how often it invents quotes. |
| Whole state rulebook | One state's full rulebook (20k–250k tokens) with that state's questions. |
| Many rulebooks, ~1M tokens | Several states' rulebooks in one context. The right rule sits among look-alike rules from other states. |
| Agent | Tools to search, read pages and check quotes, one question at a time. |

A **verified** answer is right *and* comes with a real quote that backs it (for numbers, the number must be in the quote).

### Honest limits

- The answer key was written with AI help and checked mechanically: every quote is in the official text and every number answer is in its quote. Ratio and group-size answers were compared with BackPR's separately researched state summaries. They agreed everywhere except one row, where the rule text showed BackPR's summary was wrong (Iowa, ages 10 and over); that's now fixed. It's not a lawyer's review.
- Rulebooks were downloaded from official state URLs on October 28, 2026 and change over time. Some PDFs mix rules with guidance boxes or other program types; questions name the facility type they apply to.
- 15 states, not 50: Hawaii's PDF is a scanned image, and three states blocked automated downloads.
- This is not legal advice.

### Credits

Rulebook links and the state summaries used for cross-checking come from [BackPR's open data](https://huggingface.co/datasets/backpr/us-youth-program-data) (CC BY 4.0). Model: [Beam 1.0](https://huggingface.co/reflection/Beam-1.0-501B-A23B) by Reflection, through Hugging Face Inference Providers.
