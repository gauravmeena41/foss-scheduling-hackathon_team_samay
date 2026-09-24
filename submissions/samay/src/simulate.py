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
from model import DATA_DIR, OUTCOMES, SIDE_TYPES, advance, happens, load_reference, needs_brief, outcome_probs
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
    s["times_declined"] = 0
    return s


def _draw(s, cid, day, sim_cfg, rng, mult=1.0):
    probs = outcome_probs(s.loc[cid], sim_cfg, s.at[cid, "ready_date"] <= day, attendance_mult=mult)
    return rng.choice(OUTCOMES, p=[probs[o] for o in OUTCOMES])


def confirm_readiness(ranked, s, day, cfg, sim_cfg, rng):
    """Two days before: advocates of the top candidates say 'ready' or 'need time'.

    Outcomes are drawn now (the same draw is used on the day, so nothing is double-counted).
    A would-be 'not prepared' failure is owned up to with P = confirm_reveals_prep, a would-be
    no-show with P = confirm_reveals_absence. Those cases drop out and the next-best case
    takes the slot. Returns (ranked_without_declined, predrawn_outcomes, declined[(cid, why)]).
    """
    window = 2 * cfg["day_minutes"] * cfg["overbook_factor"]
    predrawn, declined, seen = {}, [], 0.0
    for cid, em in zip(ranked.index, ranked["exp_minutes"]):
        if seen > window:
            break
        seen += em
        mult = agents.attendance_multiplier(rng, True, 1, bool(cfg.get("cluster_by_advocate"))) \
            if cfg.get("agents") else 1.0
        out = _draw(s, cid, day, sim_cfg, rng, mult)
        if out == "preparation" and rng.random() < cfg["confirm_reveals_prep"]:
            declined.append((cid, "need time (not prepared)"))
        elif out == "attendance" and rng.random() < cfg["confirm_reveals_absence"]:
            declined.append((cid, "need time (party unavailable)"))
        else:
            predrawn[cid] = out
    return ranked.drop(index=[c for c, _ in declined]), predrawn, declined


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
        predrawn, declined = {}, []
        if policy == "baseline":
            cl = baseline_causelist(s, day, cfg)
        else:
            ranked = rank(s, day, cfg)
            if cfg.get("readiness_confirmation"):
                ranked, predrawn, declined = confirm_readiness(ranked, s, day, cfg, sim_cfg, rng)
            cl = build_causelist(ranked, day, cfg)
        lists.append(cl)
        used, clock, n = 0.0, None, dict.fromkeys(["listed", "reached", "happened", "substantive"], 0)
        n["declined"] = len(declined)
        for cid, why in declined:                       # slot freed 2 days ahead, no trip made
            s.at[cid, "times_declined"] += 1
            if s.at[cid, "times_declined"] >= 2:
                s.at[cid, "repeat_adj"] = True
            nd = cal.after(day, cfg["declined_gap_days"])
            s.at[cid, "due_date"] = nd
            hearings.append({"date": day.date(), "case_id": cid, "purpose": s.at[cid, "next_purpose"],
                             "block": None, "est_start": None, "actual_start": None, "listed": False,
                             "reached": False, "happened": False, "substantive": False, "minutes_used": 0.0,
                             "failure_reason": why, "is_old": bool(s.at[cid, "is_old"]),
                             "age_years": float(s.at[cid, "age_years"]), "next_date": nd.date(),
                             "next_gap_days": None, "ref_gap_days": None})
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
                mult = 1.0
                if cfg.get("agents"):
                    mult = agents.attendance_multiplier(
                        rng, has_slot=(policy == "samay"), same_advocate_today=adv_count.get(row["advocate_id"], 1),
                        clustered=bool(cfg.get("cluster_by_advocate")) and policy == "samay")
                outcome = predrawn[cid] if cid in predrawn else _draw(s, cid, day, sim_cfg, rng, mult)
                est = s.at[cid, "est_minutes"]
                if sim_cfg.get("summary_mandate") and needs_brief(s.loc[cid]):
                    est *= 1 - cfg.get("brief_time_saving", 0.0)   # judge isn't re-reading the file
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
