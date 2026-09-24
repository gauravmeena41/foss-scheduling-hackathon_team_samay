"""E-filing signals (Set A extension). Owner: Dev 1.

DRISTI's e-filing flow (s.138 NI Act) already captures, per accused, things that predict how
long summons / warrant service will take. The hackathon roster doesn't carry them, so
`enrich()` adds SYNTHETIC values (clearly assumptions) to show what the engine does with them.
Field names follow the e-filing handover IDs.

  accused_addresses       ACC-8..12  number of addresses on file (summons goes to each)
  contact_known           ACC-6/7    phone or email known (else a declaration was filed)
  summons_rounds_prepaid  PAY-10     1-4 rounds paid upfront -> court issues without a payment task
  epost_prepaid           PAY-14/15  delivery prepaid by e-post
  accused_in_jurisdiction ACC-24     resides within the court's jurisdiction
  adr_opt_in              PRY-5      complainant willing to settle through ADR
  complainant_type        LIT-2      Individual / Institution
"""
from __future__ import annotations

import numpy as np
import pandas as pd

EFILING_COLUMNS = ["accused_addresses", "contact_known", "summons_rounds_prepaid", "epost_prepaid",
                   "accused_in_jurisdiction", "adr_opt_in", "complainant_type"]

# multipliers on the mean process-return time (assumptions, stated in SUBMISSION.md)
NO_CONTACT = 1.6          # no phone/email -> service by post only, more returns unclaimed
EXTRA_ADDRESS = 0.85      # each extra address: another chance to serve (floored below)
PREPAID = 0.7             # prepaid rounds + e-post: issued the same day, no pending payment task
OUT_OF_JURISDICTION = 1.3 # service across districts takes longer
NO_SHOW_OUTSIDE = 1.2     # accused living outside the jurisdiction misses more hearings


def enrich(roster: pd.DataFrame, seed: int = 7) -> pd.DataFrame:
    """Add synthetic e-filing columns. Distributions are assumptions, not observed data."""
    rng = np.random.default_rng(seed)
    n = len(roster)
    out = roster.copy()
    out["accused_addresses"] = rng.choice([1, 2, 3], n, p=[0.6, 0.3, 0.1])
    out["contact_known"] = rng.random(n) < 0.7
    out["summons_rounds_prepaid"] = rng.choice([1, 2, 3, 4], n, p=[0.55, 0.25, 0.1, 0.1])
    out["epost_prepaid"] = rng.random(n) < 0.6
    out["accused_in_jurisdiction"] = rng.random(n) < 0.75
    out["adr_opt_in"] = rng.random(n) < 0.3
    out["complainant_type"] = np.where(rng.random(n) < 0.45, "Institution", "Individual")
    return out


def has_signals(df: pd.DataFrame) -> bool:
    return all(c in df.columns for c in EFILING_COLUMNS)


def process_wait_multiplier(df: pd.DataFrame) -> pd.Series:
    """Per-case multiplier on the mean time for a summons / warrant to come back."""
    m = pd.Series(1.0, index=df.index)
    m *= np.where(df["contact_known"].astype(bool), 1.0, NO_CONTACT)
    m *= np.maximum(0.7, EXTRA_ADDRESS ** (df["accused_addresses"].astype(int) - 1))
    m *= np.where(df["epost_prepaid"].astype(bool) & (df["summons_rounds_prepaid"].astype(int) >= 2), PREPAID, 1.0)
    m *= np.where(df["accused_in_jurisdiction"].astype(bool), 1.0, OUT_OF_JURISDICTION)
    return m


def attendance_multiplier(df: pd.DataFrame) -> pd.Series:
    return pd.Series(np.where(df["accused_in_jurisdiction"].astype(bool), 1.0, NO_SHOW_OUTSIDE), index=df.index)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Add synthetic e-filing columns to a roster CSV")
    p.add_argument("roster")
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()
    enrich(pd.read_csv(a.roster), a.seed).to_csv(a.out, index=False)
    print(f"wrote {a.out}")
