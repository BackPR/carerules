### Handbook Inspector: planted-defect test (Beam 1.0, low effort, relevant rule pages)

Eight realistic, fictional handbooks (one per state, about 2,500 words each) were written to cover every required policy. Then 5 sentences were swapped for versions that break a specific rule, and 3 required policies were deleted. Each handbook was checked in both versions. Planted mistakes are easier to find than real ones.

| State | Planted conflicts flagged | Deleted policies caught | Conflicts claimed on the compliant handbook | Score: compliant → planted | Cost (both checks) |
|---|---|---|---|---|---|
| California | 5/5 | 3/3 | 1 | 72 → 45 | $0.135 |
| Florida | 5/5 | 3/3 | 1 | 95 → 52 | $0.048 |
| Illinois | 5/5 | 3/3 | 0 | 98 → 65 | $0.051 |
| New Jersey | 5/5 | 3/3 | 1 | 95 → 56 | $0.051 |
| North Carolina | 5/5 | 3/3 | 0 | 100 → 60 | $0.062 |
| Oregon | 5/5 | 3/3 | 0 | 100 → 57 | $0.043 |
| Pennsylvania | 5/5 | 3/3 | 0 | 100 → 32 | $0.072 |
| Texas | 5/5 | 3/3 | 0 | 100 → 54 | $0.030 |
| **All 8** | **40/40** (40 on the exact checklist item) | **24/24** | **3** in 8 handbooks | | **$0.49** for 16 checks |

Of the 3 conflicts claimed on compliant handbooks, 2 were real gaps the handbook writer missed (Florida: an allergy list posted where parents can see it, which the rule forbids; California: the 15-minute infant sleep check must also record breathing, signs of distress and sleep position) and 1 was a misreading (New Jersey: the two-staff-in-the-building rule read as a nap-room ratio). California's compliant score is lower because its rules also cover programs this handbook doesn't run (school-age and mildly ill care).

