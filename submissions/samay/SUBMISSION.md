# Submission: samay

## 1. Team

- **Team / solo name:** samay
- **Members:** Guruprasad Meena, _add teammates_
- **Complexity level claimed:** **L3** — behavioural advocate agents on top of a full L2 model (§4)

## 2. One-line summary

Samay lists only hearings that are ready to happen and likely to move the case forward, packs them into real time slots up to the day's *expected* capacity, guarantees ageing cases a fixed share of every day, and makes the next date match the work the next step needs — so a 60 → 20 → 10 day becomes ~45 → 27 → 26.

## 3. The approach

**Inputs:** all six files in `data/`. The 3,000-case roster comes from `scripts/generate_roster.py` (bootstrap resample of the 100 — "more of the same mix"; advocate IDs are redrawn, so advocate clustering at 3,000 is synthetic). Optional synthetic e-filing columns via `src/efiling.py`.

**Core logic — a greedy, explainable pipeline run every evening:**

1. **Case model** (`model.py`, `orders.py`). One row per case. The last order sheet is classified into 11 events (process awaiting / served, mediation or higher-court order pending, objections pending, not ready, absent, part-heard, heard for judgment, progressed, verdict recorded) and *who the case is waiting on*. From that: a prerequisite gate, readiness, case-level no-show and unpreparedness multipliers (from who was absent / what was pending), part-heard priority, adjournments so far, and hearings/minutes left to disposal. Every field is documented in `CASE_SCHEMA`; `validate_cases()` checks any roster.
2. **Rank** (`priority.py`). Score = age factor × P(moves forward | listed) ÷ expected minutes, × part-heard and purpose-day boosts. Cases still waiting on process, mediation or a higher court are not eligible.
3. **Pack** (`packer.py`). Capacity = 420 min × overbooking factor, in *expected* minutes (a no-show costs a 2-minute mention, not the slot). The **guardrail** fills its share of the day first with 4+ year cases using its *own* oldest-weighted ranking, so no judge's rules can starve them; the rest goes to the judge's ranking. Cases are placed in time blocks, each advocate's matters back to back, each with an estimated start time.
4. **Readiness check** (`simulate.confirm_readiness`). Two days before, advocates confirm "ready" or "need time"; freed slots go to the next case. Two "need time"s flag the case.
5. **Case brief** (`brief.py`). One page per case for 4+ year and evidence / arguments / judgement matters: journey through the stages, last order, who was absent, what it waits on, the checklist for this hearing, work left to disposal.
6. **Next date** (`next_date.py`). Reference gap for the next purpose, shortened after an absence, set at the expected process return after a summons/warrant, next working day if unreached (or same weekday next week for a Sehgal-style court) — and slid past days that are already full.

**Key decisions.** Expected-minutes packing (airline-style overbooking) over counting cases. A guardrail the judge can raise but not lower, with its own ranking. Greedy over a solver, so every listing carries a plain-language `reason`. Stage-specific fixes, because hearings fail for different reasons at different stages (below).

**Assumptions (all in code as named constants):**
- Hearing durations lognormal around the reference minutes (σ = 0.35).
- Each listing's outcome drawn from P(substantive) + the failure-reason shares for its hearing type; once process has returned, process failures drop out and the rest renormalise.
- Process return time ~ Exponential(mean 1.5 × reference gap) × the case's e-filing multiplier.
- A substantive hearing advances to the next lifecycle stage (appearance/warrant → plea; side applications return to the main stage).
- Case brief halves "not prepared" failures and saves 20% of hearing time on the cases it covers; readiness check reveals 70% of would-be unpreparedness and 40% of would-be no-shows (agents replace these fixed rates in L3 mode).
- Case-level multipliers are normalised to a roster mean of 1, so roster-wide rates stay as observed.
- Two roster cases with a verdict already recorded but "Judgement" as next purpose are treated as disposed.

## 4. Justify your complexity level

