"""Order-sheet classifier (part of Set A, case model). Owner: Dev 1.

Reads the last order text + Present/Absent lines of a case and returns what happened
and who the case is now waiting on. Rules are ordered; the first matching EVENT wins,
FLAGS are independent. Calibrated on all 35 distinct order texts in the sample roster.
"""
from __future__ import annotations

import re

# (event, waiting_on, pattern) - first match wins
EVENT_RULES = [
    ("verdict_recorded", "none", r"judgment pronounced|\bconvicted\b|\bacquitted\b"),
    ("external_pending", "mediation", r"mediation"),
    ("external_pending", "higher court", r"order of the hon'?ble|district court|high court"),
    ("process_awaiting", "witness summons", r"issue summons to witness"),
    ("process_awaiting", "court process",
     r"issue (?:by hand )?(?:nbw|warrant|summons|notice|dca notice)|await (?:summons|warrant|notice)"
     r"|for return of (?:warrant|summons|notice)|take steps"),
    ("process_served", "none", r"\bserved\b|deemed to be served"),
    ("objection_pending", "other side's objections", r"objection"),
    ("prep_failure", "counsel", r"not ready"),
    ("attendance_failure", "party", r"\babsent\b|shall be present|steps not taken"),
    ("part_heard", "none", r"heard from the side|for further hearing|for the hearing of"),
    ("heard_for_judgment", "judge", r"heard\.\s*for judgment|for judgment"),
    ("progressed", "none", r"examined|exhibits marked|pleaded|cognizance|satisfied|affidavit filed"),
]
FLAG_RULES = {
    "last_chance": r"last[\s-]chance",
    "non_compliance": r"steps not taken|repeated direction|despite sufficient opportunity|continuously absent",
}
# events after which the next hearing cannot be substantive until something outside the room happens
BLOCKING = {"process_awaiting", "external_pending"}
# readiness of the NEXT hearing implied by the last event (0 = blocked, 1 = ready to go)
READINESS = {
    "verdict_recorded": 1.0, "external_pending": 0.0, "process_awaiting": 0.0, "process_served": 0.9,
    "objection_pending": 0.5, "prep_failure": 0.4, "attendance_failure": 0.5, "part_heard": 1.0,
    "heard_for_judgment": 1.0, "progressed": 0.8, "listed": 0.6,
}


def _lines(summary: str) -> list[str]:
    return [l.strip() for l in str(summary).split("\n") if l.strip()]


def _who(lines: list[str], key: str) -> list[str]:
    line = next((l for l in lines if l.lower().startswith(key)), "")
    return [p.strip().lower() for p in line.split(":", 1)[1].split(",")] if ":" in line else []


def classify(summary: str) -> dict:
    lines = _lines(summary)
    order = lines[-1] if lines else ""
    t = order.lower()
    event, waiting = "listed", "none"
    for ev, who, pat in EVENT_RULES:
        if re.search(pat, t):
            event, waiting = ev, who
            break
    absent = _who(lines, "absent")
    return {
        "last_order": order,
        "last_event": event,
        "waiting_on": waiting,
        "blocked": event in BLOCKING,
        "readiness": READINESS[event],
        "absent_parties": ", ".join(p for p in absent if p in ("complainant", "accused")),
        **{k: bool(re.search(p, t)) for k, p in FLAG_RULES.items()},
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path

    import pandas as pd

    data = Path(__file__).resolve().parents[3] / "data" / "roster_sample_100.csv"
    r = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else data)
    out = pd.DataFrame([classify(s) for s in r["last_hearing_summary"].fillna("")])
    out["purpose"] = r["purpose_of_next_hearing"]
    print(out["last_event"].value_counts().to_string(), "\n")
    print(out.groupby(["last_event", "waiting_on"]).size().to_string(), "\n")
    print(out[["last_chance", "non_compliance", "blocked"]].sum().to_string())
