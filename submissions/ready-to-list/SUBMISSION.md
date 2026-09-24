# Submission: ready-to-list

Product name: **Samay**. Team and folder name: ready-to-list.

## 1. Team

- **Team / solo name:** ready-to-list
- **Members:** Pranav (add teammates here)
- **Complexity level claimed:** L3

## 2. One-line summary

List only the hearings that will actually happen and move the case forward, pack them into the judge's day with a constraint solver, give every advocate a real time window, and set the next date from what the case needs, never a flat 60 days.

## 3. The approach

**In plain language.** Every evening the scheduler looks at the cases due and asks three questions. Is this case ready: has its summons or warrant come back, and did counsel confirm? How likely is the hearing to be substantive, given its hearing type and what happened last time? How many minutes will it take? Ready cases are packed into the next day's two sittings (10:30-12:30 and 13:30-17:00), best value per minute first. Bail goes first and 25% of each day is locked for 4+ year cases. Cases of the same type and the same advocate are grouped, so the judge switches context less and advocates make one trip. After each hearing, the next date comes from the next purpose's reference gap, or from the failure reason (a warrant not back: when it is due back).

**Inputs used (all six files):**

| File | How it is used |
|---|---|
| `roster_sample_100.csv` | The cases. Scaled to 3,000 with your own `scripts/generate_roster.py`. `last_hearing_summary` is read for signals: who was absent, what is awaited ("Await warrant", "not ready", "last chance") |
| `court_calendar.csv` | Working days for the simulation and for next dates |
| `hearing_type_reference.csv` | Minutes per hearing type, and the gap to the next hearing for each purpose |
| `substantiveness_by_hearing_type.csv` | The real probability each type moves the case forward: the truth model is calibrated to it |
| `hearing_failure_reasons.csv` | Why hearings fail, grouped into process (summons/warrant not back), absence, not ready, court, unclear. Each group is a different lever |
| `sample_causelist_2026-09-22.csv` | Used as the shape of today's cause list (baseline lists about 60 a day) |

**Core logic (`core/pucar_engine.py`):**

1. **Truth model.** A hearing of type T is substantive with the real probability p(T). If not, it fails for a reason drawn from the real reason mix for T. "Awaiting process" is a state that persists until the process comes back, not a coin flip. The last hearing's note raises the matching risk (x2.5), normalised so each type's average stays at the real rate. Check: under today's rules, with nothing tuned to match, the model gives 57 listed, 25 reached and 12.0 substantive a day, close to the case study's 60 / 20 / 10.
2. **Readiness levers:**
   - **Process tracking:** list a case only once its summons or warrant is back (status known 90% of the time).
   - **T-2 intent check:** half of the "not ready" failures surface before listing.
   - **Fixed slot and advocate clustering:** a third fewer absences.
   - **Reading the last hearing's note** when ranking.
