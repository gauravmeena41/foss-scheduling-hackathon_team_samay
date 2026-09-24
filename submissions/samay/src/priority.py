"""Set B: Prioritisation. Owner: Dev 1 (Engine).

rank(state, day, cfg) -> eligible cases for `day`, best first.
Score = age factor x P(substantive | listed) / expected minutes  (x purpose-day boost)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from functools import lru_cache

import score100
from model import LATE_STAGES, load_reference, outcome_probs_df


@lru_cache(maxsize=1)
def _ref():
    return load_reference()

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
    est = elig["est_minutes"].astype(float)
    if cfg.get("summary_mandate"):
        brief = elig["is_old"] | elig["next_purpose"].isin(LATE_STAGES)
        est = est.where(~brief, est * (1 - cfg.get("brief_time_saving", 0.0)))
    elig["est_minutes"] = est
    # every listing also costs the changeover between hearings (calling the case, parties stepping up)
    exp_min = p_heard * est + (1 - p_heard) * cfg["mention_minutes"] + cfg.get("changeover_minutes", 0.0)
    age_factor = np.maximum(0.1, 1 + cfg["age_weight"] * elig["age_years"])
    boost_purposes = set(cfg.get("purpose_days", {}).get(WEEKDAYS[day.weekday()], []))
    boost = np.where(elig["next_purpose"].isin(boost_purposes), cfg["purpose_day_boost"], 1.0)

    elig["p_sub_eff"] = probs["substantive"]
    elig["exp_minutes"] = exp_min
    part_heard = elig["part_heard"].astype(bool) if "part_heard" in elig else False
    continuity = np.where(part_heard, cfg.get("part_heard_boost", 1.3), 1.0)   # bench still remembers it
    # three rankers: ours (value per minute), the teammate's 0-100 priority, and the hybrid of both
    pts = score100.score(elig, _ref(), cfg.get("score_weights"))
    for c in pts.columns:
        elig[c] = pts[c]
    mode = cfg.get("ranking", "hybrid")
    if mode == "samay":
        elig["score"] = age_factor * probs["substantive"] / exp_min * boost * continuity
    elif mode == "teammate":
        elig["score"] = pts["score_100"]
    else:   # hybrid: the teammate's priority, counted only if the hearing moves the case, per minute of court time
        # P(moves) is raised to a power > 1 (tuned: 1.5) so likely-to-fail listings don't look cheap
        power = cfg.get("hybrid_readiness_power", 1.5)
        elig["score"] = pts["score_100"] * probs["substantive"] ** power / exp_min * boost * continuity
    elig["overdue_days"] = (day - elig["due_date"]).dt.days
    n_here = elig["hearings_in_stage"].fillna(0).astype(int)
    elig["visit"] = np.where(n_here == 0, "first at stage", "repeat #" + (n_here + 1).astype(str))
    elig["reason"] = (
        elig["visit"] + "; "
        + pts["score_100"].round().astype(int).astype(str) + "/100 (age " + pts["pts_age"].round().astype(int).astype(str)
        + ", ready " + pts["pts_readiness"].round().astype(int).astype(str)
        + ", near-end " + pts["pts_disposal"].round().astype(int).astype(str)
        + ", churn " + pts["pts_churn"].round().astype(int).astype(str)
        + ", urgent " + pts["pts_urgency"].round().astype(int).astype(str) + "); "
        + np.where(elig["next_purpose"] == "BAIL", "liberty lane; ", "")
        + np.where(elig["is_old"], elig["age_years"].round().astype(int).astype(str) + "y old; ", "")
        + np.where(elig["repeat_adj"], "repeat adjournment; ", "")
        + np.where(boost > 1, "purpose day; ", "")
        + np.where(continuity > 1, "part-heard; ", "")
        + "P(moves)=" + (probs["substantive"] * 100).round().astype(int).astype(str) + "%"
    )
    return elig.sort_values("score", ascending=False)
