"""CLI: simulate baseline vs Samay, print the metrics, write proposed_schedule.csv.

python run.py                                  # 100-case sample, 60 working days
python run.py --roster ../../data/roster_3000.csv --preset "Justice Dimakar (clusterer)"
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from config import PRESETS, make_config  # noqa: E402
from metrics import compare, compute  # noqa: E402
from model import load_cases  # noqa: E402
from simulate import run  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--efiling", action="store_true", help="add synthetic e-filing signals to the roster first")
    p.add_argument("--roster", default=None, help="roster CSV (default: data/roster_sample_100.csv)")
    p.add_argument("--preset", default="Recommended", choices=list(PRESETS))
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--start", default="2026-09-24")
    p.add_argument("--agents", action="store_true", help="enable L3-lite advocate agents")
    p.add_argument("--out", default=str(HERE / "proposed_schedule.csv"))
    a = p.parse_args()

    t0 = time.time()
    if a.efiling:
        import tempfile

        import pandas as pd
        from efiling import enrich
        from model import DATA_DIR
        tmp = Path(tempfile.gettempdir()) / "samay_roster_efiling.csv"
        enrich(pd.read_csv(a.roster or DATA_DIR / "roster_sample_100.csv")).to_csv(tmp, index=False)
        a.roster = str(tmp)
    cases = load_cases(a.roster, as_of=a.start)
    cfg = make_config(a.preset, agents=a.agents)
    if cfg["guardrail_clamped"]:
        print(f"! Guardrail: old-case share raised to {cfg['old_case_min_share']:.0%} for preset '{a.preset}'")

    bh, bd, _, bs = run(cases, "baseline", cfg, a.start, a.days, a.seed)
    sh, sd, lists, ss = run(cases, "samay", cfg, a.start, a.days, a.seed)
    table = compare(compute(sh, sd, ss, cfg), compute(bh, bd, bs, cfg))
    print(f"\n{len(cases)} cases · {len(sd)} working days · preset: {a.preset}\n")
    print(table.to_string(index=False))

    lists.to_csv(a.out, index=False)
    print(f"\nWrote {len(lists)} listings to {a.out}  ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main()
