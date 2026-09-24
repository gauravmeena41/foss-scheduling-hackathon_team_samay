# Samay — scheduling layer for a High Court judge's docket

Team **samay**. The write-up for reviewers is [`SUBMISSION.md`](SUBMISSION.md); headline numbers are in [`results.md`](results.md); the 10-minute demo is [`DEMO.md`](DEMO.md).

```bash
pip install -r requirements.txt
python run.py                          # 100 cases: baseline vs Samay, writes proposed_schedule.csv
python run.py --roster <3000.csv> --agents --efiling
python results.py --roster <3000.csv> --seeds 10    # mean ± sd over seeds -> results.md
python ablation.py --roster <3000.csv>              # what each lever adds, by stage
python agents_study.py --roster <3000.csv>          # L3: how advocates respond to incentives
python compare_rankers.py --roster <3000.csv>       # ours vs teammate's vs hybrid ranking
python -m pytest tests -q                           # engine checks (pip install pytest)
streamlit run app.py                                # dashboard
```

Make a 3,000-case roster with `cd ../../scripts && python generate_roster.py --num-cases 3000 --seed 42 --out /tmp/roster_3000.csv`.

## Module map

| File | What it does |
|---|---|
| `src/model.py` | Case model: roster + reference tables → one row per case (`CASE_SCHEMA`, `validate_cases`), outcome probabilities |
| `src/orders.py` | Classifies the last order sheet: 11 events, who the case is waiting on, last-chance / non-compliance |
| `src/efiling.py` | Optional DRISTI e-filing signals (synthetic) → process-return and no-show multipliers |
| `src/score100.py` | Teammate's 0-100 priority: age 35, readiness 25, near the end 15, churn 15, urgency 10 — with the factor breakdown |
| `src/priority.py` | Ranks eligible cases: hybrid (priority × P(moves) ÷ minutes), ours, or the teammate's score |
| `src/packer.py` | Builds the causelist: guardrail quota for 4+ yr cases (own ranking), expected-minutes capacity, blocks, advocate clustering, start times |
| `src/next_date.py` | Next date by purpose and outcome, process-return aware, slides past full days |
| `src/brief.py` | One-page case brief with the readiness checklist for this hearing |
| `src/config.py` | Defaults, fixed guardrails, presets (Recommended / Sehgal / Dimakar / Joshi) |
| `src/simulate.py` | Day-by-day court simulation: readiness check, hearings until the court rises, outcomes, next dates |
| `src/agents.py` | L3 advocate agents: personalities, decisions, incentives, learning |
| `src/baseline.py` | The case study's court: list 60, flat 60-day gap |
| `src/metrics.py` | The five scoring dimensions and supporting metrics |
| `app.py` | Streamlit dashboard |

## Headline (one judge, 3,000 cases, 60 sitting days, 10 seeds; court sits 10:30–11:00 → 12:30 and 13:30 → 17:00, 2-min changeover, hybrid ranking)

| | Baseline | Samay |
|---|---|---|
| Listed → heard → effective / day | 60 → 12.3 → 8.4 | 22.1 → 15.2 → 14.3 |
| Cases disposed in 60 days | 127 | 407 |
| Reach rate | 37% | 86% |
| 5+ yr cases advanced | 12% | 37% |
| Started within slot | 9% | 77% |
| Next date sensible | 8% | 95% |
| Wasted trips | 2,862 | 415 |

Ranking = teammate's 0-100 priority (`src/score100.py`) × P(moves forward) ÷ minutes; see `rankers.md` for the three-way comparison.

Dashboard: `streamlit run app.py` → sidebar **Upload Excel / CSV** → `samples/sample_docket_3000.xlsx` (3,000 cases) or `samples/sample_cases.xlsx` (100-row template). Screenshots in `docs/`.