- **L2.** Sampled durations; outcome distributions per hearing type from the failure data; prerequisites that change over time; per-case attendance and preparedness that update after every hearing; costs and incentives; every rule a judge can override from the dashboard with the impact shown against the baseline immediately; Monte Carlo over 10 seeds.
- **L3.** `src/agents.py`: each of the 1,154 advocates is an agent — diligent (30%), overloaded (50%) or dilatory (20%) — with its own probability of being prepared, of turning up, of being listed in another courtroom the same day, and of being honest at the readiness check. They **decide** whether to appear, whether they're prepared, and whether to admit "need time" two days ahead. The court's policy changes those decisions: a real slot and clustering cut the other-courtroom penalty; reminders raise preparedness; a cost for adjourning *on the day* (admitting early is free) makes dilatory advocates more honest. Outcomes **feed back**: a free on-the-day adjournment makes a non-diligent advocate prepare less next time; a costly one makes them prepare more; a hearing that went ahead on its date raises their trust in dates.

  `python agents_study.py` (3,000 cases):

  | Scenario | Effective / day | On-the-day "not prepared" | Admitted early | Wasted trips |
  |---|---|---|---|---|
  | Baseline court | 13.7 | 305 | 0 | 2,471 |
  | Samay, no incentives | 26.1 | 79 | 278 | 1,003 |
  | + reminders | 26.0 | 65 | 232 | 1,062 |
  | + cost for on-the-day adjournment | 26.4 | 46 | 323 | 1,020 |
  | + both | 26.5 | 30 | 294 | 997 |

  The cost barely moves throughput; it moves unpreparedness out of the courtroom and into the readiness check, where the slot can still be refilled. Learning drift is small in 60 days (each advocate appears a handful of times) but has the right sign.

## 5. Results

**3,000 cases, 60 working days, 10 seeds (mean ± sd), Recommended rules** — `python results.py`, full table in `results.md`:

| Metric | Baseline (60/day, flat 60-day gap) | Samay |
|---|---|---|
| Utilisation (minutes used ÷ 420) | 102% ± 0% | 99% ± 0% |
| Reach rate | 56% ± 1% | 89% ± 0% |
| Substantiveness (effective ÷ heard) | 68% ± 1% | 95% ± 0% |
| Effective hearings / day | 12.9 ± 0.2 | 25.8 ± 0.3 |
| 4+ yr cases heard at least once | 38% ± 1% | 50% ± 1% |
| 5+ yr cases advanced ≥ 1 stage | 18% ± 1% | 50% ± 1% |
| Days from first listing to hearing | 9.1 ± 0.5 | 3.4 ± 0.2 |
| Date slippage (heard vs date given) | 32.9 ± 0.4 | 9.6 ± 0.4 |
| Started within slot (± 30 min) | 10% ± 0% | 89% ± 2% |
| Next date within 0.5–2× procedural gap | 8% ± 0% | 81% ± 1% |
| Wasted trips (listed, not heard) | 2,472 | 1,069 |
| Disposed in 60 days | 186 | 347 |

The baseline reproduces the case study's ~60 → 20 → 10 day — our calibration check.

**Why the levers differ by stage** (`python ablation.py`, effective hearings/day):

| Scenario | Early | Middle | Late | 5+ yr advanced |
|---|---|---|---|---|
| Baseline | 3.3 | 3.6 | 3.4 | 18% |
| + Packing & prerequisite gate | 10.4 | 5.0 | 4.8 | 36% |
| + Readiness check | 10.8 | 5.1 | 4.8 | 34% |
| + Case brief | 9.5 | 4.4 | 6.2 | 48% |
| All levers | 9.6 | 4.9 | 6.4 | 50% |

Early stages fail on process (summons/warrants not back) — the gate fixes them. Evidence and arguments fail because counsel aren't prepared and the bench re-reads the file — the readiness check and the case brief target those.

**Three judges, one engine** (dashboard tab 1, 3,000 cases): fresh-first rules (Justice Joshi) reach 34 effective hearings a day but advance **0%** of 5+ year cases; with the guardrail on, 31 a day and 33%. That is the trade-off the guardrail makes visible and bounds.

