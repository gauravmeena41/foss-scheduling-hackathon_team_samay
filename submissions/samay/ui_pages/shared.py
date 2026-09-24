"""Shared pieces for the Samay prototype pages (sign in, judge, court master): styling, sidebar, dockets, plans.

Front end only. Every number comes from Samay's engine in src/ (hybrid ranker, packer, simulator, metrics).
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent.parent
if str(HERE / "src") not in sys.path:
    sys.path.insert(0, str(HERE / "src"))

import score100  # noqa: E402
from config import PRESETS, make_config  # noqa: E402
from intake import read_upload  # noqa: E402
from metrics import compute  # noqa: E402
from model import DATA_DIR, load_cases, load_reference  # noqa: E402
from simulate import run  # noqa: E402

START = "2026-09-24"
DAYS = 60
JUDGES = ["Justice Sehgal", "Justice Dimakar", "Justice Joshi"]
COURT_OF = {"Justice Sehgal": "Court 12", "Justice Dimakar": "Court 7", "Justice Joshi": "Court 3"}
PRESET_OF = {"Justice Sehgal": "Justice Sehgal (block scheduler)", "Justice Dimakar": "Justice Dimakar (clusterer)",
             "Justice Joshi": "Justice Joshi (fresh first)"}
SEED_OF = {j: 42 + i for i, j in enumerate(JUDGES)}
LISTING = {"first": "1st listing", "second": "2nd listing", "deferred": "Deferred (3rd+)"}
OUTCOME = {"substantive": "Moved forward", "absence": "A party absent", "unready": "Not ready",
           "process": "Summons or warrant not back", "court": "Court could not reach it", "unclear": "Adjourned"}
OUTCOME_OF_ENGINE = {"substantive": "substantive", "attendance": "absence", "preparation": "unready",
                     "process": "process", "unreached": "court", "other": "unclear"}
BLUE, ORANGE, INK, MUTED = "#1B2A41", "#C08A2D", "#111925", "#56627A"
LISTING_COLOR = {"first": "#1B2A41", "second": "#3D6FD9", "deferred": "#C08A2D"}
REAL_DOCKET = DATA_DIR / "roster_sample_100.csv"      # the hackathon's real 100 cases
SAMPLE_XLSX = HERE / "samples" / "sample_cases.xlsx"
ENGINE_VERSION = hashlib.md5(b"".join(p.read_bytes() for p in sorted((HERE / "src").glob("*.py")))).hexdigest()[:12]
_V = tuple(int(x) for x in st.__version__.split(".")[:2] if x.isdigit())
FULL = {"width": "stretch"} if _V >= (1, 50) else {"use_container_width": True}

CSS = """
<style>
section.stMain > div.block-container {padding-top: 1rem; padding-bottom: 0.4rem;}
section.stSidebar div.block-container {padding-top: 0.6rem;}
h1 {margin-bottom: 0; font-size: 2rem; letter-spacing: -0.01em; font-family: 'Spectral', Georgia, serif;}
h3 {font-family: 'Spectral', Georgia, serif;}
div[data-testid="stMetric"] {background: #FFFFFF; border: 1px solid #C9D3E3; border-radius: 8px; padding: 10px 14px;}
div[data-testid="stMetricLabel"] p {font-size: 12.5px; color: #56627A; letter-spacing: 0.01em;}
div[data-testid="stMetricValue"] {font-size: 1.7rem; font-family: 'Spectral', Georgia, serif; font-weight: 600;}
div[data-testid="stTabs"] button p {font-size: 15px; font-weight: 500;}
div[data-testid="stTabs"] button[aria-selected="true"] p {color: #9A6212;}
div[data-testid="stTabs"] div[data-baseweb="tab-highlight"] {background-color: #9A6212;}
.samay-logo {font-family: 'Spectral', Georgia, serif; font-size: 40px; font-weight: 600; color: #9A6212;
             line-height: 1; letter-spacing: -0.01em; margin: 0;}
.samay-sub {font-size: 12.5px; color: #56627A; margin: 4px 0 12px 0;}
.who {font-size: 15px; color: #111925; margin-bottom: 0;}
.role {font-size: 12.5px; color: #56627A; margin-bottom: 10px;}
.eyebrow {font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: #56627A; font-weight: 600; margin-bottom: 2px;}
.sub {color: #56627A; font-size: 14px; margin-top: -4px;}
.list {height: 400px; overflow-y: auto; border: 1px solid #C9D3E3; border-radius: 8px; background: #FFFFFF;}
.list table {width: 100%; border-collapse: collapse; font-size: 14px;}
.list th {position: sticky; top: 0; background: #ECEEEA; color: #56627A; font-weight: 600; font-size: 12px;
          letter-spacing: 0.04em; text-transform: uppercase; text-align: left; padding: 9px 12px; border-bottom: 1px solid #C9D3E3;}
.list td {padding: 9px 12px; border-bottom: 1px solid #E5E9EF; vertical-align: top; color: #111925;}
.list tr:hover td {background: #F5F6F3;}
.list .time {font-family: 'Spectral', Georgia, serif; font-size: 16px; font-weight: 600; white-space: nowrap;}
.list .case {font-weight: 600; white-space: nowrap;}
.list .why {color: #56627A; font-size: 13px;}
.list .sitting td {background: #F5F6F3; color: #9A6212; font-weight: 600; font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase;}
.chip {display: inline-block; font-size: 11.5px; font-weight: 600; padding: 2px 8px; border-radius: 999px; white-space: nowrap;}
.chip.first {background: #E5E9EF; color: #1B2A41;} .chip.second {background: #DBEAFE; color: #1D4ED8;}
.chip.deferred {background: #F7ECD9; color: #9A6212;} .chip.bail {background: #E1F0E8; color: #2F7454;}
.chip.score {background: #ECEEEA; color: #111925;}
.card {background: #FFFFFF; border: 1px solid #C9D3E3; border-radius: 10px; padding: 14px 16px; height: 100%;}
.card h3 {font-family: 'Spectral', Georgia, serif; font-size: 20px; margin: 0 0 2px 0; font-weight: 600;}
.card .muted {color: #56627A; font-size: 13px; margin-bottom: 10px;}
.card .kv {display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px;}
.card .k {font-size: 12px; color: #56627A;} .card .v {font-family: 'Spectral', Georgia, serif; font-size: 22px; font-weight: 600;}
.card .empty {color: #94A3B8; font-size: 14px; padding: 18px 0;}
.cal-head {font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: #56627A; text-align: center; font-weight: 600;}
div[data-testid="stColumn"] button[kind="secondary"] {padding: 4px 6px; min-height: 44px;}
div[data-testid="stColumn"] button[kind="secondary"] p {font-size: 12px; line-height: 1.25; text-align: left;}
.daypill {display:inline-block; font-size: 11px; padding: 1px 7px; border-radius: 999px; margin-right: 6px;}
.daypill.leave {background:#F6E3E6; color:#A8253B;} .daypill.holiday {background:#F7ECD9; color:#9A6212;}
.daypill.sit {background:#E1F0E8; color:#2F7454;} .daypill.off {background:#E5E9EF; color:#56627A;}
</style>
"""


def page_setup():
    st.markdown(CSS, unsafe_allow_html=True)


def logo(size=40):
    return f"<div class='samay-logo' style='font-size:{size}px'>Samay</div>"


def user():
    return st.session_state.get("user")


def sidebar():
    u = user()
    with st.sidebar:
        st.markdown(logo() + "<div class='samay-sub'>Court scheduling</div>", unsafe_allow_html=True)
        if u:
            st.markdown(f"<div class='who'><b>{u['name']}</b></div><div class='role'>{u['role']}</div>",
                        unsafe_allow_html=True)
            st.page_link("ui_pages/dashboard.py", label="Analytics dashboard (what-ifs, 3 judges, metrics)")
            if st.button("Sign out", **FULL):
                st.session_state.pop("user", None)
                st.switch_page("ui_pages/login.py")


def require(role):
    u = user()
    if not u:
        st.switch_page("ui_pages/login.py")
    if u["role"] != role:
        st.switch_page("ui_pages/judge.py" if u["role"] == "Judge" else "ui_pages/court_master.py")
    return u


# ---------------------------------------------------------------- dockets

def hearing_cols() -> list[str]:
    return [c for c in pd.read_csv(DATA_DIR / "roster_sample_100.csv", nrows=1).columns if c.startswith("hearings_")]


def save_docket(name: str, raw: bytes):
    """Uploaded file -> clean roster CSV via Samay's intake (cached per engine version)."""
    return _save_docket(name, raw, ENGINE_VERSION)


@st.cache_data(show_spinner="Reading the docket…", max_entries=16)
def _save_docket(name: str, raw: bytes, engine: str):
    """Uploaded file -> clean roster CSV via Samay's intake. Returns (path, n_cases, problems, notes)."""
    df, problems, notes = read_upload(name, raw, START, hearing_cols())
    if df is None:
        return None, 0, problems, notes
    out = Path(tempfile.gettempdir()) / f"samay_ui_{hashlib.md5(raw).hexdigest()[:10]}_{engine}.csv"
    df.to_csv(out, index=False)
    return str(out), len(df), [], notes


def dockets() -> dict:
    """{judge: {"path", "name", "cases"}}. Justice Sehgal's docket is pre-loaded with the real 100 cases."""
    d = st.session_state.get("dockets")
    if d is None:
        path, n, _, _ = save_docket(REAL_DOCKET.name, REAL_DOCKET.read_bytes())
        d = {"Justice Sehgal": {"path": path, "name": "roster_sample_100.csv (real cases, hackathon repository)", "cases": n}}
        st.session_state.dockets = d
    return d


def docket(judge):
    return dockets().get(judge)


def leave_of(judge) -> list[str]:
    """The judge's leave: the Files tab widget's current value if it exists, else what was saved."""
    widget = st.session_state.get(f"leave_{judge}")
    if widget is not None:
        return list(widget)
    return st.session_state.setdefault("leave", {}).get(judge, [])


# ---------------------------------------------------------------- plans from the engine

def _listing(visit: str) -> str:
    v = str(visit)
    if v.startswith("first"):
        return "first"
    try:
        return "second" if int(v.split("#")[1]) <= 2 else "deferred"
    except (IndexError, ValueError):
        return "second"


def plans(path: str, judge: str, leave: tuple = ()):
    """Samay and today's rules on a judge's docket (cached per engine version, so code changes are picked up)."""
    return _plans(path, judge, tuple(leave), ENGINE_VERSION)


@st.cache_data(show_spinner="Samay is planning the next 60 sitting days…", max_entries=12)
def _plans(path: str, judge: str, leave: tuple, engine: str):
    """Run Samay and today's rules (baseline) on a judge's docket with that judge's rules."""
    cfg = make_config(PRESET_OF.get(judge, "Recommended"), leave_dates=list(leave))
    cases = load_cases(path, as_of=START)
    out = {}
    for label, policy in [("Samay", "samay"), ("Today's rules", "baseline")]:
        h, d, cl, s = run(cases.copy(), policy, cfg, start=START, days=DAYS, seed=SEED_OF.get(judge, 42))
        s = s.copy()
        s.attrs = {}
        m = compute(h, d, s, cfg)
        j = cl.merge(h[h["listed"]][["date", "case_id", "substantive", "failure_reason", "next_date"]],
                     on=["date", "case_id"], how="left")
        j["outcome"] = j["failure_reason"].map(OUTCOME_OF_ENGINE).where(~j["substantive"].fillna(False).astype(bool),
                                                                        "substantive").fillna("court")
        j = j.rename(columns={"case_id": "case_number", "purpose": "hearing_type", "est_start": "start"})
        j["listing"] = j["visit"].map(_listing)
        j["date"] = pd.to_datetime(j["date"]).dt.date
        out[label] = {"journey": j, "metrics": m, "daily": d, "cases": s, "history": h,
                      "workdays": sorted(pd.to_datetime(d["date"]).dt.date.tolist()) if len(d) else []}
    cases = cases.set_index("case_id", drop=False)
    for label in out:
        out[label]["journey"]["score"] = out[label]["journey"]["case_number"].map(cases["score_100"]).fillna(0)
    return out, cases, cfg


def blocks(cfg) -> list[dict]:
    return cfg["blocks"]


def day_list(journey, day, cfg):
    order = {b["name"]: i for i, b in enumerate(blocks(cfg))}
    return (journey[journey["date"] == day].assign(_o=lambda d: d["block"].map(order))
            .sort_values(["_o", "start"]).reset_index(drop=True))


def hearing_label(t):
    return str(t).replace("_", " ").title().replace("S351 Bnss", "s.351 BNSS")


def chip(listing, hearing_type=None):
    if hearing_type == "BAIL":
        return "<span class='chip bail'>Bail</span>"
    return f"<span class='chip {listing}'>{LISTING[listing]}</span>"


def why(row):
    if row.hearing_type == "BAIL":
        return "Liberty lane: bail is always listed"
    return str(row.reason).rstrip("; ")


def hearing_table(rows: pd.DataFrame, cfg, height=400, show_why=True, show_outcome=None):
    """The cause list as a styled table with sitting headers and chips. `show_outcome` maps case -> (text, next)."""
    html = [f"<div class='list' style='height:{height}px'><table><thead><tr><th>Time</th><th>Case</th><th>Hearing</th>"
            f"<th>Listing</th><th>Score</th><th>Advocate</th>" + ("<th>Why today</th>" if show_why else "")
            + ("<th>Outcome</th><th>Next date</th>" if show_outcome is not None else "") + "</tr></thead><tbody>"]
    ncol = 6 + int(show_why) + (2 if show_outcome is not None else 0)
    spans = {b["name"]: b for b in blocks(cfg)}
    for block, g in rows.groupby("block", sort=False):
        b = spans.get(block, {"start": "", "end": ""})
        html.append(f"<tr class='sitting'><td colspan='{ncol}'>{block}, {b['start']} to {b['end']}, "
                    f"{len(g)} matters</td></tr>")
        for r in g.itertuples():
            cells = [f"<td class='time'>{r.start}</td>", f"<td class='case'>{r.case_number}</td>",
                     f"<td>{hearing_label(r.hearing_type)}</td>", f"<td>{chip(r.listing, r.hearing_type)}</td>",
                     f"<td><span class='chip score'>{r.score:.0f}</span></td>", f"<td>{r.advocate_id}</td>"]
            if show_why:
                cells.append(f"<td class='why'>{why(r)}</td>")
            if show_outcome is not None:
                o = show_outcome.get(r.case_number, ("", ""))
                cells.append(f"<td>{o[0]}</td><td class='why'>{o[1]}</td>")
            html.append("<tr>" + "".join(cells) + "</tr>")
    html.append("</tbody></table></div>")
    return "".join(html)


def reference():
    return load_reference()


def holidays() -> dict:
    cal = pd.read_csv(DATA_DIR / "court_calendar.csv")
    cal = cal[cal["is_holiday"] == "Yes"]
    return {pd.Timestamp(r.date).date(): r.holiday_name for r in cal.itertuples()}


def next_date_text(outcome: str, purpose: str) -> str:
    """The engine's next-date rule for a recorded outcome, in days (from next_date.py and the reference table)."""
    from next_date import DETAIL_GAP, OUTCOME_GAP
    ref = reference()
    gap = float(ref.at[purpose, "gap_days"]) if purpose in ref.index else float(ref["gap_days"].median())
    if outcome == "substantive":
        return "reference gap for the next purpose"
    if outcome == "court":
        return "next working day"
    if outcome == "process":
        return f"when the process is expected back (~{1.5 * gap:.0f} days)"
    mult = {"absence": OUTCOME_GAP["attendance"], "unready": OUTCOME_GAP["preparation"],
            "unclear": DETAIL_GAP["Unclear"]}[outcome]
    return f"{max(1, round(mult * gap))} days"


def live_scores(cases: pd.DataFrame, w: dict) -> pd.DataFrame:
    pts = score100.score(cases, reference(), w)
    return pts


__all__ = ["PRESETS"]
