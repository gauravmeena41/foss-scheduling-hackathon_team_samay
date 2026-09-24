"""Set F: Metrics. Owner: Dev 2. Formulas are the ones agreed in the execution plan."""
from __future__ import annotations

import pandas as pd

SLOT_TOLERANCE_MIN = 30


def _mins(hhmm):
    if not isinstance(hhmm, str):
        return None
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def compute(hearings: pd.DataFrame, daily: pd.DataFrame, state: pd.DataFrame, cfg: dict) -> dict:
    n_days = max(1, len(daily))
    listed = len(hearings)
    reached = int(hearings["reached"].sum())
    happened = int(hearings["happened"].sum())
    substantive = int(hearings["substantive"].sum())

    heard_cases = state.dropna(subset=["first_heard"])
    wait = (heard_cases["first_heard"] - heard_cases["first_scheduled"]).dt.days

    r = hearings[hearings["reached"]]
    drift = (r["actual_start"].map(_mins) - r["est_start"].map(_mins)).abs()
    on_slot = float((drift <= SLOT_TOLERANCE_MIN).mean()) if len(r) else 0.0

    g = hearings.dropna(subset=["next_gap_days", "ref_gap_days"])
    g = g[g["failure_reason"] != "unreached"]
    sensible = float(((g["next_gap_days"] >= 0.5 * g["ref_gap_days"]) &
                      (g["next_gap_days"] <= 2 * g["ref_gap_days"])).mean()) if len(g) else 0.0

    old4 = state[state["age_years"] >= 4]
    old5 = state[state["age_years"] >= 5]
    return {
        "Utilisation": sum(hearings["minutes_used"]) / (cfg["day_minutes"] * n_days),
        "Reach rate": reached / listed if listed else 0.0,
        "Substantiveness": substantive / happened if happened else 0.0,
        "Backlog 4+ heard": float(old4["first_heard"].notna().mean()) if len(old4) else 0.0,
        "Backlog 5+ advanced": float(((old5["stages_advanced"] > 0) | old5["disposed_on"].notna()).mean())
        if len(old5) else 0.0,
        "Predictability (days to hearing)": float(wait.mean()) if len(wait) else float("nan"),
        "Started within slot": on_slot,
        "Next-date sensible": sensible,
        "Listed / day": listed / n_days,
        "Heard / day": happened / n_days,
        "Effective / day": substantive / n_days,
        "Wasted trips": listed - happened,
        "Disposed": int(state["disposed_on"].notna().sum()),
    }


PERCENT = {"Utilisation", "Reach rate", "Substantiveness", "Backlog 4+ heard", "Backlog 5+ advanced",
           "Started within slot", "Next-date sensible"}


def compare(ours: dict, base: dict) -> pd.DataFrame:
    rows = []
    for k in ours:
        fmt = (lambda v: f"{v:.0%}") if k in PERCENT else (lambda v: f"{v:.1f}" if isinstance(v, float) else str(v))
        rows.append({"metric": k, "baseline": fmt(base[k]), "samay": fmt(ours[k])})
    return pd.DataFrame(rows)
