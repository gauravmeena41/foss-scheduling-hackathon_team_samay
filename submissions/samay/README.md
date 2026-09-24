# Samay — scheduling layer for a High Court judge's docket

Team **samay**. The write-up for reviewers is [`SUBMISSION.md`](SUBMISSION.md); headline numbers are in [`results.md`](results.md); the 10-minute demo is [`DEMO.md`](DEMO.md).

```bash
pip install -r requirements.txt
python run.py                          # 100 cases: baseline vs Samay, writes proposed_schedule.csv
python run.py --roster <3000.csv> --agents --efiling
python results.py --roster <3000.csv> --seeds 10    # mean ± sd over seeds -> results.md
python ablation.py --roster <3000.csv>              # what each lever adds, by stage
python agents_study.py --roster <3000.csv>          # L3: how advocates respond to incentives
streamlit run app.py                                # dashboard
```

Make a 3,000-case roster with `cd ../../scripts && python generate_roster.py --num-cases 3000 --seed 42 --out /tmp/roster_3000.csv`.

## Module map

| File | What it does |
|---|---|
| `src/model.py` | Case model: roster + reference tables → one row per case (`CASE_SCHEMA`, `validate_cases`), outcome probabilities |
| `src/orders.py` | Classifies the last order sheet: 11 events, who the case is waiting on, last-chance / non-compliance |
| `src/efiling.py` | Optional DRISTI e-filing signals (synthetic) → process-return and no-show multipliers |
| `src/priority.py` | Ranks eligible cases: age × P(moves forward) ÷ expected minutes, part-heard / purpose-day boosts |
| `src/packer.py` | Builds the causelist: guardrail quota for 4+ yr cases (own ranking), expected-minutes capacity, blocks, advocate clustering, start times |
| `src/next_date.py` | Next date by purpose and outcome, process-return aware, slides past full days |
| `src/brief.py` | One-page case brief with the readiness checklist for this hearing |
| `src/config.py` | Defaults, fixed guardrails, presets (Recommended / Sehgal / Dimakar / Joshi) |
| `src/simulate.py` | Day-by-day court simulation: readiness check, hearings until the court rises, outcomes, next dates |
| `src/agents.py` | L3 advocate agents: personalities, decisions, incentives, learning |
| `src/baseline.py` | The case study's court: list 60, flat 60-day gap |
| `src/metrics.py` | The five scoring dimensions and supporting metrics |
| `app.py` | Streamlit dashboard |

## Headline (3,000 cases, 60 working days, 10 seeds, court sits 10:30–11:00 → 12:30 and 13:30 → 17:00)

| | Baseline | Samay |
|---|---|---|
| Listed → heard → effective / day | 60 → 14.3 → 9.8 | 33.9 → 20.8 → 20.0 |
| Reach rate | 43% | 89% |
| 5+ yr cases advanced | 14% | 39% |
| Started within slot | 9% | 78% |
| Next date sensible | 8% | 79% |
| Wasted trips | 2,742 | 785 |
