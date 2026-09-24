"""Set B: Prioritisation. Owner: Dev 1 (Engine).

rank(state, day, cfg) -> eligible cases for `day`, best first.
Score = age factor x P(substantive | listed) / expected minutes  (x purpose-day boost)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from model import outcome_probs_df

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def rank(state: pd.DataFrame, day: pd.Timestamp, cfg: dict) -> pd.DataFrame:
    """Eligible = not disposed, due on/before `day`, and (if gating) prerequisites ready."""
    elig = state[(state["next_purpose"] != "DISPOSED") & (state["due_date"] <= day)].copy()
    ready = elig["ready_date"] <= day
    if cfg["gate_prerequisites"]:
        elig, ready = elig[ready], ready[ready]
    if elig.empty:
        return elig.assign(score=[], p_sub_eff=[], exp_minutes=[], reason=[])

    probs = outcome_probs_df(elig, cfg, ready)
    p_heard = probs["substantive"] + probs["preparation"]
    exp_min = p_heard * elig["est_minutes"] + (1 - p_heard) * cfg["mention_minutes"]
    age_factor = np.maximum(0.1, 1 + cfg["age_weight"] * elig["age_years"])
    boost_purposes = set(cfg.get("purpose_days", {}).get(WEEKDAYS[day.weekday()], []))
    boost = np.where(elig["next_purpose"].isin(boost_purposes), cfg["purpose_day_boost"], 1.0)

    elig["p_sub_eff"] = probs["substantive"]
    elig["exp_minutes"] = exp_min
    elig["score"] = age_factor * probs["substantive"] / exp_min * boost
    elig["reason"] = (
        np.where(elig["is_old"], elig["age_years"].round().astype(int).astype(str) + "y old; ", "")
        + np.where(elig["repeat_adj"], "repeat adjournment; ", "")
        + np.where(boost > 1, "purpose day; ", "")
        + "P(moves)=" + (probs["substantive"] * 100).round().astype(int).astype(str) + "%"
    )
    return elig.sort_values("score", ascending=False)