Each planted defect maps to an item on the state's checklist, so this test measures the inspection, not whether the checklist is complete. Checklist items whose quote failed verification were dropped and are listed in each checklist's `dropped_unverified` (for example two of Virginia's ratio and group-size items).

### Whole rulebook or relevant pages? (5 states, same handbooks)

Beam 1.0 can read a state's whole rulebook in one call. The live tool sends the checklist's pages plus the pages that best match the handbook instead, because on this test it found the same planted mistakes for less than half the cost. With the whole rulebook it claimed no conflicts on the compliant handbooks: it avoided the New Jersey misreading, but it also missed the real Florida gap (an allergy list posted where parents can see it).

| Context sent to Beam | Planted conflicts flagged | Deleted policies caught | Conflicts claimed on compliant handbooks | Cost |
|---|---|---|---|---|
| Whole rulebook | 25/25 | 15/15 | 0 | $0.56 |
| Relevant pages (live tool) | 25/25 | 15/15 | 2 | $0.23 |

Relevant pages used 2.0 to 5.5 times fewer input tokens per state (Florida 2.2x, New Jersey 2.0x, North Carolina 3.5x, Oregon 2.3x, Texas 5.5x).

### Reasoning effort: Standard (low) vs Extra thorough (high), 8 states

| Effort | Planted conflicts flagged | Deleted policies caught | Conflicts claimed on compliant handbooks | Cost | Slowest check, average |
|---|---|---|---|---|---|
| Standard (low) | 40/40 | 24/24 | 3 | $0.49 | 17 s |
| Extra thorough (high) | 40/40 | 24/24 | 6 | $0.84 | 44 s |

Both efforts found every planted mistake. On the compliant handbooks we read each claimed conflict by hand. Standard's 3: 2 real (Florida's allergy list, California's sleep-check log) and 1 misreading (New Jersey). Extra thorough's 6: 3 real (California's sleep-check log; Illinois's "Tdap ... vaccination or immunity", where the rule says no test replaces Tdap; Oregon's center is open 11 hours, so preschoolers need 90 minutes of active play, not 60), 2 misreadings (New Jersey again, and Illinois rest time, which follows Section 407.350) and 1 debatable (California infant sleep position). So Extra thorough found two real problems Standard missed, raised more false alarms and cost more; the live tool defaults to Standard.

### One real handbook

One licensed Texas child care center's published family handbook (85-page PDF, about 30,600 words), checked at Standard effort. The center isn't named and no handbook text is published; each finding was read against the rule by hand (not by a lawyer).

Result: score 67/100, 7 findings, 75,499 tokens in, 14 seconds, $0.04. Our reading of each finding: 1 correct, 1 reasonable, 1 worth checking, 2 depend on facts outside the handbook, 1 debatable, 1 misreading.

| Finding | Rule | Our reading |
|---|---|---|
| breaks a rule: Parents may visit the center during hours of operation without prior approval to observe their child and program. | §746.201(7), page 19 | **debatable**: The handbook lets staff deny entry to a parent who poses a risk; the rule lists no exception, but a safety exception is common sense. |
| missing: If the center does not carry required liability insurance, parents must be notified in writing before admission. | §746.207(a), page 21 | **depends on facts outside the handbook**: The handbook says the center (a state agency) can't buy insurance coverage; if it carries no liability insurance, parents must be told in writing before admission, which could be a separate form. |
| incomplete: If applicable, the handbook must state transportation and water activity procedures. | §746.501(a)(14)-(15), page 33 | **reasonable**: Swim lessons and splash days are described, but there is no clear transportation or water-activity procedure section. |
| check by hand: The handbook must state parent rights consistent with Division 5 of Subchapter B. | §746.501(a)(20), page 33 | **worth checking**: Flagged as check by hand; the handbook has a short parent-rights section worth comparing with the full list of rights. |
| breaks a rule: Children's records must be immediately accessible to caregivers during hours of operation for emergency use. | §746.601(a), page 40 | **depends on facts outside the handbook**: Records 'locked in an administrator's office' may not be immediately accessible to caregivers in an emergency, as the rule requires. |
| incomplete: A food allergy emergency plan is required for each child with a health-care-professional-diagnosed food allergy. | §746.3819, page 218 | **correct**: The rule requires the plan to be signed and dated by the child's health-care professional and parent; the handbook's allergy policy doesn't say so. |
| breaks a rule: Immunization exemptions not addressed | page 45 | **misreading**: The quoted rule is about keeping immunization records, including exemptions; it doesn't require admitting unvaccinated children. |

### Whole rulebook vs memory vs search: 428 questions on 15 states' rules

The same questions in three setups: no rulebook (memory only), each state's whole rulebook in one context, and an agent that searches the rulebook, reads pages and checks its own quotes.

| Setup | Effort | Questions | Right answer | Right, with a real quote | Quotes not in the rulebook | Cost |
|---|---|---|---|---|---|---|
| No rulebook (memory only) | low | 428 | 57.2% | **0.0%** | 100.0% | $0.06 |
| Whole state rulebook in context | low | 428 | 99.8% | **80.4%** | 20.6% | $0.65 |
| Agent: search, read, check quote | low | 428 | 85.5% | **81.8%** | 0.9% | $4.73 |

Right answer: matches the answer key. Right, with a real quote: the answer is right and its quote appears word for word in the official rules (for a number, the quote must contain it).

Quotes not in the rulebook counts the answers that gave a quote: 15 of 428 from memory (asked for no quote without the rules; none of the 15 appears in the rules), 398 with the whole rulebook (82 didn't match; 72 of those contain numbers, mostly table rows, and 42 stitch table cells together with "..."), and 337 for the agent (3 didn't match).

Whole rulebook: each state's questions were asked together, up to 25 per call, so per-question tokens and cost are that call's share. All runs here use low reasoning effort ("Standard"); the sample report on the page used high ("Extra thorough").
