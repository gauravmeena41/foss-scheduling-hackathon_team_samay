# Demo — 10 minutes

Before: `streamlit run app.py`, roster 1,000, 60 days, preset Recommended, agents on. Open tabs once so they're cached.

| Min | Show | Say |
|---|---|---|
| 0:00–1:00 | Title + KPI row (sample docket, 3,000 cases) | "One judge, cheque-bounce cases, the court's real day: start 10:30–11, lunch 12:30–1:30, rise at 5, two minutes between hearings. Today's court lists 60, reaches ~12, moves ~8 — our simulator reproduces that from your data. Samay: ~23 listed, ~17 heard, ~16 move forward, and a seventh of the wasted trips." |
| 1:00–2:30 | Sidebar → Upload Excel / CSV → `samples/sample_docket_3000.xlsx` (a 3,000-case docket; `sample_cases.xlsx` is the 100-row template); Workflow tab | "The court master uploads the cases. Samay validates them, reads every last order, holds back what's waiting on a summons, mediation or a higher court, ranks the rest and lists tomorrow." Point at before/after and the 'why listed' column ("first at stage" / "repeat #4"). |
| 2:30–3:30 | Calendar tab | "Tomorrow as time blocks — fresh matters before lunch, oldest after. Below, the same day simulated: late start, changeovers, lunch as a hard break, what moved and what didn't." |
| 3:30–4:30 | Why hearings fail | "Adjournments aren't one thing — accused absent, sought time, summons not back, court didn't sit. Each gets a different next date: court-side → tomorrow, absence → sooner, summons → when it's back." |
| 4:30–5:30 | Case brief (10-year-old part-heard matter) | Aditi's point: "Later stages fail because nobody remembers the case — so every old or late-stage case gets a one-page brief." Stage table: gate fixes early, brief + readiness check move the late stages and the 5+ backlog. |
| 5:30–6:30 | Three judges; sidebar personal leave | Joshi without the guardrail: most hearings, 0% of 5+ year cases moved; with it, a floor. Add a leave day → everything re-plans around it. |
| 6:30–7:30 | Advocates (L3) + adjournment-cost toggle | "Advocates are agents: they decide whether to turn up, be ready, or own up two days early — and learn from what it cost them." |
| 7:30–9:00 | SUBMISSION §6 | "Input is DRISTI's roster and order text as-is, Excel or CSV; output a causelist CSV; one nightly call per judge. The classifier already reads real order text." |
| 9:00–10:00 | Close | "Assumptions are named constants in the write-up. Next: calibrate on real order sheets and run the readiness check over WhatsApp." |

Likely questions:
- *Where do the brief's effects come from?* Stated assumption (halves "not prepared", saves 20% time); the ablation shows the result is robust in direction, and it's the first thing to measure in a live court.
- *Is the 3,000 roster real?* Bootstrap of the 100 real-shape cases; advocate IDs redrawn, so clustering at 3,000 is synthetic — said in the write-up.
- *Why greedy, not a solver?* Explainability: every listing carries a reason a judge can read. A solver is listed as next step for multi-court conflicts.
