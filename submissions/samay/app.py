"""Samay dashboard (Set G).   streamlit run app.py

A live picture of the court for the judge and court master: what the rules cost,
what today looks like, which cases are drifting - not just a causelist.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from brief import build_brief  # noqa: E402
from config import GUARDRAILS, PRESETS, make_config  # noqa: E402
from efiling import enrich  # noqa: E402
from metrics import PERCENT, compute  # noqa: E402
from model import DATA_DIR, load_cases  # noqa: E402
from simulate import DURATION_SIGMA, run  # noqa: E402

st.set_page_config(page_title="Samay — court scheduler", layout="wide")


# ---------------------------------------------------------------- data + cached runs
@st.cache_data(show_spinner=False)
def roster_path(n_cases: int, efiling: bool) -> str:
    base = DATA_DIR / "roster_sample_100.csv"
    if n_cases == 100:
        df = pd.read_csv(base)
    else:
        spec = importlib.util.spec_from_file_location("gen", DATA_DIR.parent / "scripts" / "generate_roster.py")
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        df = gen.generate(n_cases, 42, str(base))
    if efiling:
        df = enrich(df)
    out = Path(tempfile.gettempdir()) / f"samay_roster_{n_cases}_{int(efiling)}.csv"
    df.to_csv(out, index=False)
    return str(out)


def freeze(cfg: dict) -> tuple:
    return tuple((k, repr(v) if isinstance(v, (list, dict)) else v) for k, v in sorted(cfg.items()))


def thaw(items: tuple) -> dict:
    return {k: ast.literal_eval(v) if isinstance(v, str) and v[:1] in "[{" else v for k, v in items}


@st.cache_data(show_spinner="Simulating the court…", max_entries=64)
def simulate(path: str, policy: str, cfg_items: tuple, days: int, seed: int):
    cfg = thaw(cfg_items)
    h, d, lists, s = run(load_cases(path), policy, cfg, days=days, seed=seed)
    pool = s.attrs.get("agents")
    agents_df = None
    if pool is not None:
        agents_df = pd.DataFrame([{"advocate": g.advocate_id, "personality": str(g.personality),
                                   "prepared": g.prep, "shows_up": g.show, "free_adjournments": g.adjourned_free}
                                  for g in pool.agents.values()])
    s = s.copy()
    s.attrs = {}
    return h, d, lists, s, compute(h, d, s, cfg), agents_df


@st.cache_data(show_spinner=False)
def initial_cases(path: str) -> pd.DataFrame:
    return load_cases(path).set_index("case_id", drop=False)


def fmt(k, v):
    if k in PERCENT:
        return f"{v:.0%}"
    return f"{v:,.1f}" if isinstance(v, float) else f"{v:,}"


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Docket")
    n_cases = st.select_slider("Roster size", [100, 500, 1000, 3000], value=3000,
                               help="3,000 = the case study's docket. Smaller rosters leave the baseline court idle for weeks.")
    days = st.slider("Working days to simulate", 10, 83, 60)
    seed = int(st.number_input("Seed", value=42, step=1))
    efiling_on = st.toggle("E-filing signals (synthetic)", False,
                           help="Addresses, contact known, prepaid summons/e-post, jurisdiction — predict process-return dates")

    st.header("Judge's rules")
    preset = st.selectbox("Preset", list(PRESETS))
    base = make_config(preset, enforce_guardrails=False)
    overbook = st.slider("Overbooking factor", 0.8, 2.0, float(base["overbook_factor"]), 0.05,
                         help="Listed expected minutes ÷ 420. Above 1 = planned no-shows.")
    old_share = st.slider("Share of day for 4+ yr cases", 0.0, 0.9, float(base["old_case_min_share"]), 0.05)
    age_w = st.slider("Age weight in ranking", -0.3, 1.0, float(base["age_weight"]), 0.05)
    gate = st.toggle("Don't list until prerequisites are met", base["gate_prerequisites"])
    cluster = st.toggle("Cluster by advocate", base["cluster_by_advocate"])
    weekly = st.toggle("Unreached → same weekday next week", base["carry_forward_weekly"])
    enforce = st.toggle("Enforce ageing-case guardrail", True,
                        help=f"Floor {GUARDRAILS['old_case_min_share_floor']:.0%} of the day. Off only to see its cost.")

    st.header("Preparedness levers")
    summary = st.toggle("Case brief (old / late-stage)", base["summary_mandate"])
    confirm = st.toggle("Readiness check 2 days before", base["readiness_confirmation"])
    agents_on = st.toggle("L3: advocate agents", True)
    reminders = st.toggle("Reminders to advocates", base["reminders"], disabled=not agents_on)
    cost = st.toggle("Cost for on-the-day adjournment", base["adjournment_cost"], disabled=not agents_on)

cfg = make_config(preset, enforce_guardrails=enforce, overbook_factor=overbook, old_case_min_share=old_share,
                  age_weight=age_w, gate_prerequisites=gate, cluster_by_advocate=cluster,
                  carry_forward_weekly=weekly, summary_mandate=summary, readiness_confirmation=confirm,
                  agents=agents_on, reminders=reminders, adjournment_cost=cost)
path = roster_path(n_cases, efiling_on)
key = freeze(cfg)
bh, bd, bl, bs, bm, _ = simulate(path, "baseline", key, days, seed)
sh, sd, sl, ss, sm, agents_df = simulate(path, "samay", key, days, seed)
initial = initial_cases(path)

# ---------------------------------------------------------------- header
st.title("Samay — a court day that runs to plan")
st.caption(f"{n_cases:,} cases · {len(sd)} working days · preset **{preset}** · "
           "baseline = list 60 a day, whatever gets listed gets attempted, flat 60-day next date")
if cfg["guardrail_clamped"]:
    st.warning(f"Guardrail: ageing-case share raised to {cfg['old_case_min_share']:.0%}. "
               "Old cases can't be deprioritised below the floor.")
if not enforce and old_share < GUARDRAILS["old_case_min_share_floor"]:
    st.error("Guardrail OFF — showing what this rule would cost the backlog.")

KEY = [("Effective / day", False), ("Reach rate", False), ("Backlog 5+ advanced", False),
       ("Date slippage (days)", True), ("Started within slot", False), ("Next-date sensible", False),
       ("Wasted trips", True), ("Utilisation", False)]
cols = st.columns(4)
for i, (k, lower_better) in enumerate(KEY):
    delta = sm[k] - bm[k]
    d = f"{delta:+.0%}" if k in PERCENT else f"{delta:+,.1f}"
    cols[i % 4].metric(k, fmt(k, sm[k]), f"{d} vs baseline", delta_color="inverse" if lower_better else "normal")

tabs = st.tabs(["Three judges", "Backlog & drift", "Today's causelist", "Case brief", "At-risk cases",
                "Advocates (L3)", "All metrics"])

# ---------------------------------------------------------------- 1. three judges
with tabs[0]:
    st.subheader("Same docket, each judge's rules — and what they cost")
    rows = []
    for name in PRESETS:
        for guarded in ([True, False] if "Joshi" in name else [True]):
            c = make_config(name, enforce_guardrails=guarded, agents=agents_on)
            _, _, _, _, m, _ = simulate(path, "samay", freeze(c), days, seed)
            label = name + ("" if guarded else " — guardrail off")
            rows.append({"rules": label, **{k: m[k] for k in
                         ["Effective / day", "Reach rate", "Backlog 5+ advanced", "Backlog 4+ heard",
                          "Date slippage (days)", "Started within slot", "Wasted trips"]}})
    rows.append({"rules": "Baseline court", **{k: bm[k] for k in rows[0] if k != "rules"}})
    comp = pd.DataFrame(rows).set_index("rules")
    c1, c2 = st.columns(2)
    c1.caption("Effective hearings per day")
    c1.bar_chart(comp["Effective / day"], horizontal=True)
    c2.caption("5+ year cases that moved at least one stage")
    c2.bar_chart(comp["Backlog 5+ advanced"], horizontal=True)
    st.dataframe(comp.style.format({k: "{:.0%}" for k in comp.columns if k in PERCENT} |
                                   {k: "{:,.1f}" for k in comp.columns if k not in PERCENT}),
                 width="stretch")
    st.caption("Fresh-first (Joshi) buys throughput with the old backlog; the guardrail puts a floor under that trade.")

# ---------------------------------------------------------------- 2. backlog & drift
with tabs[1]:
    trend = pd.concat([bd.assign(policy="Baseline"), sd.assign(policy="Samay")])
    c1, c2 = st.columns(2)
    c1.caption("Open 5+ year cases")
    c1.line_chart(trend.pivot(index="date", columns="policy", values="open_5plus"))
    c2.caption("Effective hearings per day")
    c2.line_chart(trend.pivot(index="date", columns="policy", values="substantive"))
    c3, c4 = st.columns(2)
    order = ["<1", "1-2", "2-3", "3-4", "4-5", "5+"]

    def open_by_age(state):
        o = state[state["next_purpose"] != "DISPOSED"]
        return o["age_bucket"].value_counts().reindex(order, fill_value=0)

    ages = pd.DataFrame({"Start": initial[initial["next_purpose"] != "DISPOSED"]["age_bucket"]
                         .value_counts().reindex(order, fill_value=0),
                         "Baseline end": open_by_age(bs), "Samay end": open_by_age(ss)})
    c3.caption("Open cases by age bucket")
    c3.bar_chart(ages, stack=False)
    work = pd.DataFrame({"hours of work left": [initial["remaining_minutes_est"].sum() / 60,
                                                ss[ss["next_purpose"] != "DISPOSED"]["remaining_minutes_est"].sum() / 60]},
                        index=["Start", "Samay end (estimate at start of run)"])
    c4.caption("Why the docket can't be 'cleared': median hearing-hours left to disposal vs court hours available")
    c4.metric("Median hearing-hours left in the docket", f"{initial['remaining_minutes_est'].sum() / 60:,.0f} h",
              f"court has {len(sd) * cfg['day_minutes'] / 60:,.0f} h in {len(sd)} days", delta_color="off")

# ---------------------------------------------------------------- 3. causelist + what-if
with tabs[2]:
    day = st.selectbox("Day", sorted(sl["date"].unique()))
    today = sl[sl["date"] == day].copy()
    today = today.join(initial[["waiting_on", "readiness", "last_event"]], on="case_id")
    today.insert(0, "keep", True)
    st.caption("Untick cases to see what moving them does to the day. Expected figures from the case model.")
    view = today[["keep", "block", "est_start", "case_id", "purpose", "advocate_id", "age_years",
                  "p_sub_eff", "exp_minutes", "waiting_on", "reason"]]
    edited = st.data_editor(
        view, hide_index=True, width="stretch", disabled=[c for c in view.columns if c != "keep"],
        column_config={"est_start": "starts ~", "age_years": st.column_config.NumberColumn("age (yrs)", format="%.1f"),
                       "p_sub_eff": st.column_config.ProgressColumn("P(moves forward)", min_value=0, max_value=1,
                                                                    format="percent"),
                       "exp_minutes": st.column_config.NumberColumn("exp. min", format="%.0f"),
                       "waiting_on": "last waited on", "reason": "why listed"})
    kept = today[edited["keep"].values]

    def day_stats(df):
        if df.empty:
            return 0.0, 0.0, 1.0, 0
        rng = np.random.default_rng(0)
        mention = cfg["mention_minutes"]
        p_heard = ((df["exp_minutes"] - mention) / (df["est_minutes"] - mention).clip(lower=0.1)).clip(0, 1).values
        heard = rng.random((2000, len(df))) < p_heard
        dur = df["est_minutes"].values * np.exp(rng.normal(-DURATION_SIGMA ** 2 / 2, DURATION_SIGMA, (2000, len(df))))
        total = np.where(heard, dur, mention).sum(axis=1)
        return df["exp_minutes"].sum(), df["p_sub_eff"].sum(), float((total <= cfg["day_minutes"] + 10).mean()), int(df["is_old"].sum())

    b = day_stats(today)
    a = day_stats(kept)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Expected minutes", f"{a[0]:.0f} / {cfg['day_minutes']}", f"{a[0] - b[0]:+.0f}")
    m2.metric("Expected effective hearings", f"{a[1]:.1f}", f"{a[1] - b[1]:+.1f}")
    m3.metric("P(everyone listed is reached)", f"{a[2]:.0%}", f"{a[2] - b[2]:+.0%}")
    m4.metric("4+ yr cases today", a[3], a[3] - b[3])

# ---------------------------------------------------------------- 4. case brief
with tabs[3]:
    bday = st.selectbox("Causelist day", sorted(sl["date"].unique()), key="brief_day")
    options = sl[sl["date"] == bday]["case_id"].tolist()
    if options:
        cid = st.selectbox("Case", options)
        st.markdown(build_brief(initial.loc[cid]))
    st.caption(f"{int((~sh['listed']).sum()):,} hearings declined 2 days ahead across the run — slots refilled, no wasted trip.")

# ---------------------------------------------------------------- 5. at-risk
with tabs[4]:
    o = ss[ss["next_purpose"] != "DISPOSED"]
    risk = o[(o["is_old"] & o["first_heard"].isna()) | o["repeat_adj"] | o["is_stuck"]].copy()
    risk["why"] = (np.where(risk["is_old"] & risk["first_heard"].isna(), "old & not heard; ", "")
                   + np.where(risk["repeat_adj"], "repeat adjournment; ", "")
                   + np.where(risk["is_stuck"], "stuck at stage; ", ""))
    st.caption(f"{len(risk):,} open cases need the judge's attention")
    st.dataframe(risk[["case_id", "age_years", "next_purpose", "why", "waiting_on", "hearings_in_stage",
                       "adjournments_est", "remaining_hearings_est", "times_listed", "due_date"]]
                 .sort_values("age_years", ascending=False), hide_index=True, width="stretch")

# ---------------------------------------------------------------- 6. advocates
with tabs[5]:
    if agents_df is None:
        st.info("Turn on L3 advocate agents in the sidebar.")
    else:
        g = agents_df.groupby("personality").agg(advocates=("advocate", "count"), prepared=("prepared", "mean"),
                                                 shows_up=("shows_up", "mean"),
                                                 free_adjournments=("free_adjournments", "sum"))
        st.caption("Advocate agents at the end of the run under the current levers "
                   "(start: dilatory 45% prepared, overloaded 65%, diligent 90%).")
        st.dataframe(g.style.format({"prepared": "{:.0%}", "shows_up": "{:.0%}"}), width="stretch")
        on_day = int((sh["failure_reason"] == "preparation").sum())
        early = int((~sh["listed"]).sum())
        st.metric("'Not prepared' discovered on the day vs admitted early", f"{on_day:,} vs {early:,}")

# ---------------------------------------------------------------- 7. all metrics
with tabs[6]:
    st.dataframe(pd.DataFrame({"metric": list(sm), "baseline": [fmt(k, bm[k]) for k in sm],
                               "samay": [fmt(k, sm[k]) for k in sm]}), hide_index=True, width="stretch")
    res = HERE / "results.md"
    if res.exists():
        st.markdown(res.read_text())
