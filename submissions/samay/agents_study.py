"""L3 study: how advocates respond to the court's incentives, and learn over the run.

python agents_study.py --roster <3000.csv>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from config import make_config  # noqa: E402
from metrics import compute  # noqa: E402
from model import load_cases  # noqa: E402
from simulate import run  # noqa: E402

SCENARIOS = {
    "Baseline court": ("baseline", {}),
    "Samay, no incentives": ("samay", {"reminders": False, "adjournment_cost": False}),
    "+ reminders": ("samay", {"reminders": True, "adjournment_cost": False}),
    "+ cost for on-the-day adjournment": ("samay", {"reminders": False, "adjournment_cost": True}),
    "+ both": ("samay", {"reminders": True, "adjournment_cost": True}),
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--roster", default=None)
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    cases = load_cases(a.roster)
    rows = []
    for name, (policy, over) in SCENARIOS.items():
        cfg = make_config(agents=True, **over)
        h, d, _, s = run(cases, policy, cfg, days=a.days, seed=a.seed)
        m = compute(h, d, s, cfg)
        pool = s.attrs["agents"]
        by = {}
        for g in pool.agents.values():
            by.setdefault(g.personality, []).append(g.prep)
        listed = h[h["listed"]]
        rows.append({
            "scenario": name,
            "effective/day": round(m["Effective / day"], 1),
            "on-day 'not prepared'": int((listed["failure_reason"] == "preparation").sum()),
            "admitted early": m["Declined in advance"],
            "wasted trips": m["Wasted trips"],
            "dilatory prep at end": f"{np.mean(by.get('dilatory', [np.nan])):.0%}",
            "overloaded prep at end": f"{np.mean(by.get('overloaded', [np.nan])):.0%}",
        })
    print(f"Advocates: {pool.mix()}  (start: dilatory 45% prepared, overloaded 65%, diligent 90%)\n")
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
