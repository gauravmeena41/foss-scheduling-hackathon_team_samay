# Demo — 10 minutes

Before: `streamlit run app.py`, roster 1,000, 60 days, preset Recommended, agents on. Open tabs once so they're cached.

| Min | Show | Say |
|---|---|---|
| 0:00–1:00 | Title + KPI row | "A typical day lists 60, reaches 20, moves 10. Our simulator reproduces that baseline from your data — that's our calibration check. Same docket under Samay: ~45 listed, ~27 heard, ~26 move forward." |
| 1:00–2:30 | Today's causelist | "Every case has a slot and a start time; each advocate's matters sit together; every row says why it's listed." Untick 3 cases → expected minutes / P(everyone reached) change. "This is how a court master overbooks with numbers instead of instinct." |
| 2:30–4:00 | Case brief tab, pick a 10-year-old part-heard matter | Aditi's question: "The prerequisite check helps early stages. Evidence and arguments fail for a different reason — nobody remembers the case. So every old or late-stage case gets a one-page brief: journey, last order, who was absent, what it's waiting on, what must be ready." Then the stage table from SUBMISSION §5: gate fixes early, brief + readiness check move the late stages. |
| 4:00–5:30 | Three judges tab | "Same engine, three judges' rules." Joshi without the guardrail: most hearings per day, 0% of 5+ year cases moved. With it: a floor under the old backlog. "Judges configure everything except this." |
| 5:30–7:00 | Advocates (L3) + sidebar toggles | Turn the on-the-day adjournment cost off/on: on-the-day "not prepared" drops, early admissions rise. "Advocates are agents: they decide whether to turn up, be ready, or own up two days early — and they learn from what it cost them last time." |
| 7:00–8:00 | Backlog & drift | Open 5+ year cases falling faster than baseline; hearing-hours left vs court hours: "3,000 cases can't be cleared in 60 days by anyone — so we measure movement and the old backlog, not 'cases cleared'." |
| 8:00–9:00 | SUBMISSION §6 | "Input is DRISTI's roster and order text as-is; output is a causelist CSV; one nightly call. The order-sheet classifier already reads real order text." |
| 9:00–10:00 | Close | "Assumptions are named constants and listed in the write-up. Next: calibrate on real DRISTI order sheets and run the readiness check over WhatsApp." |

Likely questions:
- *Where do the brief's effects come from?* Stated assumption (halves "not prepared", saves 20% time); the ablation shows the result is robust in direction, and it's the first thing to measure in a live court.
- *Is the 3,000 roster real?* Bootstrap of the 100 real-shape cases; advocate IDs redrawn, so clustering at 3,000 is synthetic — said in the write-up.
- *Why greedy, not a solver?* Explainability: every listing carries a reason a judge can read. A solver is listed as next step for multi-court conflicts.
