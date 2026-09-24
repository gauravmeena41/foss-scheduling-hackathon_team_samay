"""Case priority score, 0-100 — the teammate's algorithm (case_priority_scoring.md), vectorised.

Five factors, each 0-1, added (not multiplied, so readiness is one voice among five, not a veto):
    35 x age      : age_years / full_points_age, capped at 1 (full_points_age = max(5, round(mean + 2 sd)),
                    computed ONCE per roster and then fixed)
    25 x readiness: P(progress) for the next purpose x attendance factor (0.7 + 0.3 x share of the
                    people this hearing needs who were present last time)
    15 x disposal : stage number / 10 along the 11-stage lifecycle
    15 x churn    : (total hearings / hearings normally needed to reach this stage) - 1, clipped to [0, 1]
    10 x urgency  : 1.0 "last chance", 0.8 "for judgment", else 0
Each case is scored on its own details only; the breakdown is kept so every score can be explained.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

WEIGHTS = {"age": 35, "readiness": 25, "disposal": 15, "churn": 15, "urgency": 10}
STAGES = ["ADMISSION", "DELAY_CONDONATION_HEARING", "COGNIZANCE", "APPEARANCE", "WARRANT", "PLEA",
          "EXAMINATION_UNDER_S351_BNSS", "EVIDENCE_COMPLAINANT", "EVIDENCE_ACCUSED", "ARGUMENTS", "JUDGEMENT"]
REQUIRED = {
    "EVIDENCE_COMPLAINANT": ["complainant", "complainant's advocate", "accused advocate"],
    "EVIDENCE_ACCUSED": ["accused", "accused advocate", "complainant's advocate"],
    "PLEA": ["accused", "accused advocate"],
    "EXAMINATION_UNDER_S351_BNSS": ["accused", "accused advocate"],
    "ARGUMENTS": ["complainant's advocate", "accused advocate"],
    "JUDGEMENT": ["complainant's advocate", "accused advocate"],
    "BAIL": ["accused advocate"],
}
DEFAULT_REQUIRED = ["complainant's advocate"]


def full_points_age(age_years: pd.Series) -> int:
    """Where a case becomes unusually old for THIS roster. Compute once per roster, then keep fixed."""
    return int(max(5, round(age_years.mean() + 2 * age_years.std())))


def _present(summary: str) -> set[str]:
    line = next((l for l in str(summary).split("\n") if l.lower().startswith("present")), "")
    return {p.strip().lower() for p in line.split(":", 1)[1].split(",")} if ":" in line else set()


def attendance_factor(summary: str, purpose: str) -> float:
    need = REQUIRED.get(purpose, DEFAULT_REQUIRED)
    share = sum(p in _present(summary) for p in need) / len(need)
    return 0.7 + 0.3 * share


def urgency_value(summary: str) -> float:
    t = str(summary).lower()
    if re.search(r"last[\s-]chance", t):
        return 1.0
    if re.search(r"for judg(e)?ment", t):
        return 0.8
    return 0.0


def expected_hearings(ref: pd.DataFrame) -> dict:
    """Hearings normally needed to reach (and finish) each stage: running sum of medians."""
    out, run = {}, 0.0
    for st in STAGES:
        run += float(ref.at[st, "median_hearings"]) if st in ref.index else 0.0
        out[st] = run
    return out


AGE_WEIGHT_FLOOR = 20   # teammate's R2: judges may re-weight, but age never below 20% (not configurable)


def weights(custom: dict | None = None) -> dict:
    """Judge-adjusted weights, rescaled to 100, with the age floor enforced after rescaling."""
    w = dict(WEIGHTS, **(custom or {}))
    total = sum(w.values())
    w = {k: 100 * v / total for k, v in w.items()}
    if w["age"] < AGE_WEIGHT_FLOOR:
        rest = 100 - w["age"]
        w = {k: (AGE_WEIGHT_FLOOR if k == "age" else v * (100 - AGE_WEIGHT_FLOOR) / rest) for k, v in w.items()}
    return w


def score(df: pd.DataFrame, ref: pd.DataFrame, custom_weights: dict | None = None) -> pd.DataFrame:
    """Points per factor + total, for every row. Needs: age_years, full_points_age, p_substantive,
    attendance_factor, stage, total_hearings, urgency_value."""
    age = (df["age_years"] / df["full_points_age"]).clip(0, 1)
    ready = (df["p_substantive"].fillna(0) * df["attendance_factor"]).clip(0, 1)
    stage_no = df["stage"].map({s: i for i, s in enumerate(STAGES)}).fillna(0)
    disposal = stage_no / 10
    exp = df["stage"].map(expected_hearings(ref)).replace(0, np.nan)
    churn = (df["total_hearings"] / exp - 1).clip(0, 1).fillna(0)
    urg = df["urgency_value"].fillna(0)
    W = weights(custom_weights)
    pts = pd.DataFrame({
        "pts_age": W["age"] * age, "pts_readiness": W["readiness"] * ready,
        "pts_disposal": W["disposal"] * disposal, "pts_churn": W["churn"] * churn,
        "pts_urgency": W["urgency"] * urg,
    }, index=df.index)
    pts["score_100"] = pts.sum(axis=1).round(1)
    return pts


def explain(row) -> str:
    return (f"{row['score_100']:.0f}/100 = age {row['pts_age']:.0f} + ready {row['pts_readiness']:.0f} "
            f"+ near-end {row['pts_disposal']:.0f} + churn {row['pts_churn']:.0f} + urgent {row['pts_urgency']:.0f}")
