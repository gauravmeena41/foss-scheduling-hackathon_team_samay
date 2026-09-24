"""Baseline policy (case study, section 3). Owner: Dev 2.

List 60 hearings a day, oldest-due first, no prerequisite check, no time slots,
flat 60-day gap after every hearing, whatever happened.
"""
from __future__ import annotations

import pandas as pd

BASELINE = {"listed_per_day": 60, "flat_gap_days": 60}


def baseline_causelist(state: pd.DataFrame, day: pd.Timestamp, cfg: dict) -> pd.DataFrame:
    due = state[(state["next_purpose"] != "DISPOSED") & (state["due_date"] <= day)]
    due = due.sort_values(["due_date", "case_id"]).head(BASELINE["listed_per_day"])
    return pd.DataFrame({
        "date": day.date(), "block": "All day", "slot": "10:30-18:30", "est_start": "10:30",
        "case_id": due["case_id"], "purpose": due["next_purpose"], "est_minutes": due["est_minutes"],
        "exp_minutes": due["est_minutes"], "advocate_id": due["advocate_id"],
        "age_years": due["age_years"].round(1), "is_old": due["is_old"], "p_sub_eff": due["p_substantive"],
        "reason": "due",
    }).reset_index(drop=True)
