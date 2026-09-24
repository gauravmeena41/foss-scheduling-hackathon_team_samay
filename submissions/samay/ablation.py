"""What each lever adds, stage by stage.   python ablation.py --roster <3000.csv>

Answers "the gate helps early stages — what about evidence and arguments?"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from config import make_config  # noqa: E402
from metrics import compute  # noqa: E402
from model import load_cases  # noqa: E402
from simulate import run  # noqa: E402

GROUPS = {
    "Early (admission to warrant)": ["ADMISSION", "DELAY_CONDONATION_HEARING", "COGNIZANCE", "APPEARANCE", "WARRANT"],
    "Middle (plea to evidence)": ["PLEA", "EXAMINATION_UNDER_S351_BNSS", "EVIDENCE_COMPLAINANT", "EVIDENCE_ACCUSED"],
    "Late (arguments, judgement)": ["ARGUMENTS", "JUDGEMENT"],
}

SCENARIOS = {
    "Baseline (60/day, 60-day gap)": ("baseline", {}),
    "+ Packing & process gate": ("samay", {"summary_mandate": False, "readiness_confirmation": False}),
    "+ Readiness confirmation": ("samay", {"summary_mandate": False, "readiness_confirmation": True}),
    "+ Case brief": ("samay", {"summary_mandate": True, "readiness_confirmation": False}),
    "All levers (Samay)": ("samay", {"summary_mandate": True, "readiness_confirmation": True}),
    "All levers, no e-filing signals": ("samay", {"summary_mandate": True, "readiness_confirmation": True,
                                                  "use_efiling_signals": False}),
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--efiling", action="store_true", help="add synthetic e-filing signals to the roster first")
    p.add_argument("--roster", default=None)
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    if a.efiling:
        import tempfile

        import pandas as pd
        from efiling import enrich
        from model import DATA_DIR
        tmp = Path(tempfile.gettempdir()) / "samay_roster_efiling.csv"
        enrich(pd.read_csv(a.roster or DATA_DIR / "roster_sample_100.csv")).to_csv(tmp, index=False)
        a.roster = str(tmp)
    cases = load_cases(a.roster)
    rows = []
    for name, (policy, over) in SCENARIOS.items():
        cfg = make_config(**over)
        h, d, _, s = run(cases, policy, cfg, days=a.days, seed=a.seed)
        m = compute(h, d, s, cfg)
        listed = h[h["listed"]]
        row = {"scenario": name, "effective/day": round(m["Effective / day"], 1),
               "reach": f"{m['Reach rate']:.0%}", "5+ advanced": f"{m['Backlog 5+ advanced']:.0%}",
               "wasted trips": m["Wasted trips"], "declined early": m["Declined in advance"]}
        for g, purposes in GROUPS.items():
            part = listed[listed["purpose"].isin(purposes)]
            row[f"{g.split()[0]} eff/day"] = round(part["substantive"].sum() / max(1, len(d)), 1)
        rows.append(row)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
