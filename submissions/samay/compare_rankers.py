"""Three rankers on the same docket: ours (value per minute), the teammate's 0-100 priority, and the hybrid.

python compare_rankers.py --roster <3000.csv> --seeds 3 [--offset 3 --append]   -> rankers.md
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

MODES = {"Ours — value per minute": "samay", "Teammate — 0-100 priority": "teammate",
         "Hybrid — priority × P(moves) ÷ minutes": "hybrid"}
KEEP = ["Effective / day", "Reach rate", "Backlog 5+ advanced", "Backlog 4+ heard", "Disposed", "Wasted trips",
        "Date slippage (days)"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--roster", default=None)
    p.add_argument("--seeds", type=int, default=3)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--append", action="store_true")
    p.add_argument("--out", default=str(HERE / "rankers"))
    a = p.parse_args()
    cases = load_cases(a.roster)
    rows = []
    for seed in range(a.offset, a.offset + a.seeds):
        for name, mode in MODES.items():
            cfg = make_config(ranking=mode)
            h, d, _, s = run(cases, "samay", cfg, seed=seed)
            rows.append({"seed": seed, "ranker": name, **{k: compute(h, d, s, cfg)[k] for k in KEEP}})
    raw = pd.DataFrame(rows)
    csv = Path(a.out + ".csv")
    if a.append and csv.exists():
        raw = pd.concat([pd.read_csv(csv), raw], ignore_index=True)
    raw.to_csv(csv, index=False)
    g = raw.groupby("ranker", sort=False)[KEEP].mean()
    fmt = {k: (lambda v: f"{v:.0%}") if k in ("Reach rate", "Backlog 5+ advanced", "Backlog 4+ heard")
           else (lambda v: f"{v:,.1f}") for k in KEEP}
    lines = [f"# Rankers compared — {len(cases)} cases, 60 sitting days, {raw['seed'].nunique()} seeds (mean)", "",
             "| Ranker | " + " | ".join(KEEP) + " |", "|---" * (len(KEEP) + 1) + "|"]
    lines += [f"| {r} | " + " | ".join(fmt[k](g.at[r, k]) for k in KEEP) + " |" for r in g.index]
    Path(a.out + ".md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
