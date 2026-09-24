# Submission: samay

> DRAFT — Dev 3 finalises at 4:00 with numbers from the final run.

## 1. Team

- **Team / solo name:** samay
- **Members:** _TODO_
- **Complexity level claimed:** L2 (with an L3-lite advocate agent — see §4)

## 2. One-line summary

Samay lists only the hearings that are ready to happen and likely to move the case forward, packs them into real time slots up to the day's expected capacity, reserves a fixed share of every day for 4+ year cases, and sets each next date by the work the next step needs.

## 3. The approach

- **Inputs:** roster, court calendar, hearing-type reference, substantiveness, hearing-failure reasons. 3,000-case roster from `scripts/generate_roster.py` (bootstrap resample of the 100 — "more of the same mix", advocate IDs redrawn, so advocate clustering at 3,000 is synthetic).
- **Core logic (greedy, explainable):**
  1. *Case model* — normalise each case; parse the last order text for pending process ("Issue NBW", "take steps", summons/notice) and "last chance".
  2. *Rank* — score = age factor × P(moves forward | listed) ÷ expected minutes. Cases whose process hasn't returned aren't eligible (prerequisite gate).
  3. *Pack* — capacity = 420 min × overbooking factor, in **expected** minutes (a no-show costs a 2-min mention, not the full slot). First fill the guardrail share with 4+ yr cases, then the best of the rest. Assign to time blocks, cluster each advocate's matters back to back, give every case an estimated start time.
  4. *Next date* — reference gap for the next purpose, shortened after an absence, set to the process-return date after a process failure, next working day if unreached.
  5. *Readiness check (all stages)* — two days before, advocates of the top candidates confirm "ready" or "need time". Admitted unpreparedness / unavailability frees the slot a day early; the next-best case takes it. Two "need time" answers flag the case as repeatedly adjourned.
  6. *Case brief (middle and late stages)* — a one-page summary per case (journey through the stages, last order, who was absent, what must be done before this hearing) for every 4+ yr or evidence/arguments/judgement case. Modelled as halving "not prepared" failures and cutting 20% of hearing time on those cases (assumptions).
- **Key decisions:** expected-minutes packing (airline-style overbooking); guardrail as a floor the judge can raise but not lower; greedy over a solver so the judge can see *why* each case was listed (`reason` column).
- **Assumptions:** durations lognormal around the reference minutes (σ = 0.35); outcome of a listing drawn from P(substantive) + failure-reason shares per hearing type; once process has returned, process failures drop out and the rest renormalise; process return time ~ Exponential(mean 1.5 × reference gap); substantive hearing advances to the next lifecycle stage (appearance/warrant → plea; side applications return to the main stage); no judge leave unless configured.

- **E-filing signals (optional, synthetic):** `src/efiling.py` adds DRISTI e-filing fields (accused addresses, contact known, prepaid summons rounds + e-post, accused within jurisdiction, ADR opt-in, complainant type) with assumed distributions. They set a per-case process-return multiplier (no contact ×1.6, prepaid + e-post ×0.7, outside jurisdiction ×1.3, each extra address ×0.85) the planner uses for tentative dates. Effect in simulation is small (+0.4 effective hearings/day) — reported as such.
- **Case model:** `src/orders.py` classifies each last order (11 events: process awaiting/served, mediation or higher-court order pending, objections pending, not ready, absent, part-heard, heard for judgment, progressed, verdict recorded) and who the case waits on; this drives the prerequisite gate, readiness, case-level no-show and unpreparedness multipliers, and part-heard priority. Two cases with a verdict already recorded but "Judgement" as next purpose are treated as disposed (data-quality note).

## 4. Justify your complexity level

