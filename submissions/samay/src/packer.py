"""Set C: Day packing. Owner: Dev 1 (Engine).

build_causelist(ranked, day, cfg) -> DataFrame[CauselistRow]
1. Capacity = day_minutes x overbook_factor, in EXPECTED minutes (no-shows cost only a mention).
2. Guardrail first: fill old_case_min_share of capacity with the best 4+ yr cases.
3. Fill the rest with the best remaining cases of any age.
4. Put each case in its time block; cluster an advocate's cases back to back; give est. start time.
"""
from __future__ import annotations

import pandas as pd

from config import GUARDRAILS

CAUSELIST_COLUMNS = ["date", "block", "slot", "est_start", "case_id", "purpose", "visit", "est_minutes",
                     "exp_minutes", "advocate_id", "age_years", "is_old", "p_sub_eff", "reason"]


def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(mins: float) -> str:
    mins = int(round(mins))
    return f"{mins // 60:02d}:{mins % 60:02d}"


def _fits(block: dict, is_old: bool) -> bool:
    return block["filter"] == "all" or (block["filter"] == "old") == bool(is_old)


def select(ranked: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    cap = cfg["day_minutes"] * cfg["overbook_factor"]
    old_cap = cap * cfg["old_case_min_share"]
    # The guardrail quota is filled by its OWN fixed ranking - oldest-weighted - so a judge's
    # age preference (e.g. fresh-first) can't starve the 5+ year cases inside the quota.
    guard_w = GUARDRAILS["guardrail_age_weight"]
    old_part = ranked[ranked["is_old"]]
    if cfg.get("ranking", "hybrid") == "samay":
        judge_age = (1 + cfg["age_weight"] * old_part["age_years"]).clip(lower=0.1)
        guard_age = (1 + max(guard_w, cfg["age_weight"]) * old_part["age_years"])
        # keep every other signal in the judge's score (readiness, part-heard, purpose days); swap only the age term
        guard_order = (old_part["score"] / judge_age * guard_age).sort_values(ascending=False).index
    else:   # the 0-100 score already carries a fixed 35-point age factor
        guard_order = old_part["score"].sort_values(ascending=False).index
    chosen, taken, used = [], set(), 0.0
    # Liberty lane (teammate's R3): bail matters are always listed, ahead of everything else
    if cfg.get("bail_liberty_lane", True):
        for k in ranked.index[ranked["next_purpose"] == "BAIL"]:
            m = ranked.at[k, "exp_minutes"]
            if used + m <= cap:
                chosen.append(k); taken.add(k); used += m
    # No case waits forever (teammate's R7): overdue by max_overdue_days -> listed, up to a share of the day
    max_over = cfg.get("max_overdue_days")
    if max_over and "overdue_days" in ranked:
        forced_cap = used + cap * cfg.get("overdue_share", 0.2)
        for k in ranked.index[(ranked["overdue_days"] >= max_over) & ~ranked.index.isin(list(taken))]:
            m = ranked.at[k, "exp_minutes"]
            if used + m <= forced_cap:
                chosen.append(k); taken.add(k); used += m
    old_cap = used + old_cap
    for k in guard_order:                                          # guardrail quota
        if k in taken:
            continue
        m = ranked.at[k, "exp_minutes"]
        if used + m <= old_cap:
            chosen.append(k); taken.add(k); used += m
    idx = ranked.index.tolist()
    em = ranked["exp_minutes"].tolist()
    for k, m in zip(idx, em):                                      # best of the rest, judge's ranking
        if used >= cap - 2:
            break
        if k not in taken and used + m <= cap:
            chosen.append(k); used += m
    return ranked.loc[chosen]


def build_causelist(ranked: pd.DataFrame, day: pd.Timestamp, cfg: dict) -> pd.DataFrame:
    if ranked.empty:
        return pd.DataFrame(columns=CAUSELIST_COLUMNS)
    picked = select(ranked, cfg)
    blocks = cfg["blocks"]
    room = [(_mins(b["end"]) - _mins(b["start"])) * cfg["overbook_factor"] for b in blocks]

    assign = {i: [] for i in range(len(blocks))}
    for idx, row in picked.iterrows():
        order = sorted(range(len(blocks)), key=lambda i: not _fits(blocks[i], row["is_old"]))
        target = next((i for i in order if room[i] >= row["exp_minutes"]), order[0])
        room[target] -= row["exp_minutes"]
        assign[target].append(idx)

    rows = []
    for i, block in enumerate(blocks):
        part = picked.loc[assign[i]]
        if part.empty:
            continue
        if cfg["cluster_by_advocate"]:
            best = part.groupby("advocate_id")["score"].transform("max")
            part = part.assign(_g=best).sort_values(["_g", "advocate_id", "score"], ascending=[False, True, False])
        t = _mins(block["start"])
        for _, c in part.iterrows():
            rows.append({
                "date": day.date(), "block": block["name"], "slot": f"{block['start']}-{block['end']}",
                "est_start": _hhmm(t), "case_id": c["case_id"], "purpose": c["next_purpose"],
                "visit": c.get("visit", ""),
                "est_minutes": c["est_minutes"], "exp_minutes": round(c["exp_minutes"], 1),
                "advocate_id": c["advocate_id"], "age_years": round(c["age_years"], 1),
                "is_old": c["is_old"], "p_sub_eff": round(c["p_sub_eff"], 2), "reason": c["reason"],
            })
            t += c["exp_minutes"]
    return pd.DataFrame(rows, columns=CAUSELIST_COLUMNS)
