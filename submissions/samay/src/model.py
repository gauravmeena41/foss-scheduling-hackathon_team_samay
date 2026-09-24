"""Set A: Case model. Owner: Dev 1 (Engine).

Loads the roster + reference tables and returns one normalised row per case
(the `Case` contract). Everything downstream reads only these columns.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

import efiling
from orders import classify

DATA_DIR = Path(__file__).resolve().parents[3] / "data"

# Fixed lifecycle order (case study, section 5.1). Side types sit outside it.
LIFECYCLE = [
    "ADMISSION", "DELAY_CONDONATION_HEARING", "COGNIZANCE", "APPEARANCE", "WARRANT",
    "PLEA", "EXAMINATION_UNDER_S351_BNSS", "EVIDENCE_COMPLAINANT", "EVIDENCE_ACCUSED",
    "ARGUMENTS", "JUDGEMENT",
]
SIDE_TYPES = {"BAIL", "REPORTS", "APPLICATION_REVIEW"}
DISPOSED = "DISPOSED"

# Failure-reason columns grouped into what our levers can act on.
FAILURE_GROUPS = {
    "attendance": ["Respondent Absence / Non-Compliance", "Petitioner Absence / Non-Compliance",
                   "Both Parties Unready / Absent"],
    "preparation": ["Party Sought Time / Adjournment", "Evidence / Filing Not Ready"],
    "process": ["Awaiting Process / Summons / Warrant Return"],
    "other": ["Court Administrative Issue", "Court Holiday / No Sitting", "External Dependency", "Unclear"],
}

# Order-text keywords that mean a prerequisite (process return) is still pending.

# Attendance history -> multiplier on the observed no-show rate for THIS case
ATT_ACCUSED_ABSENT = 1.4
ATT_BOTH_ABSENT = 1.8
ATT_ALL_PRESENT = 0.7
ATT_MIN, ATT_MAX = 0.5, 2.5


def attendance_multiplier(summary: str) -> float:
    """From the last order sheet's Present/Absent lines. Parties matter more than advocates."""
    absent = next((l.split(":", 1)[1].lower() for l in str(summary).split("\n")
                   if l.lower().startswith("absent")), "")
    parties = [p.strip() for p in absent.split(",") if p.strip()]
    accused = any(p == "accused" for p in parties)
    complainant = any(p == "complainant" for p in parties)
    if accused and complainant:
        return ATT_BOTH_ABSENT
    if accused or complainant:
        return ATT_ACCUSED_ABSENT
    return ATT_ALL_PRESENT if not parties else 1.0   # only advocates absent -> neutral


AGE_BINS = [0, 1, 2, 3, 4, 5, 100]
AGE_LABELS = ["<1", "1-2", "2-3", "3-4", "4-5", "5+"]

CASE_COLUMNS = [
    "case_id", "advocate_id", "party_id", "filing_date", "age_years", "age_bucket",
    "stage", "next_purpose", "hearings_in_stage", "total_hearings", "est_minutes",
    "p_substantive", "fail_attendance", "fail_preparation", "fail_process", "fail_other", "att_mult",
    "p_happen", "prereq_ok", "prereq_reason", "is_old", "is_stuck", "repeat_adj",
    "first_scheduled", "last_heard", "last_summary", "history",
    "last_event", "waiting_on", "readiness", "prep_mult", "part_heard", "last_chance", "non_compliance",
    "absent_parties", "adjournments_est", "remaining_hearings_est", "remaining_minutes_est", "data_note",
    "process_wait_mult", "has_efiling", "visit",
]