**E-filing signals** (synthetic): no measurable gain in this simulation, because the prerequisite gate already keeps unready cases off the list. Their value is operational — flagging cases with no known contact for alternative service early, and giving parties realistic tentative dates.

**What a judge does with the dashboard** (`streamlit run app.py`):
- *Three judges* — see what their own rules cost the old backlog before adopting them.
- *Backlog & drift* — open 5+ year cases over time vs the baseline; hearing-hours left in the docket vs court hours available.
- *Today's causelist* — untick cases and see expected minutes, expected effective hearings and P(everyone listed is reached) change.
- *Case brief* — read one page instead of the file.
- *At-risk* — old-and-unheard, repeatedly adjourned and stuck cases, with what each is waiting on.
- *Advocates (L3)* — how advocates respond to reminders and adjournment costs.

## 6. Specs for integration

- **Input schema:** the roster CSV exactly as in `data/` (`case_number, filing_number, filing_date, advocate_id, party_id, current_stage, last_hearing_summary, purpose_of_next_hearing, hearings_<type>…, total_hearings_held`) plus the four reference CSVs and the calendar. Optional e-filing columns: `accused_addresses, contact_known, summons_rounds_prepaid, epost_prepaid, accused_in_jurisdiction, adr_opt_in, complainant_type`. `model.validate_cases()` returns a list of problems (empty = OK).
- **Output:** `proposed_schedule.csv` — `date, block, slot, est_start, case_id, purpose, est_minutes, exp_minutes, advocate_id, age_years, is_old, p_sub_eff, reason`. Case table: `model.CASE_COLUMNS`, documented in `model.CASE_SCHEMA`.
- **Interfaces:** Python package (`src/`), CLIs (`run.py`, `results.py`, `ablation.py`, `agents_study.py`), Streamlit dashboard (`app.py`). The nightly call a court system needs: `build_causelist(rank(state, day, cfg), day, cfg)`; after each hearing: `next_date(purpose, outcome, day, calendar, ref, cfg)`; per case: `build_brief(case)`.
- **Configuration:** `config.DEFAULT_CONFIG` + `PRESETS` (Recommended, Sehgal, Dimakar, Joshi); the guardrail in `config.GUARDRAILS` cannot be overridden by a preset or the UI.
- **Dependencies:** Python 3.11, pandas, numpy, streamlit. No external services, no network.
- **Real vs modelled:** real — case model, order-sheet classifier, ranking, packing, guardrail, readiness check logic, next date, case brief, metrics, dashboard. Modelled — outcomes (drawn from the failure tables), process-return times, agent behaviour, e-filing values.
- **What integration takes:** read cases and order sheets from DRISTI instead of the CSV (the classifier already works on order text); feed service-report status into `ready_date`; run nightly to publish the causelist; send slot times, the readiness check and reminders to advocates through DRISTI notifications / pending tasks; seed the case brief from the e-filing synopsis and append each order sheet.

## 7. How to run it

```
cd submissions/samay
pip install -r requirements.txt
python run.py                                   # 100-case sample, baseline vs Samay, writes proposed_schedule.csv
cd ../../scripts && python generate_roster.py --num-cases 3000 --seed 42 --out /tmp/roster_3000.csv && cd -
python run.py --roster /tmp/roster_3000.csv --agents
python results.py --roster /tmp/roster_3000.csv --seeds 10
python ablation.py --roster /tmp/roster_3000.csv
python agents_study.py --roster /tmp/roster_3000.csv
streamlit run app.py
```

## 8. What we'd build next

1. Calibrate the agent personalities and the case-brief effect on real DRISTI order sheets instead of assumptions.
2. Seed the case brief from the e-filing synopsis and let both counsel mark agreed vs disputed facts in DRISTI.
3. Run the readiness check through WhatsApp/SMS with a one-tap "ready / need time", and measure honesty directly.
4. A solver-based packer (CP-SAT) for multi-courtroom advocate conflicts across a court complex.
5. Learn process-return times from service reports per police station and address type.