- **L2:** sampled durations; outcome distributions per hearing type from the failure data; prerequisite readiness that changes over time; overbooking factor, guardrail, clustering, weekly carry-forward, mandatory summaries as rules a judge toggles, with the dashboard showing the impact against the baseline immediately.
- **L3 (behavioural):** `src/agents.py` — every advocate is an agent with a personality (diligent 30% / overloaded 50% / dilatory 20%: how often prepared, how often they turn up, how honest at the readiness check, how often listed in another courtroom the same day). They **decide** whether to appear, whether they're prepared, and whether to admit "need time" two days ahead. The court's policy changes those decisions: a real time slot and clustering cut the clash penalty; reminders raise preparedness; a cost for adjourning *on the day* (admitting early is free) makes dilatory advocates more honest and better prepared. Outcomes **feed back**: an adjournment that cost nothing makes a non-diligent advocate prepare less next time; one that cost something makes them prepare more; a hearing that went ahead on its date raises their trust in dates. Multipliers are relative to the population, so with no levers the court-wide rates match the observed data.

  `python agents_study.py` (3,000 cases, 1,154 advocate agents):

  | Scenario | Effective / day | On-day "not prepared" | Admitted early | Wasted trips |
  |---|---|---|---|---|
  | Baseline court | 13.7 | 305 | 0 | 2,471 |
  | Samay, no incentives | 26.2 | 69 | 273 | 1,015 |
  | + reminders | 26.5 | 67 | 214 | 986 |
  | + cost for on-the-day adjournment | 26.0 | 42 | 381 | 1,035 |
  | + both | 27.0 | 24 | 291 | 1,014 |

  The cost doesn't raise throughput much by itself; it moves unpreparedness from the courtroom to the readiness check, where the slot can still be refilled. Learning drift is small in 60 days (each advocate appears only a handful of times) but has the right sign.

## 5. Results

**Why the levers differ by stage** (`python ablation.py`, 3,000 cases, effective hearings/day):

| Scenario | Early | Middle | Late | 5+ yr advanced |
|---|---|---|---|---|
| Baseline | 2.7 | 3.5 | 3.9 | 23% |
| + Packing & process gate | 10.4 | 4.2 | 5.7 | 40% |
| + Readiness check + case brief | 10.0 | 5.2 | 6.5 | 59% |

The prerequisite gate fixes early stages (waiting for summons/warrants dominates their failures). Evidence and arguments fail for a different reason — counsel not prepared, the bench re-reading the file — which the readiness check and the case brief target.


_3,000 cases, 60 working days, seed 42, Recommended preset — replace with final Monte Carlo means._

| Metric | Baseline (60/day, flat 60-day gap) | Samay |
|---|---|---|
| Heard / day | 18.2 | 28.3 |
| Effective / day | 12.3 | 25.3 |
| Reach rate | 53% | 92% |
| Utilisation | 104% | 103% |
| 4+ yr cases heard | 40% | 47% |
| 5+ yr cases advanced | 23% | 40% |
| Days from first listing to hearing | 8.9 | 3.3 |
| Started within slot (±30 min) | 10% | 95% |
| Next date within 0.5–2× procedural gap | 8% | 74% |
| Wasted trips (listed, not heard) | 2,506 | 1,116 |

The baseline reproduces the case study's ~60 → 20 → 10 day, which is our calibration check. _TODO(Dev 3): screenshot + what a judge decides from each view._

## 6. Specs for integration

- **Data schema:** input = the roster CSV as in `data/` plus the four reference CSVs. Output = `proposed_schedule.csv` (`date, block, slot, est_start, case_id, purpose, est_minutes, exp_minutes, advocate_id, age_years, is_old, p_sub_eff, reason`).
- **Interfaces:** Python package (`src/`), CLI (`run.py`), Streamlit dashboard (`app.py`). `build_causelist(rank(state, day, cfg), day, cfg)` is the single call a court system needs each evening.
- **Dependencies:** Python 3.11, pandas, numpy, streamlit. No external services.
- **What's stubbed vs real:** real — ranking, packing, guardrail, next date, simulator, metrics, dashboard. Modelled — attendance/preparation behaviour (from the failure tables), process return times, agent behaviour.
- **What integration would take:** replace the CSV loader with DRISTI case + order-sheet data; feed actual process-service status into `ready_date`; run nightly to publish the causelist and push slot times to advocates/litigants.

## 7. How to run it

```
cd submissions/samay
pip install -r requirements.txt
python run.py
python run.py --roster ../../data/roster_3000.csv --preset "Justice Dimakar (clusterer)"
streamlit run app.py
```

## 8. What we'd build next

_TODO_