CASE_SCHEMA = {
    "case_id": "case number (anonymised)",
    "advocate_id / party_id": "for clustering",
    "filing_date, age_years, age_bucket": "age of the case; buckets <1 … 5+",
    "stage": "current lifecycle stage (UPPER_SNAKE)",
    "next_purpose": "purpose of the next hearing; DISPOSED once judgment is delivered",
    "hearings_in_stage, total_hearings": "hearings held at the next purpose's stage / overall",
    "est_minutes": "reference minutes for the next purpose",
    "p_substantive": "P(moves forward) for the purpose (substantiveness table)",
    "fail_attendance / preparation / process / other": "share of non-substantive outcomes by cause (failure table)",
    "att_mult": "case-level no-show multiplier from who was absent last time (roster mean = 1)",
    "prep_mult": "case-level unpreparedness multiplier from the last order (roster mean = 1)",
    "p_happen": "P(hearing actually happens) at reference rates",
    "prereq_ok, prereq_reason": "False = blocked until process / mediation / higher-court order returns",
    "last_event, waiting_on": "classified last order (orders.py) and who the case now waits on",
    "readiness": "0-1 readiness of the next hearing implied by the last order",
    "part_heard": "arguments/evidence begun - list soon, same bench memory",
    "last_chance, non_compliance": "order-text flags",
    "is_old, is_stuck, repeat_adj": "4+ yrs · at/above median hearings at stage with no movement last time · repeated adjournment",
    "adjournments_est": "total hearings minus stages completed",
    "remaining_hearings_est, remaining_minutes_est": "median work left to disposal",
    "data_note": "data-quality note (e.g. verdict already recorded)",
    "process_wait_mult": "case-specific multiplier on summons/warrant return time from e-filing signals (1 = no signals)",
    "has_efiling": "True when the roster carries e-filing columns (efiling.EFILING_COLUMNS)",
    "visit": "'first at stage' or 'repeat #N' - how many times this purpose has been heard before",
}

# Stages every case passes through (delay condonation and warrant are conditional)
CORE_PATH = [p for p in LIFECYCLE if p not in ("DELAY_CONDONATION_HEARING", "WARRANT")]

# Stages where the judge needs the file re-read -> the case brief pays off here
LATE_STAGES = {"EVIDENCE_COMPLAINANT", "EVIDENCE_ACCUSED", "ARGUMENTS", "JUDGEMENT"}


def needs_brief(case) -> bool:
    return bool(case["is_old"]) or case["next_purpose"] in LATE_STAGES


def norm(purpose: str) -> str:
    """'Examination Under S351 Bnss' -> 'EXAMINATION_UNDER_S351_BNSS'."""
    return re.sub(r"\s+", "_", str(purpose).strip()).upper()


def load_reason_shares(data_dir: Path = DATA_DIR) -> dict:
    """{hearing type: {group: [(detailed reason, share within the group), ...]}} from the failure table."""
    fail = pd.read_csv(data_dir / "hearing_failure_reasons.csv").set_index("hearingType")
    out = {}
    for ht, row in fail.iterrows():
        out[ht] = {}
        for group, cols in FAILURE_GROUPS.items():
            counts = [(c, float(row[c])) for c in cols]
            total = sum(n for _, n in counts)
            out[ht][group] = [(c, n / total) for c, n in counts] if total > 0 else [(cols[0], 1.0)]
    return out


def visit_label(hearings_in_stage) -> pd.Series:
    """'first at stage' or 'repeat #N' (N = this hearing's number at the current stage)."""
    n = pd.Series(hearings_in_stage).fillna(0).astype(int)
    return pd.Series(np.where(n == 0, "first at stage", "repeat #" + (n + 1).astype(str)), index=n.index)


