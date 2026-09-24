"""Quick checks on the engine's contracts.   python -m pytest tests -q"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import GUARDRAILS, make_config  # noqa: E402
from model import DATA_DIR, load_cases, load_reference, validate_cases  # noqa: E402
from next_date import Calendar, next_date  # noqa: E402
from orders import classify  # noqa: E402
from packer import build_causelist  # noqa: E402
from priority import rank  # noqa: E402
from simulate import init_state, run  # noqa: E402

DAY = pd.Timestamp("2026-09-24")


def _state(cfg):
    import numpy as np
    cases = load_cases()
    return init_state(cases, DAY, load_reference(), np.random.default_rng(0), cfg)


def test_sample_roster_is_valid():
    assert validate_cases(load_cases()) == []


def test_order_classifier_reads_real_orders():
    assert classify("Issue NBW to accused. Take steps. For return of warrant.")["blocked"]
    assert not classify("Summons served. For the appearance of the accused.")["blocked"]
    assert classify("Heard from the side of the complainant. For the hearing of the accused.")["last_event"] == "part_heard"
    assert classify("For defence evidence, last chance.")["last_chance"]


def test_causelist_fits_the_day_and_respects_the_guardrail():
    cfg = make_config("Justice Joshi (fresh first)")          # would starve old cases without the floor
    cl = build_causelist(rank(_state(cfg), DAY, cfg), DAY, cfg)
    assert cl["exp_minutes"].sum() <= cfg["day_minutes"] * cfg["overbook_factor"] + 1
    old_share = cl.loc[cl["is_old"], "exp_minutes"].sum() / cl["exp_minutes"].sum()
    assert old_share >= GUARDRAILS["old_case_min_share_floor"] - 0.1


def test_blocked_cases_are_not_listed():
    cfg = make_config()
    s = _state(cfg)
    cl = build_causelist(rank(s, DAY, cfg), DAY, cfg)
    assert not set(cl["case_id"]) & set(s.index[~s["prereq_ok"].astype(bool)])


def test_next_date_follows_the_reason():
    cfg, ref = make_config(), load_reference()
    cal = Calendar(DATA_DIR / "court_calendar.csv", ["2026-09-25"])      # judge on leave on the 25th
    court_side = next_date("EVIDENCE_COMPLAINANT", "other", DAY, cal, ref, cfg, detail="Court Holiday / No Sitting")
    assert court_side == pd.Timestamp("2026-09-28")                      # skips leave + weekend
    absent = next_date("EVIDENCE_COMPLAINANT", "attendance", DAY, cal, ref, cfg)
    prepared = next_date("EVIDENCE_COMPLAINANT", "preparation", DAY, cal, ref, cfg)
    assert absent < prepared


def test_simulation_beats_baseline_on_effective_hearings():
    cfg, cases = make_config(), load_cases()
    _, bd, _, _ = run(cases, "baseline", cfg, days=20)
    _, sd, _, _ = run(cases, "samay", cfg, days=20)
    assert sd["substantive"].sum() > bd["substantive"].sum()