3. **Priority score.** Every case gets a Samay score from 0 to 100 on its own details only: case age 35 points (full at 8 years, computed once per roster as mean plus two standard deviations), hearing readiness 25 (the type's real progress rate, reduced by at most 30 percent for absent required people), disposal proximity 15 (position in the 11 stages), hearing churn 15 (hearings held against the median expected by that stage), court-set urgency 10 ("last chance", "for judgment"). Rules beside the score, never in it: Conditional status when a summons or warrant is out, the liberty lane for bail, 4+ and 5+ year flags, age weight never below 20 percent. Full specification with worked examples: `docs/PRIORITY_SCORE.md`; code: `core/priority.py`.
4. **Optimiser.** CP-SAT knapsack per sitting. Value = Samay score x P(substantive) x minutes^0.75, so the ratio per minute favours likely, short hearings without starving long arguments and judgments. Capacity is 95% of the net minutes, with a same-day waitlist. Bail goes first; the ageing quota is locked.
5. **Next date:** after a substantive hearing, the reference gap for the next purpose. After a failure, the gap for its reason: process 21 days or when it is due back, absence 7, not ready 10.

**Nothing here runs on dummy data.** Every screen, number and rule uses your six files: the 100 real cases (scaled with your generator when a full docket is needed), your hearing-type table, your substantiveness and failure-reason rates, your calendar and your sample cause list. An earlier High Court version on synthetic data was removed from the product and is not part of this submission.

**Key decisions:**
- **Calibrate to your rates.** The baseline must reproduce your substantive rates before any claim about improvement means anything.
- **Treat "awaiting process" as state, not luck.** It is the largest preventable failure: 67% of failed WARRANT hearings and 51% of failed ADMISSION hearings.
- **Score per minute, not per case.** A 30-minute evidence hearing and a 5-minute admission compete fairly.
- **Lock the ageing quota and bail-first.** Judges can configure everything else.

**Assumptions (explicit):**
- **Lever strengths** (process status accuracy 90%, intent check catches half of "not ready", fixed slots remove a third of absences) are assumptions set in `config/pucar.yaml`. The ablation below shows how much each one matters.
- **Minutes** are your estimates x lognormal noise (sigma 0.35). An adjournment costs 2 minutes.
- **Process return time:** a pending process comes back in 3 to 25 working days.
- **Court day:** 10:30-12:30 and 13:30-17:00, which is 330 minutes. We also report the 420-minute day from your README.
- **Initial due dates:** the roster's cases are spread evenly over the horizon.

## 4. Justify your complexity level (L3)

- **L1:** fixed rules: bail first, the ageing quota, the readiness gate, the priority formula (`config/pucar.yaml`).
- **L2:**
  - Distributions: real substantive rates and reason mixes per type, lognormal durations, process-return times.
  - A prediction step: P(substantive) per case from type plus last-note signals.
  - A constraint solver: CP-SAT.
  - Costs: changeovers, the adjournment call.
  - Judge overrides: in the app, the impact meter shows the change in utilisation, predictability and 5+ year cases before approval.
- **L3:**
  - Parties and advocates behave. Their chance of appearing rises with a fixed slot and clustering (35 percent fewer absences), and falls when they are called at short notice from the waitlist. The T-2 confirmation changes what gets listed, and an unready party's answer keeps the case off the list.
  - The court responds to the case's history: the 1st, 2nd and deferred listings of a purpose are treated differently, and a deferred case is held until its last failure is cured.
  - Their decisions feed back: each outcome sets the next date and the next day's plan, and a leave day moves the whole list.
  - The lever strengths are assumptions, stated in `config/pucar.yaml` and tested by switching each lever off.

## 5. Results

**A. The judge's full docket, 60 working days.** 3,000 cases (your generator, seed 42) from 1 Oct 2026, 330 court minutes a day, three of them judge-leave days, averaged over 5 seeds (`outputs/results.md`):

| Metric (case study) | Today's rules | Samay |
|---|---|---|
| Utilisation: court minutes used | 94% | 95% |
| Reach rate: scheduled cases the court gets to | 44% | 97% |
| Substantiveness: reached hearings that move the case | 48% | 79% |
| Backlog-age impact: 4+ year cases heard at least once | 32% | 47% |
| Predictability: days from first listing to the hearing that moved it | 23 | 2 |
| Next-date gap, days | 60 (flat) | 14 (purpose-based) |
| Substantive hearings a day | 12.0 | 13.9 (+16%) |
| Cases disposed in 60 days | 196 | 356 (+82%) |
| Wasted listings (trips for nothing) | 2,694 | 259 (-90%) |

With your 420-minute day (`outputs/capacity_420/`), today against Samay: 15.2 against 17.6 substantive hearings a day, 230 against 465 disposed, substantiveness 47% against 82%.

**Which lever does what** (one switched off at a time, and the halves alone):

| Configuration | Substantive a day | Moves the case | Wasted listings | Disposed |
|---|---|---|---|---|
| Samay, everything on | 13.9 | 79% | 259 | 356 |
| Scheduling only: registry packing and next dates, no party input | 13.1 | 65% | 463 | 329 |
| Scheduling only + fixed slots and clustering | 13.4 | 67% | 439 | 346 |
| Readiness levers only (no optimiser) | 12.9 | 63% | 2,645 | 136 |
| Without reading the last hearing's note | 13.4 | 72% | 335 | 317 |
| Without the pre-filing check | 13.8 | 79% | 263 | 360 |

Scheduling alone, which needs only the registry's own data, delivers most of the disposals; the readiness levers raise how often a heard case moves forward and cut wasted listings further.

**B. One judge for a year, the 100 real cases inside it, new complaints arriving** (`outputs/one_judge_year.md`, 250 working days, 3 seeds, about 2.5 new complaints a day). This is where pre-filing shows: 96 of your 100 cases went through Delay Condonation hearings (3.37 hearings per case, 29% substantive). When the registry computes limitation at e-filing and the condonation petition is heard with admission, new complaints stop stalling there.

| Over a year | Today's rules | Scheduling only | Scheduling + pre-filing | Samay (all) |
|---|---|---|---|---|
| Cases disposed | 541 | 643 | 644 | 847 |
| Of the 100 real cases | 18 | 21 | 21 | 28 |
| New complaints past cognizance within the year | 3% | 32% | 91% | 92% |
| Delay condonation listings | 407 | 290 | 20 | 9 |
| Substantive hearings a day | 12.4 | 13.4 | 12.7 | 14.5 |
| Wasted listings | 11,708 | 3,913 | 3,939 | 1,958 |

**The prototype** (`app.py`): sign in as a judge or as the court master. Justice Sehgal's docket is pre-loaded from this repository's `roster_sample_100.csv`, so the app works the moment it opens. The court master runs several judges from one dashboard: a card per judge with docket size, listings a day, reach, disposals against today's rules and leave, and each judge's next sitting day. Files: add any files or a whole folder (CSV, Excel, JSON, or a ZIP); Samay recognises a docket by its columns and the reference tables (hearing types, substantiveness, failure reasons, calendar) by theirs, replacing the defaults; the required columns and an example of how rows look sit beside the uploader. Run a day: call each matter, record the outcome, the next date follows by rule. New complaint: registry scrutiny at e-filing. The judge sees Today (a timeline of the two sittings and the cause list with time, listing chip, score, advocate and why today; remove, restore, approve), Week (five days side by side), Cases, Priority (five adjustable weights, age never below 20), Insight and How Samay decides (score, model, steps, and every parameter with its value for that judge). Typefaces follow Sanhita: Playfair Display for display, Inter Tight for text. Pages are fixed to the screen; lists scroll in their own frames.

**Listing number.** The data shows the same purpose is listed many times (Warrant 5.0 hearings per case, Evidence complainant 6.8). The prototype tracks how many times a case has been listed for its current purpose: a 1st listing is planned normally; a 2nd listing carries a priority boost and a readiness check; a deferred case (3rd or later) is held until the reason for its last failure is cured (a warrant not back is never relisted blind), then listed with priority and a fixed slot.  Rules in `config/pucar.yaml` under `escalation`.

**Calendar.** Your `court_calendar.csv` is used as given for the scored runs. One finding for you: its holiday names ("Janmashtami (Shravan Vad-8)", Samvatsari, Vikram Samvat New Year) are Gujarat's General Administration Department naming and match the Gujarat Gazette list for 2026, not Kerala's. For the Kerala demo court we also loaded the official High Court of Kerala 2026 calendar (210 sitting days; Sep to Dec holidays: 4 Sep, 21 Sep, 2 Oct, 20 and 21 Oct, 25 Dec; HC non-sitting 19 Oct and 9 Nov; Christmas vacation 24 to 31 Dec; second Saturdays closed) in `config/calendar.yaml`, with the source URL. Note 5 of that calendar says vacations apply to the High Court and civil courts; magistrate courts, where these cheque cases sit, keep sitting.

**Statutory clock.** NI Act s.143(3) asks the court to conclude the trial within six months of filing, with day-to-day hearings under s.143(2). Cases past 180 days get a priority boost (`config/pucar.yaml`, `statutory_clock`).

**Judge leave.** Leave days come from the leave register (`config/pucar.yaml`, `judge_leave`; Kerala Service Rules allow at most 20 casual leave days a year). On a leave day nothing sits. Under today's rules the day's cases take the flat 60-day gap; under Samay they move to the next sitting day with room.

**Upload a docket** (second page): upload the docket file from this repo (`data/roster_sample_100.csv`, or the same columns as an Excel sheet). The app checks the columns and explains any problem in plain words. It then shows what is in the docket, reads each case's readiness from its last hearing note, plans the next week to year with time windows, and compares the results with today's rules. The pitch deck is `docs/presentation.html`: open it in a browser and use the arrow keys.

**Visualisation and workflow** (Streamlit app, page "Justice Sehgal's docket"):
- **The data:** every file and column, with the key findings (`docs/DATA_PROFILE.md`).
- **Registry intake:** the manual scrutiny of an NI Act s.138 complaint as structured e-filing fields. Statutory dates are computed (cheque validity, 30-day notice, 15 days to pay, one month from cause of action), with documents, summons details and jurisdiction (s.225 enquiry). Nothing is refused; the result says what to cure (`config/registry_ni138.yaml`, `core/registry.py`).
- **Lifecycle:** the stage graph derived from your data, with cases now at each stage, P(substantive), minutes and hearings per case.
- **Case file:** each of the 100 real cases, with hearings held per stage, the last note and the signals read from it, and its simulated next year under both approaches.
- **Plan by day, week, month or year:** the cause list with time windows; the week board by hearing type; the month's listed and moved hearings; the year's cumulative disposals and where pending cases stand.

**Against the default.** "Whatever is listed gets attempted, 60-day gap" lists 57 a day and reaches 44% of them. Samay lists about 18, reaches 97%, and hears more of them substantively.

## 6. Specs for integration

- **Input schema:** exactly your CSVs, unchanged. `core/pucar_engine.load(data_dir, roster=...)` reads them. The hearing-type names from your files are normalised to upper case with underscores.
- **Output:** `outputs/proposed_schedule.csv` with columns `date, block, expected_start, window, case_number, hearing_type, advocate_id, from_waitlist, p_substantive_planned, simulated_outcome`, plus `results.csv` and `daily.csv`. `simulated_outcome` exists only in simulation; drop it in production.
- **Scaling to every court and judge:** the unit is one judge's docket. `judge_docket()` builds it, `simulate()` plans it, and each court's rules (sitting blocks, hearing-type flow, priorities, registry checks) live in YAML (`config/pucar.yaml`, `config/registry_ni138.yaml`). Another bench is another docket and config, with no code change. Advocates shared across benches would be handled by a court-wide planning step that never lists one advocate in two courtrooms at once; that is the first thing to add when a second bench comes on.
- **Interfaces:** a Python module (`core/pucar_engine.py`, `core/registry.py`), two CLIs (`scripts/run_pucar.py`, `scripts/run_one_judge.py`) and a Streamlit app (`app.py`). `docs/HOW_IT_WORKS.md` describes the decision, the data, the lifecycle, the model, the optimiser step by step, the calendar, the screens, a production backend with API endpoints, and a stage-by-stage table of every feature.
- **Dependencies:** Python 3.11+, pandas, numpy, OR-Tools (CP-SAT), PyYAML, Streamlit, Plotly, openpyxl, tabulate. No external services and no machine learning trained on this data: the model is your measured rates per hearing type, adjusted per case by signals in the last order, with a CP-SAT solver on top.
- **Stubbed vs real:**
  - Real: the optimiser, the next-date rules, the listing-number rule, judge leave, the registry timeline computation, the calibration to your rates, the ablation, the four screens and the upload flow.
  - Assumptions in config: lever strengths, process-return times, demo leave dates.
  - Simulated: process-return status, confirmations and outcomes. In production they come from DRISTI and the court master.
- **What integration would take:**
  1. Feed process-return status and advocate confirmations from DRISTI.
  2. Map DRISTI hearing purposes to the 14 types.
  3. Run the planner each evening and show the judge the draft list for approval.
  4. Write outcomes back so the models retrain.

## 7. How to run it

```bash
cd submissions/ready-to-list
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# The app: Justice Sehgal's docket is pre-loaded; sign in as Judge or Court master
.venv/bin/streamlit run app.py
# Score on your data (3,000 cases, 60 days, 330-minute day; add --capacity 420 for the README's day)
.venv/bin/python -m scripts.run_pucar --out outputs
# One judge for a year: the 100 real cases inside the docket, new complaints arriving, with and without pre-filing
.venv/bin/python -m scripts.run_one_judge --out outputs
# Profile every data file and column
.venv/bin/python -m scripts.data_profile
```

## 8. What we'd build next

1. Fit lever strengths from real process-status and confirmation data instead of assuming them.
2. Replace keyword signals from the last hearing's note with a small classifier trained on the notes.
3. Learn minutes per hearing from court-master timestamps.
4. A two-way loop with advocates (WhatsApp confirmations) so the intent check is real, not simulated.

---
**Checklist before you open your PR:**
- [x] No real case numbers, party names, or advocate names appear anywhere in this submission. (Case numbers come from your generator; the demo filings are fictional.)
- [x] Everything lives under `submissions/ready-to-list/`.
- [x] This file is filled in, not left as a template.
- [x] Your code actually runs with the commands in section 7.
