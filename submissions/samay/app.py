"""Samay dashboard (Set G).   streamlit run app.py

One judge's docket. Upload the cases (Excel/CSV) or use the sample docket; Samay reads each
case, holds back what isn't ready, ranks and packs tomorrow's day into the court's sittings,
and shows the judge what their rules cost.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import sys
import tempfile
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from brief import build_brief  # noqa: E402
from config import GUARDRAILS, PRESETS, make_config  # noqa: E402
from efiling import enrich  # noqa: E402
from metrics import PERCENT, compute  # noqa: E402
from model import DATA_DIR, load_cases, validate_cases  # noqa: E402
from next_date import Calendar  # noqa: E402
from simulate import DURATION_SIGMA, run  # noqa: E402

st.set_page_config(page_title="Samay — court scheduler", layout="wide")

# Cached results must be thrown away whenever the engine changes, not only when app.py does.
ENGINE_VERSION = hashlib.md5(b"".join(p.read_bytes() for p in sorted((HERE / "src").glob("*.py")))).hexdigest()[:12]

REQUIRED_INPUT = ["case_number", "filing_date", "advocate_id", "party_id", "current_stage",
                  "last_hearing_summary", "purpose_of_next_hearing", "total_hearings_held"]
SAMPLE_XLSX = HERE / "samples" / "sample_cases.xlsx"
START = "2026-09-24"


# ---------------------------------------------------------------- inputs
@st.cache_data(show_spinner=False)
def sample_roster(n_cases: int, efiling: bool, engine: str = ENGINE_VERSION) -> str:
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


def uploaded_roster(file, efiling: bool) -> tuple[str | None, list[str]]:
    """Save an uploaded .xlsx/.csv as a roster CSV. Returns (path, problems)."""
    raw = file.getvalue()
    try:
        df = pd.read_csv(file) if file.name.lower().endswith(".csv") else pd.read_excel(file)
    except Exception as e:  # noqa: BLE001
        return None, [f"Couldn't read the file: {e}"]
    missing = [c for c in REQUIRED_INPUT if c not in df.columns]
    if missing:
        return None, [f"Missing column(s): {', '.join(missing)} — use the sample Excel as the template."]
    for col in [c for c in df.columns if c.startswith("hearings_")] + ["total_hearings_held"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    for c in [c for c in pd.read_csv(DATA_DIR / "roster_sample_100.csv", nrows=1).columns if c.startswith("hearings_")]:
        if c not in df.columns:
            df[c] = 0
    df["filing_number"] = df.get("filing_number", df["case_number"])
    if efiling:
        df = enrich(df)
    out = Path(tempfile.gettempdir()) / f"samay_upload_{hashlib.md5(raw).hexdigest()[:10]}_{int(efiling)}.csv"
    df.to_csv(out, index=False)
    try:
        problems = validate_cases(load_cases(str(out), as_of=START))
    except Exception as e:  # noqa: BLE001
        problems = [f"Couldn't build the case model: {e}"]
    return str(out), problems


def freeze(cfg: dict) -> tuple:
    return tuple((k, repr(v) if isinstance(v, (list, dict)) else v) for k, v in sorted(cfg.items()))


def thaw(items: tuple) -> dict:
    return {k: ast.literal_eval(v) if isinstance(v, str) and v[:1] in "[{" else v for k, v in items}


@st.cache_data(show_spinner="Simulating the court…", max_entries=64)
def simulate(path: str, policy: str, cfg_items: tuple, days: int, seed: int, engine: str = ENGINE_VERSION):
    cfg = thaw(cfg_items)
    h, d, lists, s = run(load_cases(path, as_of=START), policy, cfg, start=START, days=days, seed=seed)
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
def initial_cases(path: str, engine: str = ENGINE_VERSION) -> pd.DataFrame:
    return load_cases(path, as_of=START).set_index("case_id", drop=False)


def fmt(k, v):
    if k in PERCENT:
        return f"{v:.0%}"
    return f"{v:,.1f}" if isinstance(v, float) else f"{v:,}"


def hm(minutes: float) -> pd.Timestamp:
    return pd.Timestamp("2026-01-01") + pd.Timedelta(minutes=float(minutes))


def to_min(hhmm: str) -> int:
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Docket — one judge")
    source = st.radio("Cases", ["Sample docket", "Upload Excel / CSV"], horizontal=True)
    efiling_on = st.toggle("E-filing signals (synthetic)", False,
                           help="Addresses, contact known, prepaid summons/e-post, jurisdiction")
    path, problems = None, []
    if source == "Upload Excel / CSV":
        up = st.file_uploader("Cases file (.xlsx or .csv)", type=["xlsx", "xls", "csv"])
        if SAMPLE_XLSX.exists():
            st.download_button("Download the sample Excel template", SAMPLE_XLSX.read_bytes(),
                               file_name="sample_cases.xlsx")
        if up is not None:
            path, problems = uploaded_roster(up, efiling_on)
    else:
        n_cases = st.select_slider("Roster size", [100, 500, 1000, 3000], value=3000,
                                   help="3,000 = the case study's docket. Smaller rosters leave the baseline court idle.")
        path = sample_roster(n_cases, efiling_on, ENGINE_VERSION)
    days = st.slider("Working days to simulate", 10, 80, 60)
    seed = int(st.number_input("Seed", value=42, step=1))
    cal_all = Calendar(DATA_DIR / "court_calendar.csv")
    horizon = [d for d in cal_all.days if d >= pd.Timestamp(START)][:days + 10]
    hol = pd.read_csv(DATA_DIR / "court_calendar.csv", parse_dates=["date"])
    hol = hol[(hol["is_holiday"] == "Yes") & (hol["date"] >= pd.Timestamp(START))]
    st.caption("Government holidays are non-sitting days already: "
               + ", ".join(f"{r.holiday_name.split(' (')[0]} {r.date:%d %b}" for r in hol.itertuples()))
    leave = st.multiselect("Judge's personal leave (extra days off)", [d.date() for d in horizon],
                           help="On top of weekends and government holidays. Hearings and next dates move to sitting days.")

    st.header("Judge's rules")
    preset = st.selectbox("Preset", list(PRESETS))
    ranking = st.radio("Ranking", ["hybrid", "samay", "teammate"], horizontal=True,
                       format_func={"hybrid": "Hybrid", "samay": "Value/min", "teammate": "0-100 score"}.get,
                       help="Hybrid = 0-100 priority × P(moves forward) ÷ minutes (default). "
                            "Value/min = most effective hearings. 0-100 score = most disposals and 5+ yr movement.")
    base = make_config(preset, enforce_guardrails=False)
    overbook = st.slider("Overbooking factor", 0.8, 2.0, float(base["overbook_factor"]), 0.05,
                         help="Listed expected minutes ÷ sitting minutes (~315). Above 1 = planned no-shows.")
    old_share = st.slider("Share of day for 4+ yr cases", 0.0, 0.9, float(base["old_case_min_share"]), 0.05)
    age_w = st.slider("Age weight in ranking", -0.3, 1.0, float(base["age_weight"]), 0.05)
    changeover = st.slider("Changeover between hearings (min)", 0.0, 10.0, float(base["changeover_minutes"]), 0.5)
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

st.title("Samay — a court day that runs to plan")
if path is None:
    st.info("Upload the judge's cases as an Excel or CSV file (sidebar) — or switch to the sample docket. "
            "The sample Excel shows the expected columns.")
    st.stop()
if problems:
    st.error("The file needs fixing before Samay can schedule it:\n\n" + "\n".join(f"- {p}" for p in problems))
    st.stop()

cfg = make_config(preset, enforce_guardrails=enforce, overbook_factor=overbook, old_case_min_share=old_share,
                  age_weight=age_w, gate_prerequisites=gate, cluster_by_advocate=cluster,
                  carry_forward_weekly=weekly, summary_mandate=summary, readiness_confirmation=confirm,
                  agents=agents_on, reminders=reminders, adjournment_cost=cost, changeover_minutes=changeover,
                  ranking=ranking,
                  leave_dates=[str(d) for d in leave])
key = freeze(cfg)
bh, bd, bl, bs, bm, _ = simulate(path, "baseline", key, days, seed, ENGINE_VERSION)
sh, sd, sl, ss, sm, agents_df = simulate(path, "samay", key, days, seed, ENGINE_VERSION)
initial = initial_cases(path, ENGINE_VERSION)

st.caption(f"One judge · {len(initial):,} cases · {len(sd)} sitting days"
           + (f" ({len(leave)} on leave)" if leave else "")
           + f" · sits 10:30–11:00 → 12:30, lunch, 13:30 → 17:00 (≈{cfg['day_minutes'] / 60:.2f} h) · "
           f"{cfg['changeover_minutes']:g}-min changeover · preset **{preset}** · baseline = list 60 a day, flat 60-day next date")
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

tabs = st.tabs(["Workflow", "Calendar", "Three judges", "Backlog & drift", "Why hearings fail",
                "Causelist what-if", "Case brief", "At-risk cases", "Advocates (L3)", "Rankers", "All metrics"])

# ---------------------------------------------------------------- workflow
with tabs[0]:
    st.subheader("From the uploaded cases to tomorrow's causelist")
    first_day = sl["date"].min() if len(sl) else None
    active = initial[initial["next_purpose"] != "DISPOSED"]
    blocked = active[~active["prereq_ok"].astype(bool)]
    ready = active[active["prereq_ok"].astype(bool)]
    day1 = sl[sl["date"] == first_day]
    steps = pd.DataFrame({
        "step": ["1. Cases loaded & validated", "2. Case model: last order read",
                 "3. Held back — prerequisite pending", "4. Eligible and ranked", "5. Listed for day 1"],
        "cases": [len(initial), len(active), len(blocked), len(ready), len(day1)],
        "what happens": [
            "Every row checked against the case schema (validate_cases).",
            f"{initial['last_event'].nunique()} kinds of order recognised; {int((initial['next_purpose'] == 'DISPOSED').sum())} already disposed.",
            "Waiting on: " + ", ".join(f"{k} {v}" for k, v in blocked["prereq_reason"].value_counts().items()),
            {"hybrid": "0-100 priority (age, readiness, near the end, churn, urgency) × P(moves forward) ÷ minutes; bail first; overdue 30+ days forced in.",
             "samay": "Age × P(moves forward) ÷ expected minutes (+ part-heard, purpose-day boosts).",
             "teammate": "0-100 priority: age 35, readiness 25, near the end 15, churn 15, urgency 10."}[ranking],
            f"Packed into the sittings at ~{day1['exp_minutes'].sum():.0f} expected minutes; "
            f"{int(day1['is_old'].sum())} are 4+ years old.",
        ]})
    st.dataframe(steps, hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    c1.markdown("**Before — as uploaded**")
    raw = pd.read_csv(path)
    c1.dataframe(raw[["case_number", "filing_date", "purpose_of_next_hearing"]].head(20)
                 .rename(columns={"case_number": "case", "purpose_of_next_hearing": "next purpose"}),
                 hide_index=True, width="stretch")
    c2.markdown(f"**After — Samay's causelist for {first_day}**")
    c2.dataframe(day1.join(initial[["score_100"]], on="case_id")[["est_start", "case_id", "purpose", "score_100", "reason"]].head(20)
                 .rename(columns={"est_start": "starts ~", "case_id": "case", "reason": "why listed"}),
                 hide_index=True, width="stretch")
    st.download_button("Download the proposed schedule (CSV)", sl.to_csv(index=False).encode(),
                       file_name="proposed_schedule.csv")

# ---------------------------------------------------------------- calendar
with tabs[1]:
    cday = st.selectbox("Day", sorted(sl["date"].unique()), key="cal_day")
    plan = sl[sl["date"] == cday].copy()
    plan["start"] = plan["est_start"].map(lambda t: hm(to_min(t)))
    plan["end"] = [hm(to_min(t) + m) for t, m in zip(plan["est_start"], plan["exp_minutes"])]
    plan["lane"] = plan["block"]
    lunch = pd.DataFrame({"start": [hm(750)], "end": [hm(810)], "label": ["Lunch"]})
    x = alt.X("start:T", title=None, axis=alt.Axis(format="%H:%M"), scale=alt.Scale(domain=[hm(630), hm(1030)]))
    band = alt.Chart(lunch).mark_rect(opacity=0.15, color="gray").encode(x=x, x2="end:T")
    bars = alt.Chart(plan).mark_bar(cornerRadius=2, stroke="white", strokeWidth=0.5).encode(
        x=x, x2="end:T", y=alt.Y("lane:N", title=None),
        color=alt.Color("purpose:N", legend=alt.Legend(orient="bottom", columns=4)),
        tooltip=["case_id", "purpose", "visit", "est_start", alt.Tooltip("exp_minutes", format=".0f"), "reason"])
    st.markdown("**Planned** — each case's expected slot (hover for details)")
    st.altair_chart(band + bars, width="stretch")
    ran = sh[(sh["date"] == cday) & sh["listed"] & sh["reached"]].copy()
    if len(ran):
        ran["start"] = ran["actual_start"].map(lambda t: hm(to_min(t)))
        ran["end"] = [s + pd.Timedelta(minutes=max(float(m), 1.0)) for s, m in zip(ran["start"], ran["minutes_used"])]
        ran["result"] = np.select([ran["substantive"], ran["happened"]], ["moved forward", "heard, didn't move"],
                                  "adjourned (mention)")
        ran["why"] = ran["failure_detail"].fillna("")
        ran["lane"] = "Simulated day"
        bars2 = alt.Chart(ran).mark_bar(cornerRadius=2, stroke="white", strokeWidth=0.5).encode(
            x=x, x2="end:T", y=alt.Y("lane:N", title=None),
            color=alt.Color("result:N", scale=alt.Scale(domain=["moved forward", "heard, didn't move", "adjourned (mention)"],
                                                        range=["#2a9d5c", "#e9a23b", "#c0392b"]),
                            legend=alt.Legend(orient="bottom")),
            tooltip=["case_id", "purpose", "visit", "actual_start", alt.Tooltip("minutes_used", format=".0f"), "result", "why"])
        st.markdown("**What happened (simulated)** — actual start between 10:30 and 11:00, "
                    f"{cfg['changeover_minutes']:g}-min changeovers, lunch as a hard break")
        st.altair_chart(band + bars2, width="stretch")
        unreached = int((sh["date"] == cday).sum() - len(ran) - (~sh.loc[sh["date"] == cday, "listed"]).sum())
        st.caption(f"{len(ran)} reached · {unreached} not reached before 17:00")

# ---------------------------------------------------------------- three judges
with tabs[2]:
    st.subheader("Same docket, each judge's rules — and what they cost")
    rows = []
    shared = dict(agents=agents_on, changeover_minutes=changeover, leave_dates=[str(d) for d in leave], ranking=ranking)
    for name in PRESETS:
        for guarded in ([True, False] if "Joshi" in name else [True]):
            c = make_config(name, enforce_guardrails=guarded, **shared)
            _, _, _, _, m, _ = simulate(path, "samay", freeze(c), days, seed, ENGINE_VERSION)
            rows.append({"rules": name + ("" if guarded else " — guardrail off"),
                         **{k: m[k] for k in ["Effective / day", "Reach rate", "Backlog 5+ advanced",
                                              "Backlog 4+ heard", "Date slippage (days)", "Started within slot",
                                              "Wasted trips"]}})
    rows.append({"rules": "Baseline court", **{k: bm[k] for k in rows[0] if k != "rules"}})
    comp = pd.DataFrame(rows).set_index("rules")
    c1, c2 = st.columns(2)
    c1.caption("Effective hearings per day")
    c1.bar_chart(comp["Effective / day"], horizontal=True)
    c2.caption("5+ year cases that moved at least one stage")
    c2.bar_chart(comp["Backlog 5+ advanced"], horizontal=True)
    st.dataframe(comp.style.format({k: "{:.0%}" for k in comp.columns if k in PERCENT} |
                                   {k: "{:,.1f}" for k in comp.columns if k not in PERCENT}), width="stretch")
    st.caption("Fresh-first (Joshi) buys throughput with the old backlog; the guardrail puts a floor under that trade.")

# ---------------------------------------------------------------- backlog & drift
with tabs[3]:
    trend = pd.concat([bd.assign(policy="Baseline"), sd.assign(policy="Samay")])
    c1, c2 = st.columns(2)
    c1.caption("Open 5+ year cases")
    c1.line_chart(trend.pivot(index="date", columns="policy", values="open_5plus"))
    c2.caption("Effective hearings per day")
    c2.line_chart(trend.pivot(index="date", columns="policy", values="substantive"))
    order = ["<1", "1-2", "2-3", "3-4", "4-5", "5+"]

    def open_by_age(state):
        o = state[state["next_purpose"] != "DISPOSED"]
        return o["age_bucket"].value_counts().reindex(order, fill_value=0)

    ages = pd.DataFrame({"Start": initial[initial["next_purpose"] != "DISPOSED"]["age_bucket"]
                         .value_counts().reindex(order, fill_value=0),
                         "Baseline end": open_by_age(bs), "Samay end": open_by_age(ss)})
    c3, c4 = st.columns(2)
    c3.caption("Open cases by age bucket")
    c3.bar_chart(ages, stack=False)
    c4.caption("Why the docket can't be 'cleared'")
    c4.metric("Median hearing-hours left in the docket", f"{initial['remaining_minutes_est'].sum() / 60:,.0f} h",
              f"court sits {len(sd) * cfg['day_minutes'] / 60:,.0f} h in {len(sd)} days", delta_color="off")

# ---------------------------------------------------------------- why hearings fail
with tabs[4]:
    st.subheader("Why listed hearings didn't move the case — per sitting day")

    SHORT = {"Awaiting Process / Summons / Warrant Return": "Awaiting summons / warrant",
             "Evidence / Filing Not Ready": "Evidence / filing not ready",
             "Respondent Absence / Non-Compliance": "Accused absent", "Petitioner Absence / Non-Compliance": "Complainant absent",
             "Both Parties Unready / Absent": "Both parties absent", "Party Sought Time / Adjournment": "Party sought time",
             "Court Administrative Issue": "Court administrative", "Court Holiday / No Sitting": "Court didn't sit",
             "External Dependency": "External (mediation, report)", "Unclear": "Unclear from order"}

    def reasons(h, d, label):
        L = h[h["listed"]]
        r = L["failure_detail"].where(L["reached"], "Not reached before 17:00").dropna().replace(SHORT)
        return (r.value_counts() / max(1, len(d))).rename(label)

    early = (sh.loc[~sh["listed"], "failure_reason"].value_counts() / max(1, len(sd))).rename("Samay")
    fail = pd.concat([reasons(bh, bd, "Baseline"), reasons(sh, sd, "Samay")], axis=1).fillna(0)
    fail = fail.sort_values("Baseline", ascending=False)
    st.bar_chart(fail, horizontal=True, stack=False)
    st.caption("Detailed reasons are drawn from the organisers' failure table for each hearing type. "
               "Court-side reasons (holiday, administrative) bring the case back the next working day; "
               "an absence brings it back sooner; a pending summons/warrant waits for the return.")
    if len(early):
        st.markdown("**Admitted two days early at the readiness check (slot refilled, no trip):** "
                    + ", ".join(f"{k} {v:.1f}/day" for k, v in early.items()))
    vis = sh[sh["listed"] & sh["reached"]].assign(first=lambda x: x["visit"].eq("first at stage"))
    if len(vis):
        g = vis.groupby("first")["substantive"].mean()
        st.markdown(f"**First-time vs repeat hearings:** first at stage move forward "
                    f"{g.get(True, float('nan')):.0%} of the time, repeat hearings {g.get(False, float('nan')):.0%}.")

# ---------------------------------------------------------------- causelist what-if
with tabs[5]:
    day = st.selectbox("Day", sorted(sl["date"].unique()))
    today = sl[sl["date"] == day].copy()
    today = today.join(initial[["waiting_on", "readiness", "last_event"]], on="case_id")
    today.insert(0, "keep", True)
    st.caption("Untick cases to see what moving them does to the day. Expected figures from the case model.")
    today = today.join(initial[["score_100"]], on="case_id")
    view = today[["keep", "block", "est_start", "case_id", "purpose", "visit", "score_100", "age_years",
                  "p_sub_eff", "exp_minutes", "reason"]]
    edited = st.data_editor(
        view, hide_index=True, width="stretch", disabled=[c for c in view.columns if c != "keep"],
        column_config={"score_100": st.column_config.ProgressColumn("priority /100", min_value=0, max_value=100, format="%.0f"),
                       "est_start": "starts ~", "age_years": st.column_config.NumberColumn("age (yrs)", format="%.1f"),
                       "p_sub_eff": st.column_config.ProgressColumn("P(moves forward)", min_value=0, max_value=1,
                                                                    format="percent"),
                       "exp_minutes": st.column_config.NumberColumn("exp. min", format="%.0f"),
                       "reason": "why listed"})
    kept = today[edited["keep"].values]

    def day_stats(df):
        if df.empty:
            return 0.0, 0.0, 1.0, 0
        rng = np.random.default_rng(0)
        mention, co = cfg["mention_minutes"], cfg["changeover_minutes"]
        p_heard = ((df["exp_minutes"] - co - mention) / (df["est_minutes"] - mention).clip(lower=0.1)).clip(0, 1).values
        heard = rng.random((2000, len(df))) < p_heard
        dur = df["est_minutes"].values * np.exp(rng.normal(-DURATION_SIGMA ** 2 / 2, DURATION_SIGMA, (2000, len(df))))
        total = np.where(heard, dur, mention).sum(axis=1) + co * len(df)
        return df["exp_minutes"].sum(), df["p_sub_eff"].sum(), float((total <= cfg["day_minutes"] + 10).mean()), int(df["is_old"].sum())

    b = day_stats(today)
    a = day_stats(kept)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Expected minutes", f"{a[0]:.0f} / {cfg['day_minutes']:.0f}", f"{a[0] - b[0]:+.0f}")
    m2.metric("Expected effective hearings", f"{a[1]:.1f}", f"{a[1] - b[1]:+.1f}")
    m3.metric("P(everyone listed is reached)", f"{a[2]:.0%}", f"{a[2] - b[2]:+.0%}")
    m4.metric("4+ yr cases today", a[3], a[3] - b[3])

# ---------------------------------------------------------------- case brief
with tabs[6]:
    bday = st.selectbox("Causelist day", sorted(sl["date"].unique()), key="brief_day")
    options = sl[sl["date"] == bday]["case_id"].tolist()
    if options:
        cid = st.selectbox("Case", options)
        st.markdown(build_brief(initial.loc[cid]))

# ---------------------------------------------------------------- at-risk
with tabs[7]:
    o = ss[ss["next_purpose"] != "DISPOSED"]
    risk = o[(o["is_old"] & o["first_heard"].isna()) | o["repeat_adj"] | o["is_stuck"]].copy()
    risk["why"] = (np.where(risk["is_old"] & risk["first_heard"].isna(), "old & not heard; ", "")
                   + np.where(risk["repeat_adj"], "repeat adjournment; ", "")
                   + np.where(risk["is_stuck"], "stuck at stage; ", ""))
    st.caption(f"{len(risk):,} open cases need the judge's attention")
    st.dataframe(risk[["case_id", "age_years", "next_purpose", "why", "waiting_on", "hearings_in_stage",
                       "adjournments_est", "remaining_hearings_est", "times_listed", "due_date"]]
                 .sort_values("age_years", ascending=False), hide_index=True, width="stretch")

# ---------------------------------------------------------------- advocates
with tabs[8]:
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

# ---------------------------------------------------------------- rankers
with tabs[9]:
    st.subheader("Three ways to rank the same docket")
    st.markdown("**Value per minute** (ours) maximises hearings that move a case forward. **0-100 priority** "
                "(teammate) maximises cases finished and old-case movement. **Hybrid** — the teammate's priority, "
                "counted only if the hearing moves the case, per minute — keeps most of both.")
    rk = []
    for mode, label in [("samay", "Value per minute"), ("teammate", "0-100 priority"), ("hybrid", "Hybrid (default)")]:
        _, _, _, _, m, _ = simulate(path, "samay", freeze(dict(cfg, ranking=mode)), days, seed, ENGINE_VERSION)
        rk.append({"ranker": label, **{k: m[k] for k in ["Effective / day", "Backlog 5+ advanced", "Disposed",
                                                        "Wasted trips", "Reach rate"]}})
    rk = pd.DataFrame(rk).set_index("ranker")
    st.dataframe(rk.style.format({"Backlog 5+ advanced": "{:.0%}", "Reach rate": "{:.0%}", "Effective / day": "{:.1f}"}),
                 width="stretch")
    r = HERE / "rankers.md"
    if r.exists():
        st.markdown(r.read_text())

# ---------------------------------------------------------------- all metrics
with tabs[10]:
    st.dataframe(pd.DataFrame({"metric": list(sm), "baseline": [fmt(k, bm[k]) for k in sm],
                               "samay": [fmt(k, sm[k]) for k in sm]}), hide_index=True, width="stretch")
    res = HERE / "results.md"
    if res.exists():
        st.markdown(res.read_text())
