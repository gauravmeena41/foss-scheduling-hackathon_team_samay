"""Set C: Day packing. Owner: Dev 1 (Engine).

build_causelist(ranked, day, cfg) -> DataFrame[CauselistRow]
1. Capacity = day_minutes x overbook_factor, in EXPECTED minutes (no-shows cost only a mention).
2. Guardrail first: fill old_case_min_share of capacity with the best 4+ yr cases.
3. Fill the rest with the best remaining cases of any age.
4. Put each case in its time block; cluster an advocate's cases back to back; give est. start time.
"""
from __future__ import annotations

import pandas as pd

CAUSELIST_COLUMNS = ["date", "block", "slot", "est_start", "case_id", "purpose", "est_minutes",
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
    idx = ranked.index.tolist()
    em = ranked["exp_minutes"].tolist()
    old = ranked["is_old"].tolist()
    chosen, taken, used = [], set(), 0.0
    for i, (k, m, o) in enumerate(zip(idx, em, old)):             # guardrail quota
        if o and used + m <= old_cap:
            chosen.append(k); taken.add(i); used += m
    for i, (k, m) in enumerate(zip(idx, em)):                     # best of the rest
        if used >= cap - 2:
            break
        if i not in taken and used + m <= cap:
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
                "est_minutes": c["est_minutes"], "exp_minutes": round(c["exp_minutes"], 1),
                "advocate_id": c["advocate_id"], "age_years": round(c["age_years"], 1),
                "is_old": c["is_old"], "p_sub_eff": round(c["p_sub_eff"], 2), "reason": c["reason"],
            })
            t += c["exp_minutes"]
    return pd.DataFrame(rows, columns=CAUSELIST_COLUMNS)
