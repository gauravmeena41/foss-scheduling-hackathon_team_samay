"""Set G: Insights UI. Owner: Dev 3.   streamlit run app.py"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from config import GUARDRAILS, PRESETS, make_config  # noqa: E402
from metrics import PERCENT, compute  # noqa: E402
from model import DATA_DIR, load_cases  # noqa: E402
from simulate import run  # noqa: E402

st.set_page_config(page_title="Samay — court scheduler", layout="wide")


@st.cache_data(show_spinner=False)
def roster_path(n_cases: int) -> str:
    if n_cases == 100:
        return str(DATA_DIR / "roster_sample_100.csv")
    spec = importlib.util.spec_from_file_location("gen", DATA_DIR.parent / "scripts" / "generate_roster.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    out = HERE / f".cache_roster_{n_cases}.csv"
    gen.generate(n_cases, 42, str(DATA_DIR / "roster_sample_100.csv")).to_csv(out, index=False)
    return str(out)


@st.cache_data(show_spinner="Simulating the court…")
def simulate(path: str, policy: str, cfg_items: tuple, days: int, seed: int):
    cfg = thaw(cfg_items)
    cases = load_cases(path)
    h, d, lists, s = run(cases, policy, cfg, days=days, seed=seed)
    return h, d, lists, s, compute(h, d, s, cfg)


def freeze(cfg: dict) -> tuple:
    return tuple((k, repr(v) if isinstance(v, (list, dict)) else v) for k, v in sorted(cfg.items()))


def thaw(items: tuple) -> dict:
    import ast
    return {k: ast.literal_eval(v) if isinstance(v, str) and v[:1] in "[{" else v for k, v in items}


# ---------------- sidebar: the judge's controls ----------------
with st.sidebar:
    st.header("Docket")
    n_cases = st.select_slider("Roster size", [100, 500, 1000, 3000], value=1000)
    days = st.slider("Working days to simulate", 10, 83, 60)
    seed = st.number_input("Seed", value=42, step=1)

    st.header("Judge's rules")
    preset = st.selectbox("Preset", list(PRESETS))
    base = make_config(preset)
    overbook = st.slider("Overbooking factor", 0.8, 2.0, float(base["overbook_factor"]), 0.05)
    old_share = st.slider("Share of day for 4+ yr cases", 0.0, 0.9, float(PRESETS[preset].get(
        "old_case_min_share", base["old_case_min_share"])), 0.05)
    age_w = st.slider("Age weight in ranking", -0.3, 1.0, float(base["age_weight"]), 0.05)
    gate = st.toggle("Don't list until prerequisites are met", base["gate_prerequisites"])
    cluster = st.toggle("Cluster by advocate", base["cluster_by_advocate"])
    weekly = st.toggle("Carry unreached cases to same weekday next week", base["carry_forward_weekly"])
    summary = st.toggle("Mandatory case summary for old cases", base["summary_mandate"])
    agents = st.toggle("L3: advocate agents", False)
    enforce = st.toggle("Enforce ageing-case guardrail", True,
                        help=f"Floor: {GUARDRAILS['old_case_min_share_floor']:.0%}. Turn off only to see its cost.")

cfg = make_config(preset, enforce_guardrails=enforce, overbook_factor=overbook, old_case_min_share=old_share,
                  age_weight=age_w, gate_prerequisites=gate, cluster_by_advocate=cluster,
                  carry_forward_weekly=weekly, summary_mandate=summary, agents=agents)
path = roster_path(n_cases)
key = freeze(cfg)
bh, bd, bl, bs, bm = simulate(path, "baseline", key, days, int(seed))
sh, sd, sl, ss, sm = simulate(path, "samay", key, days, int(seed))

# ---------------- header ----------------
st.title("Samay — a court day that runs to plan")
st.caption(f"{n_cases} cases · {len(sd)} working days · preset: {preset}. Baseline = list 60/day, flat 60-day gap.")
if cfg["guardrail_clamped"]:
    st.warning(f"Guardrail: ageing-case share raised to {cfg['old_case_min_share']:.0%}. "
               "Old cases can't be deprioritised below the floor.")
if not enforce:
    st.error("Guardrail OFF — showing what this rule would cost the backlog.")

KEY = ["Effective / day", "Reach rate", "Utilisation", "Backlog 5+ advanced", "Predictability (days to hearing)",
       "Started within slot", "Next-date sensible", "Wasted trips"]
cols = st.columns(4)
for i, k in enumerate(KEY):
    fmt = (lambda v: f"{v:.0%}") if k in PERCENT else (lambda v: f"{v:,.1f}" if isinstance(v, float) else f"{v:,}")
    delta = sm[k] - bm[k]
    dfmt = f"{delta:+.0%}" if k in PERCENT else f"{delta:+,.1f}"
    inverse = k in ("Predictability (days to hearing)", "Wasted trips")
    cols[i % 4].metric(k, fmt(sm[k]), f"{dfmt} vs baseline", delta_color="inverse" if inverse else "normal")

tab1, tab2, tab3, tab4 = st.tabs(["Backlog over time", "Today's causelist", "At-risk cases", "All metrics"])

with tab1:
    trend = pd.concat([bd.assign(policy="Baseline"), sd.assign(policy="Samay")])
    c1, c2 = st.columns(2)
    c1.subheader("Open 5+ year cases")
    c1.line_chart(trend.pivot(index="date", columns="policy", values="open_5plus"))
    c2.subheader("Effective hearings per day")
    c2.line_chart(trend.pivot(index="date", columns="policy", values="substantive"))

with tab2:
    day = st.selectbox("Day", sorted(sl["date"].unique()))
    today = sl[sl["date"] == day]
    st.caption(f"{len(today)} listed · expected {today['exp_minutes'].sum():.0f} of {cfg['day_minutes']} min")
    st.dataframe(today[["block", "est_start", "case_id", "purpose", "advocate_id", "age_years", "p_sub_eff",
                        "reason"]], hide_index=True, width="stretch")

with tab3:
    open_ = ss[ss["next_purpose"] != "DISPOSED"]
    risk = open_[(open_["is_old"] & open_["first_heard"].isna()) | open_["repeat_adj"] | open_["is_stuck"]]
    st.caption(f"{len(risk)} open cases are old-and-unheard, repeatedly adjourned, or stuck at one stage")
    st.dataframe(risk[["case_id", "age_years", "next_purpose", "hearings_in_stage", "times_listed", "is_old",
                       "repeat_adj", "is_stuck", "due_date"]].sort_values("age_years", ascending=False),
                 hide_index=True, width="stretch")

with tab4:
    st.dataframe(pd.DataFrame({"metric": list(sm), "baseline": list(bm.values()), "samay": list(sm.values())}),
                 hide_index=True, width="stretch")
