# Samay — a court day that runs to plan

**PUCAR "Scheduling Justice" hackathon · FOSS United Week · 24 September 2026**  
**Team:** samay · **Members:** Gaurav (Guruprasad) Meena, _add teammates_ · **Level claimed:** L3  
**Code:** `submissions/samay/` on branch `team-samay` · **Run it:** `pip install -r requirements.txt && streamlit run app.py`

---

## 1. The problem in one line

A cheque-bounce (s.138 NI Act) judge lists ~60 cases a day, reaches about a third, and only ~9 hearings actually move a case forward; the rest are adjourned and handed a flat 60-day date. Old cases wait, litigants make wasted trips, and nobody knows when their case will be called.

## 2. What Samay does

Every evening, for one judge, Samay decides **which** cases to list tomorrow, **in which sitting and at what time**, and **the next date** for every case that does not move — using only the court's own data.

| Step | What happens | Where |
|---|---|---|
| 1. Intake | Court master uploads the judge's docket (Excel/CSV). Header spellings, dd/mm dates, blank or duplicate rows and multi-sheet workbooks are handled; wrong files get a clear message. | `src/intake.py` |
| 2. Read every case | The last order is read: what happened, what the case is waiting on, who was absent, "last chance", first vs repeat hearing at this stage. | `src/orders.py`, `src/model.py` |
| 3. Score 0–100 | The team's **Case Priority Scoring** algorithm, implemented exactly (section 3). | `src/score100.py` |
| 4. Hold back | Cases whose summons / warrant / notice is still out are **Conditional** and not listed (rule R1). | `src/model.py` |
| 5. Build the day | Bail first (liberty lane) → cases overdue 30+ days → a protected share for 4+ year cases → the rest by **score × P(moves forward)^1.5 ÷ expected minutes**, packed into 10:45–12:30 and 13:30–17:00 with a 2-min changeover and a start time per case. | `src/priority.py`, `src/packer.py` |
| 6. Readiness check | Two days before, advocates confirm; "need time" frees the slot for the next case — no wasted trip. | `src/simulate.py` |
| 7. Next date | By *why* it didn't move: court didn't sit → next sitting day; party absent → sooner; summons pending → when it's expected back. Never a flat 60 days. Holidays and the judge's leave respected. | `src/next_date.py` |
| 8. Judge approves | Judge sees the list, removes or adds cases, approves; the causelist downloads. | `ui_pages/judge.py` |

## 3. Case priority score — exactly as specified

```
Priority = 35 × age_value + 25 × readiness_value + 15 × disposal_value + 15 × churn_value + 10 × urgency_value
```

- **Age** — years since filing ÷ full-points age (mean + 2 sd of the roster = **8 years**, fixed once).
- **Readiness** — P(hearing of this type makes progress) from `substantiveness_by_hearing_type.csv` × attendance factor (0.7–1.0 from who the hearing needs vs who was present).
- **Disposal proximity** — position of the current stage in the 11-stage lifecycle.
- **Churn** — hearings held ÷ median hearings expected by this stage (`hearing_type_reference.csv`), full points at 2×.
- **Urgency** — "last chance" 1.0, "for judgment" 0.8.

Rules beside the score: R1 Eligible/Conditional, R2 age weight never below 20, R3 bail liberty lane, R4 Backlog 4y+ / Ageing 5y+ flags, R7 no case waits forever (overdue forced in).

**Verified on the real data:** on all 100 cases in `roster_sample_100.csv`, Samay reproduces the document's score, status and flags for **100 / 100 cases** (range 7.2–91.3, mean 37.7, median 35.2; 80 Eligible, 20 Conditional). Example: ST/1261/2017 = 35.0 + 25.0 + 13.5 + 9.8 + 8.0 = **91.3**.

## 4. Results (60 sitting days from 24 Sep 2026, same simulator for both)

**On the real 100 cases** (`data/roster_sample_100.csv`):

| | Today's court | Samay |
|---|---:|---:|
| Listed cases reached | 49% | **97%** |
| Heard hearings that move the case | 63% | **91%** |
| Hearings that move a case, per day | 0.5 | **4.3** |
| 4+ year cases heard at least once | 30% | **87%** |
| 5+ year cases moved a stage | 13% | **73%** |
| Started within 30 min of the slot | 12% | **81%** |
| Next date sensible for the case | 12% | **90%** |
| Cases disposed | 5 | **54** |

**At the case study's scale** (3,000 cases resampled from the real 100):

| | Today's court | Samay |
|---|---:|---:|
| Listed per day | 60 | **21** |
| Hearings that move a case, per day | 8.8 | **14.2** (+62%) |
| Listed cases reached | 35% | **86%** |
| Wasted trips in 60 days | 2,856 | **378** (−87%) |
| 5+ year cases moved a stage | 12% | **43%** |
| Cases disposed | 135 | **437** (3.2×) |

Fewer listings, far more progress: Samay lists what is ready and fits, instead of listing everything and adjourning most of it.

## 5. The prototype (one command: `streamlit run app.py`)

- **Sign in** as a judge or the court master.
- **Judge:** *Today* (timeline + causelist with time, listing number, score, why listed; remove/approve/download) · *Calendar* (month view, holidays, leave) · *Cases* (score, status, flags, last order, journey) · *Priority* (re-weight live; age floor 20) · *Insight* (Samay vs today's rules) · *How Samay decides*.
- **Court master:** *Judges* (each bench's numbers) · *Files* (upload a docket, set leave) · *Run a day* (record outcomes; next date follows the rule) · *New complaint* (s.138 limitation and papers check before listing).
- **Analytics dashboard:** what-if levers, three judges' rules compared, why hearings fail, advocates (L3), rankers.

## 6. Complexity: L3

- **L2:** sampled durations, start times and changeovers; per-type outcome and failure-reason distributions; prerequisites that change over time; per-case attendance and preparedness.
- **L3:** each advocate is an agent (diligent / overloaded / dilatory) who learns from the court's incentives (reminders, cost for on-the-day adjournment) — see *Advocates (L3)* and `agents_study.py`.

## 7. Data and honesty

- Only the organisers' files in `data/` are used: roster, hearing reference, substantiveness, failure reasons, court calendar. No invented cases in the prototype — the judge's default docket is the real 100 cases.
- The 3,000-case run resamples the real 100 (`scripts/generate_roster.py`) only to show scale.
- Fixed rules (0.7–1.0 attendance range, "last chance" = 1.0, 30-day overdue, 2-min changeover, 10:30–11:00 start, lunch 12:30–13:30) are named constants, documented in `case_priority_scoring.md` and `src/config.py`.
- Limits: one case type (s.138), one judge at a time, simulated outcomes (not yet validated on live court results).

## 8. Repository

`app.py` (entry) · `ui_pages/` (sign-in, judge, court master, dashboard) · `src/` (engine: intake, orders, model, score100, priority, packer, simulate, next_date, agents, metrics) · `tests/` (8 passing) · `samples/` (Excel template) · `results.md`, `rankers.md`.
