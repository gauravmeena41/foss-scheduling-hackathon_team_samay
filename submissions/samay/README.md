# Team Samay — working guide

Everything runs end to end already (v0). Each owner improves their own files; wire-up changes happen only at the 2:00 and 3:15 syncs.

```bash
pip install -r requirements.txt
python run.py                          # 100 cases, baseline vs Samay, writes proposed_schedule.csv
python run.py --roster <3000.csv>      # scale test (~12s)
python ablation.py --roster <3000.csv>  # what each lever adds, by stage (early / middle / late)
streamlit run app.py                   # dashboard
```

## Who owns what

| File | Set | Owner | v0 does | Your TODO |
|---|---|---|---|---|
| `src/model.py` | A | Dev 1 | Loads roster + reference tables; parses order text for pending process / "last chance"; old / stuck / repeat flags; `outcome_probs` | Richer summary parsing (who was absent → per-party attendance); e-filing features (see below) |
| `src/priority.py` | B | Dev 1 | Score = age factor × P(moves) ÷ expected min; prereq gate; purpose-day boost | Tune weights; urgency (bail, custody) |
| `src/packer.py` | C | Dev 1 | Guardrail quota for 4+ yr cases, fill to expected capacity, blocks, advocate clustering, est. start times | Short-first within block; party clustering |
| `src/next_date.py` | D | Dev 1 | Gap by next purpose × today's outcome; process → return date; weekly carry-forward | Load-aware dates (skip full days) |
| `src/config.py` | E | Dev 3 | Defaults, guardrail floor, presets: Recommended / Sehgal / Dimakar / Joshi | Tune presets; leave dates in UI |
| `src/simulate.py`, `baseline.py`, `metrics.py` | F | Dev 2 | Day-by-day sim, lognormal durations, outcomes drawn from the failure data, 13 metrics | Monte Carlo over seeds (mean ± spread); utilisation overrun cap |
| `src/agents.py` | L3 | Dev 2 | Advocate attendance multiplier (clash / slot / clustering) | Personalities, incentives, feedback loop |
| `src/brief.py` | Aditi's steer | Dev 1 → Dev 3 | One-page case brief: journey, last order, who was absent, per-stage readiness checklist | Seed from e-filing synopsis fields; "agreed / disputed" section |
| `simulate.confirm_readiness` | Aditi's steer | Dev 2 | Advocates confirm ready / need time 2 days before; freed slots refilled | Make it the L3 agent's decision (personality, incentives) |
| `app.py` | G | Dev 3 | KPI deltas vs baseline, backlog trend, causelist, at-risk list, all rule toggles | "Move these cases" what-if, 3-judge side-by-side, polish |
| `SUBMISSION.md` | — | Dev 3 | Draft | Fill numbers from final run at 4:00 |

## Contracts (don't change without telling the others)

- **Case** columns: `model.CASE_COLUMNS`
- **Causelist** columns: `packer.CAUSELIST_COLUMNS`
- **Hearing log** keys: see `simulate.run` (`rec` dict)
- **Config** keys: `config.DEFAULT_CONFIG`

## v0 numbers (3,000-case roster, 60 working days, seed 42, Recommended preset)

| Metric | Baseline | Samay |
|---|---|---|
| Heard / day | 18.2 | 28.3 |
| Effective / day | 12.3 | 25.3 |
| Reach rate | 53% | 92% |
| 4+ yr cases heard | 40% | 47% |
| 5+ yr cases advanced | 23% | 40% |
| Started within slot | 10% | 95% |
| Next-date sensible | 8% | 74% |
| Wasted trips | 2,506 | 1,116 |
| Disposed | 213 | 344 |

The baseline lands close to the case study's 60 → 20 → 10, which is a useful sanity check to show the panel.

## Levers by stage (3,000 cases, `python ablation.py`)

Effective hearings per day:

| Scenario | Early | Middle | Late | Total | 5+ yr advanced |
|---|---|---|---|---|---|
| Baseline | 2.7 | 3.5 | 3.9 | 12.3 | 23% |
| + Packing & process gate | 10.4 | 4.2 | 5.7 | 25.3 | 40% |
| + Readiness check | 10.7 | 4.9 | 5.8 | 26.3 | 41% |
| + Case brief | 10.2 | 4.4 | 6.1 | 25.9 | 53% |
| All levers | 10.0 | 5.2 | 6.5 | 26.8 | 59% |

The process gate fixes the early stages; the readiness check and case brief are what move middle- and late-stage cases.
