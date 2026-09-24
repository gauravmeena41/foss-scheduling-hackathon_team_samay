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
from model import ATT_MAX, ATT_MIN, DATA_DIR, OUTCOMES, SIDE_TYPES, advance, happens, load_reference, needs_brief, outcome_probs
from next_date import Calendar, next_date
from packer import _mins, build_causelist
from priority import rank

DURATION_SIGMA = 0.35
DAY_END_GRACE = 10       # minutes a started hearing may run past the end of the day    # lognormal spread around the reference minutes
PROCESS_PURPOSES = {"APPEARANCE", "WARRANT"}   # entering these needs a process to return first


def _mean_wait(ref, purpose) -> float:
    return 1.5 * ref.at[purpose, "gap_days"]


def _process_wait(rng, ref, purpose, mult: float = 1.0):
    """TRUE time for a summons / warrant to come back (case-specific when e-filing signals exist)."""
    return pd.Timedelta(days=float(rng.exponential(_mean_wait(ref, purpose) * mult)))


def _expected_wait(ref, purpose, mult: float, cfg: dict):
    """What the PLANNER expects: case-specific with e-filing signals, roster average without."""
    m = mult if cfg.get("use_efiling_signals", True) else 1.0
    return pd.Timedelta(days=_mean_wait(ref, purpose) * m)


def init_state(cases: pd.DataFrame, start: pd.Timestamp, ref: pd.DataFrame, rng, cfg: dict | None = None) -> pd.DataFrame:
    s = cases.copy().set_index("case_id", drop=False)
    s.index.name = None
    s["due_date"] = start
    if "process_wait_mult" not in s:
        s["process_wait_mult"] = 1.0
    s["ready_date"] = [start - pd.Timedelta(days=1) if ok else start + _process_wait(rng, ref, p, m)
                       for ok, p, m in zip(s["prereq_ok"], s["next_purpose"], s["process_wait_mult"])]
    s["first_heard"] = pd.NaT
    s["times_listed"] = 0
    s["stages_advanced"] = 0
    s["ready_est"] = [start - pd.Timedelta(days=1) if ok else start + _expected_wait(ref, p, m, cfg or {})
                      for ok, p, m in zip(s["prereq_ok"], s["next_purpose"], s["process_wait_mult"])]
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


def run(cases: pd.DataFrame, policy: str, cfg: dict, start: str = "2026-09-24", days: int = 60,  # noqa: C901
        seed: int = 42, data_dir: Path = DATA_DIR):
    """policy: 'samay' | 'baseline'. Returns (hearings_log, daily_log, causelists, final_state)."""
    rng = np.random.default_rng(seed)
    ref = load_reference(data_dir)
    cal = Calendar(data_dir / "court_calendar.csv", cfg.get("leave_dates", []))
    start_ts = cal.on_or_after(pd.Timestamp(start))
    s = init_state(cases, start_ts, ref, rng, cfg)
    if policy == "samay":   # blocked cases get a tentative date at the expected process return
        blocked = ~s["prereq_ok"].astype(bool)
        s.loc[blocked, "due_date"] = [cal.on_or_after(d) for d in s.loc[blocked, "ready_est"]]
    sim_cfg = cfg if policy == "samay" else {**cfg, "summary_mandate": False, "agents": cfg.get("agents")}
    blocks = {b["name"]: _mins(b["start"]) for b in cfg["blocks"]}

    hearings, daily, lists = [], [], []
    booked: dict = {}      # expected minutes already booked per future date (load-aware next dates)
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
            promised = s.at[cid, "due_date"]
            rec = {"date": day.date(), "case_id": cid, "purpose": purpose, "block": row["block"],
                   "promised_date": promised.date(), "slippage_days": (day - promised).days,
                   "est_start": row["est_start"], "actual_start": None, "listed": True, "reached": False,
                   "happened": False, "substantive": False, "minutes_used": 0.0, "failure_reason": "unreached",
                   "is_old": bool(s.at[cid, "is_old"]), "age_years": float(s.at[cid, "age_years"])}

            # court rises at day_minutes: don't start a hearing that is expected to run past it (10-min grace)
            if used + s.at[cid, "est_minutes"] > cfg["day_minutes"] + DAY_END_GRACE:
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
            # attendance history: a no-show makes the next no-show likelier, a hearing less so
            if outcome == "preparation":                  # unprepared again -> likelier next time too
                s.at[cid, "prep_mult"] = min(2.0, s.at[cid, "prep_mult"] * 1.2)
            if outcome == "substantive":                   # new stage, clean slate on preparation
                s.at[cid, "prep_mult"], s.at[cid, "part_heard"] = 1.0, False
            if outcome == "attendance":
                s.at[cid, "att_mult"] = min(ATT_MAX, s.at[cid, "att_mult"] * 1.3)
            elif happens(outcome):
                s.at[cid, "att_mult"] = max(ATT_MIN, s.at[cid, "att_mult"] * 0.85)
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
                        m = s.at[cid, "process_wait_mult"]
                        s.at[cid, "ready_date"] = day + _process_wait(rng, ref, new_p, m)
                        s.at[cid, "ready_est"] = day + _expected_wait(ref, new_p, m, cfg)
            nxt_purpose = s.at[cid, "next_purpose"]
            if nxt_purpose == "DISPOSED":
                nd = pd.NaT
            elif policy == "baseline":
                nd = cal.after(day, BASELINE["flat_gap_days"])
            else:
                need = 0.6 * s.at[cid, "est_minutes"]      # rough expected minutes of the next listing
                nd = next_date(nxt_purpose, outcome, day, cal, ref, cfg, s.at[cid, "ready_est"],
                               load=booked, need=need)
                if outcome == "substantive" and nxt_purpose in PROCESS_PURPOSES:
                    nd = max(nd, cal.on_or_after(s.at[cid, "ready_est"]))   # not before process is expected back
                booked[nd] = booked.get(nd, 0.0) + need
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
