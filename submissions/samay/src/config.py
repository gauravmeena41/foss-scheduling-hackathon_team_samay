"""Set E: Judge configuration + fixed guardrails. Owner: Dev 3 (after G).

A judge changes behaviour through config, never code. GUARDRAILS cannot be
overridden by a preset or the UI (case study goal #6: ageing cases must not be
deprioritised).
"""
from __future__ import annotations

import copy

GUARDRAILS = {
    "old_case_min_share_floor": 0.30,  # >= 30% of expected minutes go to 4+ yr cases, always
    "guardrail_age_weight": 0.35,      # the quota is filled oldest-first, whatever the judge's own age weight
}

DEFAULT_CONFIG = {
    # Court timings: bench sits from 10:30-11:00 (start varies) to 12:30, lunch 12:30-13:30, then 13:30-17:00.
    "court_sittings": [["10:30", "12:30"], ["13:30", "17:00"]],
    "start_window": ["10:30", "11:00"],   # actual start is anywhere in this window; the plan assumes the midpoint
    "day_minutes": 315,                   # expected sitting minutes (derived in make_config)
    "overbook_factor": 1.15,          # list up to 115% of the day's EXPECTED minutes
    "mention_minutes": 2,             # time a non-happening listing still costs the court
    "old_case_min_share": 0.50,       # clamped to GUARDRAILS floor (tuned: beats baseline on 4+ and 5+)
    "age_weight": 0.35,               # score multiplier per year of age
    "gate_prerequisites": True,       # don't list cases whose process hasn't returned
    "cluster_by_advocate": True,      # same advocate -> same block, back to back
    "carry_forward_weekly": False,    # Sehgal: unreached case -> same weekday next week
    "purpose_days": {},               # {"Mon": ["ARGUMENTS"], ...} -> score boost on that day
    "purpose_day_boost": 1.5,
    "part_heard_boost": 1.3,          # part-heard matters first: the bench still remembers them
    "summary_mandate": True,          # case brief for old / late-stage cases (Dimakar's cover page, auto-drafted)
    "summary_prep_reduction": 0.5,    # ...halves "not prepared" failures on those cases (assumption)
    "brief_time_saving": 0.2,         # ...and cuts their hearing time 20%: no re-reading the file (assumption)
    "readiness_confirmation": True,   # advocates confirm ready / need time 2 days before
    "confirm_reveals_prep": 0.7,      # share of would-be "not prepared" failures they own up to in advance
    "confirm_reveals_absence": 0.4,   # share of would-be no-shows they flag in advance
    "declined_gap_days": 7,           # "need time" -> relisted after this many days
    "blocks": [                       # time blocks; filter picks which cases go where
        {"name": "Morning (fresh & short first)", "start": "10:45", "end": "12:30", "filter": "not_old"},
        {"name": "Afternoon (oldest matters)", "start": "13:30", "end": "17:00", "filter": "old"},
    ],
    "use_efiling_signals": True,      # predict process-return dates per case when e-filing data exists
    "leave_dates": [],                # judge's personal leave (YYYY-MM-DD)
    "agents": False,                  # L3: advocate agents (personalities) decide, and learn from the court
    "reminders": True,                # SMS/WhatsApp reminder of next steps 2 days before (acts on agents)
    "adjournment_cost": True,         # costs for adjourning ON THE DAY; free if admitted at the readiness check
}

PRESETS = {
    "Recommended": {},
    "Justice Sehgal (block scheduler)": {
        "carry_forward_weekly": True,
        "old_case_min_share": 0.40,
        # His split - fresh & notice matters before lunch, oldest matters after - on the court's timings
        "blocks": [
            {"name": "Fresh & notice", "start": "10:45", "end": "12:30", "filter": "not_old"},
            {"name": "Oldest matters", "start": "13:30", "end": "17:00", "filter": "old"},
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


def _m(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def expected_sitting_minutes(cfg: dict) -> float:
    """Sitting minutes in a day, taking the expected (midpoint) start of the first sitting."""
    (s1, e1), *rest = cfg["court_sittings"]
    w0, w1 = (_m(t) for t in cfg["start_window"])
    first = _m(e1) - (w0 + w1) / 2
    return first + sum(_m(e) - _m(s) for s, e in rest)


def make_config(preset: str = "Recommended", enforce_guardrails: bool = True, **overrides) -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(copy.deepcopy(PRESETS.get(preset, {})))
    cfg.update(overrides)
    if "day_minutes" not in overrides:
        cfg["day_minutes"] = expected_sitting_minutes(cfg)
    cfg["guardrail_clamped"] = False
    if enforce_guardrails and cfg["old_case_min_share"] < GUARDRAILS["old_case_min_share_floor"]:
        cfg["old_case_min_share"] = GUARDRAILS["old_case_min_share_floor"]
        cfg["guardrail_clamped"] = True
    return cfg
