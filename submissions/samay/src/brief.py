"""Case brief: a one-page, always-current summary of a case for the judge. Owner: Dev 1 / Dev 3.

Starts from what the file already holds (filing date, stage history, last order sheet)
and grows with every hearing. In DRISTI it would be seeded from the e-filing synopsis
(parties, cheque, dishonour, notice, cause of action) and appended from each order sheet.
Advocates confirm the agreed facts and mark what is disputed before the hearing.
"""
from __future__ import annotations

import re

import pandas as pd

from model import LATE_STAGES, LIFECYCLE

# What must be true before a hearing of this purpose can be substantive.
# Each item: (label, regex that means "done" in the order text, regex that means "pending")
CHECKLIST = {
    "ADMISSION": [("Complaint and documents complete", None, r"defect|return")],
    "DELAY_CONDONATION_HEARING": [("Objection to delay filed by accused", r"objection", None)],
    "COGNIZANCE": [("Enquiry / records received", None, r"awaiting|report")],
    "APPEARANCE": [("Summons served on accused", r"served", r"summons|take steps|unclaimed|notice")],
    "WARRANT": [("Warrant executed / accused produced", r"executed|appeared", r"nbw|warrant|take steps")],
    "PLEA": [("Accused present for plea", r"accused present", r"absent")],
    "EXAMINATION_UNDER_S351_BNSS": [("Accused present for examination", r"accused present", None),
                                    ("Defence witness list filed", r"witness list", None)],
    "EVIDENCE_COMPLAINANT": [("Proof affidavit filed", r"proof affidavit", None),
                             ("Complainant witnesses summoned / present", r"examined|present", r"not ready"),
                             ("Accused's counsel ready to cross-examine", r"cross-examined", r"not ready for cross")],
    "EVIDENCE_ACCUSED": [("Defence witness list filed", r"witness list|dw1|examined", None),
                         ("Defence witnesses summoned / present", r"examined", r"last chance|not ready")],
    "ARGUMENTS": [("Evidence closed", r"evidence closed|for arguments", None),
                  ("Case brief confirmed by both sides", None, None),
                  ("Written arguments filed", r"written arguments", None)],
    "JUDGEMENT": [("Arguments closed", r"heard|for judgment", None)],
    "BAIL": [("Bail application + surety ready", r"surety", None)],
    "REPORTS": [("Mediation / report received", r"report received|settled", r"referred|mediation")],
    "APPLICATION_REVIEW": [("Objections to application filed", r"objection", None)],
}


def _status(text: str, done: str | None, pending: str | None) -> str:
    t = text.lower()
    if pending and re.search(pending, t):
        return "pending"
    if done and re.search(done, t):
        return "done"
    return "confirm"


def checklist(case) -> list[tuple[str, str]]:
    text = str(case.get("last_summary", ""))
    items = [(label, _status(text, d, p)) for label, d, p in CHECKLIST.get(case["next_purpose"], [])]
    if not case.get("prereq_ok", True):
        items.insert(0, ("Process returned (summons / warrant)", "pending"))
    return items


def readiness(case) -> float:
    """Share of checklist items not known to be pending (0-1). 'confirm' counts as half."""
    items = checklist(case)
    if not items:
        return 1.0
    score = {"done": 1.0, "confirm": 0.5, "pending": 0.0}
    return sum(score[s] for _, s in items) / len(items)


def _journey(history: str, current: str) -> str:
    parts = []
    for chunk in filter(None, str(history).split("|")):
        p, n = chunk.split(":")
        label = p.replace("_", " ").title().replace("S351 Bnss", "s.351 BNSS")
        parts.append(f"{label} ×{n}" + (" ◀ now" if p == current else ""))
    return " → ".join(parts) or "—"


def build_brief(case) -> str:
    """Markdown brief for one case (a row of the Case table / simulator state)."""
    purpose = case["next_purpose"]
    lines = str(case.get("last_summary", "")).split("\n")
    present = next((l.split(":", 1)[1].strip() for l in lines if l.lower().startswith("present")), "—")
    absent = next((l.split(":", 1)[1].strip() for l in lines if l.lower().startswith("absent")), "—")
    order = lines[-1].strip() if lines else "—"
    flags = []
    if case["is_old"]:
        flags.append(f"pending {case['age_years']:.1f} years")
    if case["repeat_adj"]:
        flags.append("repeatedly adjourned")
    if case["is_stuck"]:
        flags.append(f"{int(case['hearings_in_stage'])} hearings at this stage — above typical")
    icon = {"done": "✅", "pending": "⛔", "confirm": "❓"}
    items = checklist(case)
    stage_no = LIFECYCLE.index(purpose) + 1 if purpose in LIFECYCLE else None

    md = [
        f"### {case['case_id']} — next: {purpose.replace('_', ' ').title()}"
        + (f" (stage {stage_no} of 11)" if stage_no else ""),
        f"Filed {pd.Timestamp(case['filing_date']).date()} · {int(case['total_hearings'])} hearings so far · "
        f"advocate {case['advocate_id']}",
        "",
        "**Flags:** " + (" · ".join(flags) if flags else "none"),
        "",
        f"**Journey:** {_journey(case.get('history', ''), purpose)}",
        "",
        f"**Last hearing** — present: {present}; absent: {absent}",
        f"> {order}",
        "",
        f"**Before this hearing** (readiness {readiness(case):.0%})",
        *[f"- {icon[s]} {label}" for label, s in items],
    ]
    if purpose in LATE_STAGES or case["is_old"]:
        md += ["", "**For both counsel to confirm 2 days before:** agreed facts · disputed points · "
                   "documents relied on · witnesses still to be examined."]
    return "\n".join(md)


if __name__ == "__main__":
    from model import load_cases
    c = load_cases()
    print(build_brief(c.iloc[0]))
    print()
    print(build_brief(c[c.next_purpose == "ARGUMENTS"].iloc[0]))