def load_reference(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """One row per hearing type: minutes, ideal gap, median hearings, P(substantive), failure shares."""
    ref = pd.read_csv(data_dir / "hearing_type_reference.csv").rename(columns={
        "Hearing Purpose": "purpose",
        "Time it takes for hearing (mins) - estimated": "est_minutes",
        "Time to next hearing given this is the purpose (days)": "gap_days",
        "Median Hearings per Case": "median_hearings",
    }).set_index("purpose")
    sub = pd.read_csv(data_dir / "substantiveness_by_hearing_type.csv").set_index("hearingType")
    ref["p_substantive"] = sub.iloc[:, 0] / 100.0

    fail = pd.read_csv(data_dir / "hearing_failure_reasons.csv").set_index("hearingType")
    total = fail[sum(FAILURE_GROUPS.values(), [])].sum(axis=1).replace(0, 1)
    for group, cols in FAILURE_GROUPS.items():
        # share of NON-substantive outcomes caused by this group
        ref[f"fail_{group}"] = fail[cols].sum(axis=1) / total
    return ref[["est_minutes", "gap_days", "median_hearings", "p_substantive",
                "fail_attendance", "fail_preparation", "fail_process", "fail_other"]]


def p_happen(p_sub: float, f_att: float, f_proc: float, f_other: float) -> float:
    """P(hearing actually happens / is heard). Heard = substantive OR heard-but-unprepared."""
    return p_sub + (1 - p_sub) * (1 - f_att - f_proc - f_other)


def load_cases(roster_path: Path | str | None = None, as_of: str = "2026-09-24",
               data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Roster CSV -> DataFrame[Case]. TODO(Dev 1): richer parsing of last_hearing_summary."""
    roster_path = Path(roster_path) if roster_path else data_dir / "roster_sample_100.csv"
    r = pd.read_csv(roster_path, parse_dates=["filing_date"])
    ref = load_reference(data_dir)
    as_of_ts = pd.Timestamp(as_of)

    df = pd.DataFrame({
        "case_id": r["case_number"],
        "advocate_id": r["advocate_id"],
        "party_id": r["party_id"],
        "filing_date": r["filing_date"],
        "stage": r["current_stage"].map(norm),
        "next_purpose": r["purpose_of_next_hearing"].map(norm),
        "total_hearings": r["total_hearings_held"],
    })
    df["age_years"] = (as_of_ts - df["filing_date"]).dt.days / 365.25
    df["age_bucket"] = pd.cut(df["age_years"], AGE_BINS, labels=AGE_LABELS, right=False).astype(str)
    df["hearings_in_stage"] = [
        r.at[i, f"hearings_{p.lower()}"] if f"hearings_{p.lower()}" in r.columns else 0
        for i, p in enumerate(df["next_purpose"])
    ]

    per = ref.reindex(df["next_purpose"]).reset_index(drop=True)
    for col in ["est_minutes", "p_substantive", "fail_attendance", "fail_preparation",
                "fail_process", "fail_other"]:
        df[col] = per[col].values
    df["p_happen"] = [p_happen(s, a, pr, o) for s, a, pr, o in
                      zip(df.p_substantive, df.fail_attendance, df.fail_process, df.fail_other)]

    summary = r["last_hearing_summary"].fillna("")
    df["att_mult"] = summary.map(attendance_multiplier)
    df["has_efiling"] = efiling.has_signals(r)
    if df["has_efiling"].iloc[0]:
        m = efiling.process_wait_multiplier(r).values
        df["process_wait_mult"] = m / m.mean()   # relative: keeps the observed average return time
        df["att_mult"] *= efiling.attendance_multiplier(r).values
    else:
        df["process_wait_mult"] = 1.0
    df["att_mult"] /= df["att_mult"].mean()   # relative: keeps the roster-wide no-show rate as observed

    orders = pd.DataFrame([classify(t) for t in summary])
    for col in ["last_event", "waiting_on", "readiness", "last_chance", "non_compliance", "absent_parties"]:
        df[col] = orders[col].values
    df["readiness"] = np.where(df["last_chance"], np.minimum(df["readiness"], 0.5), df["readiness"])
    df["part_heard"] = df["last_event"] == "part_heard"
    # warrant stage: blocked until the warrant is executed, unless the order says served
    warrant_wait = (df["next_purpose"] == "WARRANT") & ~df["last_event"].isin(["process_served", "external_pending"])
    blocked = orders["blocked"].values | warrant_wait
    df["prereq_ok"] = ~blocked
    df["prereq_reason"] = np.where(warrant_wait & ~orders["blocked"].values, "warrant execution",
                                   np.where(blocked, df["waiting_on"], ""))
    df["readiness"] = np.where(blocked, 0.0, df["readiness"])
    df["prep_mult"] = 1.5 - df["readiness"]
    df["prep_mult"] /= df["prep_mult"].mean()

    # verdict already on record but next purpose still says judgement -> treat as disposed
    done = (df["last_event"] == "verdict_recorded") & (df["next_purpose"] == "JUDGEMENT")
    df["data_note"] = np.where(done, "verdict already recorded; next purpose said JUDGEMENT - treated as disposed", "")
    df.loc[done, "next_purpose"] = DISPOSED
    df.loc[done, "stage"] = DISPOSED

    df["is_old"] = df["age_years"] >= 4
    # stuck = already at/above the typical number of hearings for this stage, and the last one didn't move it
    moving = df["last_event"].isin(["progressed", "part_heard", "heard_for_judgment", "process_served"])
    df["is_stuck"] = (df["hearings_in_stage"] >= np.maximum(2, per["median_hearings"].values)) & ~moving
    df["repeat_adj"] = df["last_chance"] | df["non_compliance"] | (
        df["hearings_in_stage"] >= 2 * per["median_hearings"].values)
    df["first_scheduled"] = pd.NaT
    df["last_heard"] = pd.NaT
    df["last_summary"] = summary
    df["visit"] = visit_label(df["hearings_in_stage"]).values
    stages_done = (r[[c for c in r.columns if c.startswith("hearings_")]] > 0).sum(axis=1)
    df["adjournments_est"] = (df["total_hearings"] - stages_done).clip(lower=0).values
    rem = [remaining_work(p, st, n, ref) for p, st, n in zip(df["next_purpose"], df["stage"], df["hearings_in_stage"])]
    df["remaining_hearings_est"] = [h for h, _ in rem]
    df["remaining_minutes_est"] = [m for _, m in rem]
    order = LIFECYCLE + sorted(SIDE_TYPES)
    df["history"] = [
        "|".join(f"{p}:{int(r.at[i, 'hearings_' + p.lower()])}" for p in order
                 if f"hearings_{p.lower()}" in r.columns and r.at[i, f"hearings_{p.lower()}"] > 0)
        for i in range(len(r))
    ]
    return df[CASE_COLUMNS]


def remaining_work(purpose: str, stage: str, done_here: int, ref: pd.DataFrame) -> tuple[float, float]:
    """Median hearings and minutes left to disposal along the core path."""
    if purpose == DISPOSED:
        return 0.0, 0.0
    main = purpose if purpose in LIFECYCLE else (stage if stage in LIFECYCLE else "ADMISSION")
    path = [p for p in CORE_PATH if LIFECYCLE.index(p) > LIFECYCLE.index(main)]
    here = max(1.0, ref.at[main, "median_hearings"] - done_here)
    hearings = here + sum(ref.at[p, "median_hearings"] for p in path)
    minutes = here * ref.at[main, "est_minutes"] + sum(ref.at[p, "median_hearings"] * ref.at[p, "est_minutes"] for p in path)
    if purpose in SIDE_TYPES:
        hearings += 1
        minutes += ref.at[purpose, "est_minutes"]
    return float(hearings), float(minutes)


def validate_cases(df: pd.DataFrame) -> list[str]:
    """Contract check for any roster fed to the engine. Empty list = OK."""
    problems = [f"missing column: {c}" for c in CASE_COLUMNS if c not in df.columns]
    if problems:
        return problems
    active = df[df["next_purpose"] != DISPOSED]
    unknown = set(active["next_purpose"]) - set(LIFECYCLE) - SIDE_TYPES
    if unknown:
        problems.append(f"unknown purposes: {sorted(unknown)}")
    for c in ["p_substantive", "readiness", "fail_attendance", "fail_preparation", "fail_process", "fail_other"]:
        bad = active[(active[c] < 0) | (active[c] > 1) | active[c].isna()]
        if len(bad):
            problems.append(f"{c} outside [0,1] for {len(bad)} cases")
    if df["case_id"].duplicated().any():
        problems.append("duplicate case_id")
    if (df["age_years"] < 0).any():
        problems.append("filing_date in the future")
    return problems


OUTCOMES = ["substantive", "attendance", "preparation", "process", "other"]


def outcome_probs(case, cfg: dict, prereq_ready: bool, attendance_mult: float = 1.0,
                  prep_mult: float = 1.0) -> dict:
    """P(each outcome) for one listing of `case`. Shared by the scorer and the simulator.

    - prerequisites not ready -> the hearing fails on process, full stop
    - prerequisites ready     -> process failures drop out, the rest renormalise
    - summary_mandate         -> case brief: prep failures on old / late-stage cases cut
    - attendance_mult         -> hook for L3 agents / incentives (1.0 = observed data)
    """
    if not prereq_ready:
        return {"substantive": 0.0, "attendance": 0.0, "preparation": 0.0, "process": 1.0, "other": 0.0}
    ps = case["p_substantive"]
    q = 1 - ps
    att = q * case["fail_attendance"] * case.get("att_mult", 1.0) * attendance_mult
    prep = q * case["fail_preparation"] * case.get("prep_mult", 1.0) * prep_mult
    other = q * case["fail_other"]
    if cfg.get("summary_mandate") and needs_brief(case):
        moved = prep * cfg.get("summary_prep_reduction", 0.5)
        prep, ps = prep - moved, ps + moved
    total = ps + att + prep + other
    return {"substantive": ps / total, "attendance": att / total, "preparation": prep / total,
            "process": 0.0, "other": other / total}


def outcome_probs_df(df: pd.DataFrame, cfg: dict, ready: pd.Series) -> pd.DataFrame:
    """Vectorised outcome_probs for ranking thousands of cases per day (same maths)."""
    ps = df["p_substantive"].astype(float)
    q = 1 - ps
    att = q * df["fail_attendance"] * (df["att_mult"] if "att_mult" in df else 1.0)
    prep = q * df["fail_preparation"] * (df["prep_mult"] if "prep_mult" in df else 1.0)
    other = q * df["fail_other"]
    if cfg.get("summary_mandate"):
        mask = (df["is_old"] | df["next_purpose"].isin(LATE_STAGES)).astype(float)
        moved = prep * cfg.get("summary_prep_reduction", 0.5) * mask
        prep, ps = prep - moved, ps + moved
    total = ps + att + prep + other
    out = pd.DataFrame({"substantive": ps / total, "attendance": att / total,
                        "preparation": prep / total, "process": 0.0, "other": other / total},
                       index=df.index)
    out.loc[~ready.astype(bool)] = [0.0, 0.0, 0.0, 1.0, 0.0]
    return out


def happens(outcome: str) -> bool:
    """Heard (consumes real time) = substantive, or heard-but-unprepared."""
    return outcome in ("substantive", "preparation")


def advance(purpose: str, stage: str) -> tuple[str, str]:
    """Next (purpose, stage) after a SUBSTANTIVE hearing. Returns DISPOSED after judgement."""
    if purpose in SIDE_TYPES:  # side application resolved -> back to the main stage
        return (stage if stage in LIFECYCLE else "ADMISSION"), stage
    if purpose == "JUDGEMENT":
        return DISPOSED, DISPOSED
    if purpose in ("APPEARANCE", "WARRANT"):  # accused appeared -> plea
        return "PLEA", "PLEA"
    if purpose == "ADMISSION":  # delay condonation only when filed late; skip by default
        return "COGNIZANCE", "COGNIZANCE"
    nxt = LIFECYCLE[LIFECYCLE.index(purpose) + 1] if purpose in LIFECYCLE else stage
    return nxt, nxt


if __name__ == "__main__":
    c = load_cases()
    print(c.head().T)
    print(c[["prereq_ok", "is_old", "is_stuck", "repeat_adj"]].sum())
