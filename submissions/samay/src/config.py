"""Set E: Judge configuration + fixed guardrails. Owner: Dev 3 (after G).

A judge changes behaviour through config, never code. GUARDRAILS cannot be
overridden by a preset or the UI (case study goal #6: ageing cases must not be
deprioritised).
"""
from __future__ import annotations

import copy

GUARDRAILS = {
    "old_case_min_share_floor": 0.30,  # >= 30% of expected minutes go to 4+ yr cases, always
}

DEFAULT_CONFIG = {
    "day_minutes": 420,
    "overbook_factor": 1.15,          # list up to 115% of the day's EXPECTED minutes
    "mention_minutes": 2,             # time a non-happening listing still costs the court
    "old_case_min_share": 0.50,       # clamped to GUARDRAILS floor (tuned: beats baseline on 4+ and 5+)
    "age_weight": 0.35,               # score multiplier per year of age
    "gate_prerequisites": True,       # don't list cases whose process hasn't returned
    "cluster_by_advocate": True,      # same advocate -> same block, back to back
    "carry_forward_weekly": False,    # Sehgal: unreached case -> same weekday next week
    "purpose_days": {},               # {"Mon": ["ARGUMENTS"], ...} -> score boost on that day
    "purpose_day_boost": 1.5,
    "summary_mandate": False,         # Dimakar: cover-page summary halves prep failures on old cases
    "summary_prep_reduction": 0.5,
    "blocks": [                       # time blocks; filter picks which cases go where
        {"name": "Fresh & short", "start": "10:30", "end": "13:30", "filter": "not_old"},
        {"name": "Old matters", "start": "14:30", "end": "18:30", "filter": "old"},
    ],
    "leave_dates": [],                # judge's personal leave (YYYY-MM-DD)
    "agents": False,                  # L3: advocate agents decide to appear / seek adjournment
}

PRESETS = {
    "Recommended": {},
    "Justice Sehgal (block scheduler)": {
        "carry_forward_weekly": True,
        "old_case_min_share": 0.40,
        # His morning-fresh / afternoon-oldest split, stretched to the 420-min day
        "blocks": [
            {"name": "Fresh & notice", "start": "10:30", "end": "14:00", "filter": "not_old"},
            {"name": "Oldest matters", "start": "14:30", "end": "18:00", "filter": "old"},
        ],
    },
    "Justice Dimakar (clusterer)": {
        "cluster_by_advocate": True,
        "summary_mandate": True,
        "old_case_min_share": 0.50,
        "purpose_days": {"Tue": ["ARGUMENTS", "JUDGEMENT"], "Thu": ["APPEARANCE", "WARRANT"]},
    },
    "Justice Joshi (fresh first)": {
        "old_case_min_share": 0.0,    # he'd like 0 -> guardrail clamps to the floor
        "age_weight": -0.15,          # prefers young cases
        "cluster_by_advocate": False,
    },
}


def make_config(preset: str = "Recommended", enforce_guardrails: bool = True, **overrides) -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(copy.deepcopy(PRESETS.get(preset, {})))
    cfg.update(overrides)
    cfg["guardrail_clamped"] = False
    if enforce_guardrails and cfg["old_case_min_share"] < GUARDRAILS["old_case_min_share_floor"]:
        cfg["old_case_min_share"] = GUARDRAILS["old_case_min_share_floor"]
        cfg["guardrail_clamped"] = True
    return cfg
