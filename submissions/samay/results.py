"""Monte Carlo results: every metric as mean ± sd over N seeds, baseline vs Samay.

python results.py --roster <3000.csv> --seeds 10          # writes results.csv + results.md
python results.py --roster <3000.csv> --seeds 5 --offset 5 --append   # add more seeds
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from config import PRESETS, make_config  # noqa: E402
from metrics import PERCENT, compute  # noqa: E402
from model import load_cases  # noqa: E402
from simulate import run  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--roster", default=None)
    p.add_argument("--preset", default="Recommended", choices=list(PRESETS))
    p.add_argument("--seeds", type=int, default=10)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--append", action="store_true")
    p.add_argument("--out", default=str(HERE / "results"))
    a = p.parse_args()

    cases = load_cases(a.roster)
    cfg = make_config(a.preset)
    rows = []
    for seed in range(a.offset, a.offset + a.seeds):
        for policy in ("baseline", "samay"):
            h, d, _, s = run(cases, policy, cfg, days=a.days, seed=seed)
            rows.append({"seed": seed, "policy": policy, **compute(h, d, s, cfg)})
    raw = pd.DataFrame(rows)
    csv = Path(a.out + ".csv")
    if a.append and csv.exists():
        raw = pd.concat([pd.read_csv(csv), raw], ignore_index=True)
    raw.to_csv(csv, index=False)

    metrics = [c for c in raw.columns if c not in ("seed", "policy")]
    g = raw.groupby("policy")[metrics].agg(["mean", "std"])

    def fmt(policy, m):
        mu, sd = g.loc[policy, (m, "mean")], g.loc[policy, (m, "std")]
        return f"{mu:.0%} ± {sd:.0%}" if m in PERCENT else f"{mu:,.1f} ± {sd:,.1f}"

    n = raw["seed"].nunique()
    lines = [f"# Results — {len(cases)} cases, {a.days} working days, {n} seeds, preset: {a.preset}", "",
             "| Metric | Baseline (60/day, 60-day gap) | Samay |", "|---|---|---|"]
    lines += [f"| {m} | {fmt('baseline', m)} | {fmt('samay', m)} |" for m in metrics]
    Path(a.out + ".md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
