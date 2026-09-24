"""Set F: Simulation. Owner: Dev 2 (Simulator).

run(cases, policy, cfg, ...) plays the court forward day by day:
  plan causelist -> hear in order until the day's minutes run out -> draw outcomes from
  the observed data -> advance / adjourn -> set next date -> log.
The same simulator runs the baseline and our policy, so the comparison is fair.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import agents
from baseline import BASELINE, baseline_causelist
from model import DATA_DIR, OUTCOMES, SIDE_TYPES, advance, happens, load_reference, outcome_probs
from next_date import Calendar, next_date
from packer import _mins, build_causelist
from priority import rank

DURATION_SIGMA = 0.35    # lognormal spread around the reference minutes
PROCESS_PURPOSES = {"APPEARANCE", "WARRANT"}   # entering these needs a process to return first


def _process_wait(rng, ref, purpose):
    return pd.Timedelta(days=float(rng.exponential(1.5 * ref.at[purpose, "gap_days"])))


def init_state(cases: pd.DataFrame, start: pd.Timestamp, ref: pd.DataFrame, rng) -> pd.DataFrame:
    s = cases.copy().set_index("case_id", drop=False)
    s.index.name = None
    s["due_date"] = start
    s["ready_date"] = [start - pd.Timedelta(days=1) if ok else start + _process_wait(rng, ref, p)
                       for ok, p in zip(s["prereq_ok"], s["next_purpose"])]
    s["first_heard"] = pd.NaT
    s["times_listed"] = 0
    s["stages_advanced"] = 0
    s["disposed_on"] = pd.NaT
    return s


def _set_purpose(s, cid, purpose, stage, ref):
    s.at[cid, "next_purpose"], s.at[cid, "stage"] = purpose, stage
    if purpose in ref.index:
        for col in ["est_minutes", "p_substantive", "fail_attendance", "fail_preparation",
                    "fail_process", "fail_other"]:
            s.at[cid, col] = ref.at[purpose, col]
        s.at[cid, "hearings_in_stage"] = 0


def run(cases: pd.DataFrame, policy: str, cfg: dict, start: str = "2026-09-24", days: int = 60,
        seed: int = 42, data_dir: Path = DATA_DIR):
    """policy: 'samay' | 'baseline'. Returns (hearings_log, daily_log, causelists, final_state)."""
    rng = np.random.default_rng(seed)
    ref = load_reference(data_dir)
    cal = Calendar(data_dir / "court_calendar.csv", cfg.get("leave_dates", []))
    start_ts = cal.on_or_after(pd.Timestamp(start))
    s = init_state(cases, start_ts, ref, rng)
    sim_cfg = cfg if policy == "samay" else {**cfg, "summary_mandate": False, "agents": cfg.get("agents")}
    blocks = {b["name"]: _mins(b["start"]) for b in cfg["blocks"]}

    hearings, daily, lists = [], [], []
    workdays = [d for d in cal.days if d >= start_ts][:days]
    for day in workdays:
        if policy == "baseline":
            cl = baseline_causelist(s, day, cfg)
        else:
            cl = build_causelist(rank(s, day, cfg), day, cfg)
        lists.append(cl)
        used, clock, n = 0.0, None, dict.fromkeys(["listed", "reached", "happened", "substantive"], 0)
        adv_count = cl["advocate_id"].value_counts().to_dict() if len(cl) else {}
        for _, row in cl.iterrows():
            cid = row["case_id"]
            n["listed"] += 1
            s.at[cid, "times_listed"] += 1
            if pd.isna(s.at[cid, "first_scheduled"]):
                s.at[cid, "first_scheduled"] = day
            block_start = blocks.get(row["block"], _mins(row["est_start"]))
            clock = block_start if clock is None else max(clock, block_start)
            purpose = s.at[cid, "next_purpose"]
            rec = {"date": day.date(), "case_id": cid, "purpose": purpose, "block": row["block"],
                   "est_start": row["est_start"], "actual_start": None, "listed": True, "reached": False,
                   "happened": False, "substantive": False, "minutes_used": 0.0, "failure_reason": "unreached",
                   "is_old": bool(s.at[cid, "is_old"]), "age_years": float(s.at[cid, "age_years"])}

            if used >= cfg["day_minutes"]:
                outcome = "unreached"
            else:
                ready = s.at[cid, "ready_date"] <= day
                mult = 1.0
                if cfg.get("agents"):
                    mult = agents.attendance_multiplier(
                        rng, has_slot=(policy == "samay"), same_advocate_today=adv_count.get(row["advocate_id"], 1),
                        clustered=bool(cfg.get("cluster_by_advocate")) and policy == "samay")
                probs = outcome_probs(s.loc[cid], sim_cfg, ready, attendance_mult=mult)
                outcome = rng.choice(OUTCOMES, p=[probs[o] for o in OUTCOMES])
                est = s.at[cid, "est_minutes"]
                mins = est * float(np.exp(rng.normal(-DURATION_SIGMA ** 2 / 2, DURATION_SIGMA))) \
                    if happens(outcome) else cfg["mention_minutes"]
                rec.update(reached=True, happened=happens(outcome), substantive=outcome == "substantive",
                           minutes_used=round(mins, 1), failure_reason=outcome, actual_start=f"{int(clock)//60:02d}:{int(clock)%60:02d}")
                used += mins
                clock += mins
                n["reached"] += 1
                n["happened"] += happens(outcome)
                n["substantive"] += outcome == "substantive"

            # --- state update ---
            if happens(outcome):
                s.at[cid, "last_heard"] = day
                if pd.isna(s.at[cid, "first_heard"]):
                    s.at[cid, "first_heard"] = day
                s.at[cid, "hearings_in_stage"] += 1
            if outcome == "substantive":
                new_p, new_stage = advance(purpose, s.at[cid, "stage"])
                s.at[cid, "stages_advanced"] += purpose not in SIDE_TYPES
                if new_p == "DISPOSED":
                    s.at[cid, "next_purpose"] = "DISPOSED"
                    s.at[cid, "disposed_on"] = day
                else:
                    _set_purpose(s, cid, new_p, new_stage, ref)
                    if new_p in PROCESS_PURPOSES:
                        s.at[cid, "ready_date"] = day + _process_wait(rng, ref, new_p)
            nxt_purpose = s.at[cid, "next_purpose"]
            if nxt_purpose == "DISPOSED":
                nd = pd.NaT
            elif policy == "baseline":
                nd = cal.after(day, BASELINE["flat_gap_days"])
            else:
                nd = next_date(nxt_purpose, outcome, day, cal, ref, cfg, s.at[cid, "ready_date"])
            s.at[cid, "due_date"] = nd if not pd.isna(nd) else pd.Timestamp("2100-01-01")
            rec["next_date"] = None if pd.isna(nd) else nd.date()
            rec["next_gap_days"] = None if pd.isna(nd) else (nd - day).days
            rec["ref_gap_days"] = ref.at[nxt_purpose, "gap_days"] if nxt_purpose in ref.index else None
            hearings.append(rec)

        open_ = s[s["next_purpose"] != "DISPOSED"]
        daily.append({"date": day.date(), **n, "minutes_used": round(used, 1),
                      "open_cases": len(open_), "open_4plus": int(open_["is_old"].sum()),
                      "open_5plus": int((open_["age_years"] >= 5).sum()),
                      "disposed_total": int((s["next_purpose"] == "DISPOSED").sum())})

    return pd.DataFrame(hearings), pd.DataFrame(daily), pd.concat(lists, ignore_index=True), s
