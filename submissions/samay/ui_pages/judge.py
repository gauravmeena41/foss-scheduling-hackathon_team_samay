import calendar as cal
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from ui_pages.shared import (BLUE, COURT_OF, FULL, LISTING, LISTING_COLOR, ORANGE, OUTCOME, PRESET_OF, blocks,
                             day_list, docket, hearing_label, hearing_table, holidays, leave_of, live_scores,
                             page_setup, plans, require, sidebar)
import score100

page_setup()
u = require("Judge")
sidebar()
name = u["name"]

head = st.columns([3, 1])
head[0].markdown(f"<div class='eyebrow'>{COURT_OF.get(name, '')}</div>", unsafe_allow_html=True)
head[0].markdown(f"# {name}")
head[1].markdown(f"<div style='text-align:right;color:#64748B;padding-top:14px'>{COURT_OF.get(name, '')}, "
                 f"sitting 10:30 to 12:30 and 13:30 to 17:00</div>", unsafe_allow_html=True)
dk = docket(name)
if dk is None:
    st.info("The court master has not uploaded your docket yet.")
    st.stop()

R, cases, cfg = plans(dk["path"], name, tuple(leave_of(name)))
rtl, base = R["Samay"], R["Today's rules"]
j = rtl["journey"]
m, bm = rtl["metrics"], base["metrics"]
leave = {date.fromisoformat(x) for x in cfg.get("leave_dates", [])}
hol = holidays()
sitting_days = rtl["workdays"]
if not sitting_days or j.empty:
    st.warning("No case could be listed in this period: every open case is waiting on a summons, warrant or notice.")
    st.stop()
cap = cfg["day_minutes"]

tabs = st.tabs(["Today", "Calendar", "Cases", "Priority", "Insight", "How Samay decides"])


def timeline_chart(rows, height=190):
    """The day's hearings on a clock, one bar per hearing, coloured by listing number."""
    if rows.empty:
        return None
    t0 = pd.Timestamp("2026-01-01")
    d = rows.copy()
    d["from"] = [t0 + pd.Timedelta(minutes=int(s[:2]) * 60 + int(s[3:5])) for s in d["start"]]
    d["to"] = d["from"] + pd.to_timedelta(d["exp_minutes"].clip(lower=2), unit="m")
    d["Listing"] = d["listing"].map(LISTING)
    d["Hearing"] = d["hearing_type"].map(hearing_label)
    x = alt.X("from:T", title=None, axis=alt.Axis(format="%H:%M"),
              scale=alt.Scale(domain=[t0 + pd.Timedelta(minutes=615), t0 + pd.Timedelta(minutes=1035)]))
    return alt.Chart(d).mark_bar(stroke="white", strokeWidth=1.5).encode(
        x=x, x2="to:T", y=alt.Y("block:N", title=None),
        color=alt.Color("Listing:N", scale=alt.Scale(domain=list(LISTING.values()), range=list(LISTING_COLOR.values())),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["case_number", "Hearing", alt.Tooltip("score:Q", format=".0f"), "start"]).properties(height=height)


# ---------------------------------------------------------------- today
with tabs[0]:
    top = st.columns([2.2, 1, 1, 1, 1])
    day = top[0].selectbox("Court date", sitting_days, format_func=lambda x: x.strftime("%A %d %B %Y"))
    todays = day_list(j, day, cfg)
    removed = st.session_state.setdefault("removed", set())
    shown = todays[~todays.case_number.isin(removed)]
    planned = float(shown["exp_minutes"].sum())
    top[1].metric("Listed", len(shown))
    top[2].metric("Planned minutes", f"{planned:.0f} / {cap:.0f}")
    top[3].metric("Expected to move forward", f"{shown['p_sub_eff'].sum():.1f}")
    top[4].metric("Deferred, fixed slot", int((shown.listing == "deferred").sum()))
    fig = timeline_chart(shown)
    if fig is not None:
        st.altair_chart(fig, **FULL)
    left, right = st.columns([2.6, 1])
    with left:
        st.markdown(hearing_table(shown, cfg, height=380), unsafe_allow_html=True)
    with right:
        drop = st.selectbox("Remove a case from today", ["None"] + shown.case_number.tolist())
        b1, b2 = st.columns(2)
        if drop != "None" and b1.button("Remove", **FULL):
            removed.add(drop)
            st.rerun()
        if removed and b2.button("Restore", **FULL):
            st.session_state.removed = set()
            st.rerun()
        approved = st.session_state.get("approved") == (name, day)
        if st.button("Approve today's list", type="primary", disabled=approved, **FULL):
            st.session_state.approved = (name, day)
            st.rerun()
        if approved:
            st.success(f"Approved for {day:%d %B}. Time windows go to advocates and parties.")
            st.download_button("Download the causelist (CSV)",
                               shown[["start", "block", "case_number", "hearing_type", "listing", "score", "advocate_id",
                                      "reason"]].to_csv(index=False).encode(), file_name=f"causelist_{day}.csv", **FULL)
        st.markdown(f"**Grouped for you**  \n{shown.advocate_id.nunique()} advocates for "
                    f"{len(shown)} matters; {shown.hearing_type.nunique()} kinds of hearing, called together.")

# ---------------------------------------------------------------- calendar
with tabs[1]:
    workset = set(sitting_days)
    count = j.groupby("date").size().to_dict()
    months = sorted({(d.year, d.month) for d in sitting_days})
    left, right = st.columns([1.45, 1])
    with left:
        labels = [f"{cal.month_name[mm]} {yy}" for yy, mm in months]
        pick = st.segmented_control("Month", labels, default=labels[0], label_visibility="collapsed") or labels[0]
        y, mth = next(((yy, mm) for yy, mm in months if f"{cal.month_name[mm]} {yy}" == pick), months[0])
        if st.session_state.get("cal_day") not in workset | leave | set(hol):
            st.session_state.cal_day = sitting_days[0]
        sel = st.session_state.cal_day
        hdr = st.columns(7)
        for c, dn in zip(hdr, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            c.markdown(f"<div class='cal-head'>{dn}</div>", unsafe_allow_html=True)
        for week in cal.monthcalendar(y, mth):
            cols = st.columns(7)
            for c, dnum in zip(cols, week):
                if dnum == 0:
                    c.markdown("")
                    continue
                d = date(y, mth, dnum)
                if d in leave:
                    label = f"**{dnum}** leave"
                elif d in hol:
                    label = f"**{dnum}** holiday"
                elif d not in workset:
                    label = f"**{dnum}**"
                else:
                    label = f"**{dnum}** {count.get(d, 0)} cases"
                if c.button(label, key=f"cal_{d.isoformat()}", type="primary" if d == sel else "secondary", **FULL):
                    st.session_state.cal_day = d
                    st.rerun()
        st.markdown("<span class='daypill sit'>Sitting</span><span class='daypill holiday'>Holiday</span>"
                    "<span class='daypill leave'>Judge on leave</span><span class='daypill off'>Plain date: no sitting</span>",
                    unsafe_allow_html=True)
    with right:
        d = st.session_state.cal_day
        st.markdown(f"<div class='eyebrow'>{d:%A}</div>", unsafe_allow_html=True)
        st.markdown(f"### {d:%d %B %Y}")
        if d in leave:
            st.markdown("Judge on leave. The cases due today move to the next sitting day with room; none takes the flat 60-day gap.")
        elif d in hol:
            st.markdown(f"Holiday: {hol[d]}. No sitting.")
        elif d not in workset:
            st.markdown("No sitting.")
        else:
            dl = day_list(j, d, cfg)
            k1, k2, k3 = st.columns(3)
            k1.metric("Hearings", len(dl))
            k2.metric("Minutes", f"{float(dl['exp_minutes'].sum()):.0f} / {cap:.0f}")
            k3.metric("4+ years old", int(dl["is_old"].sum()))
            st.markdown(hearing_table(dl, cfg, height=430, show_why=False), unsafe_allow_html=True)

# ---------------------------------------------------------------- cases
with tabs[2]:
    open_ = cases[cases["next_purpose"] != "DISPOSED"]
    end = rtl["cases"]
    flags = open_["flags"].replace("", "—")
    listed = j.groupby("case_number").size()
    moved = j[j.outcome == "substantive"].groupby("case_number").size()
    dkv = pd.DataFrame({
        "Case": open_["case_id"], "Score": open_["score_100"].round(0),
        "Status": open_["status"], "Flags": flags,
        "Next hearing": open_["next_purpose"].map(hearing_label), "Age (years)": open_["age_years"].round(1),
        "Advocate": open_["advocate_id"], "Listings": open_["case_id"].map(listed).fillna(0).astype(int),
        "Moved forward": open_["case_id"].map(moved).fillna(0).astype(int),
        "Now": open_["case_id"].map(end.set_index("case_id")["next_purpose"]).map(
            lambda p: "Disposed" if p == "DISPOSED" else hearing_label(p))}).sort_values("Score", ascending=False)
    f = st.columns([1.2, 1, 1, 1.5])
    status = f[0].multiselect("Status", ["Eligible", "Conditional"], default=["Eligible", "Conditional"])
    old_only = f[1].toggle("Over 4 years")
    churn_only = f[2].toggle("Churning")
    view = dkv[dkv.Status.isin(status)]
    if old_only:
        view = view[view["Age (years)"] >= 4]
    if churn_only:
        view = view[view.Flags.str.contains("Churning")]
    cid = f[3].selectbox("Open a case", view.Case.tolist())
    left, right = st.columns([1.7, 1])
    with left:
        st.dataframe(view, hide_index=True, height=560, **FULL)
    with right:
        if cid is not None:
            c = cases.loc[cid]
            st.markdown(f"**{cid}**, score **{c.score_100:.0f}**  \nAge {c.pts_age:.0f}, readiness {c.pts_readiness:.0f}, "
                        f"disposal {c.pts_disposal:.0f}, churn {c.pts_churn:.0f}, urgency {c.pts_urgency:.0f}  \n"
                        f"{c.status}{': ' + str(c.prereq_reason) if not c.prereq_ok else ''}. {c.flags or 'No flags'}. "
                        f"{c.visit.capitalize()} at this stage.")
            st.code(c.last_summary or "(no order text)", language=None)
            hist = rtl["history"][(rtl["history"]["case_id"] == cid) & rtl["history"]["listed"]].copy()
            hist["Outcome"] = hist["failure_reason"].map(
                lambda r: OUTCOME.get({"attendance": "absence", "preparation": "unready", "unreached": "court",
                                       "other": "unclear"}.get(r, r), r))
            hist.loc[hist["substantive"], "Outcome"] = OUTCOME["substantive"]
            st.dataframe(hist[["date", "est_start", "purpose", "Outcome"]].rename(columns={
                "date": "Date", "est_start": "Time", "purpose": "Hearing"}), hide_index=True, height=200, **FULL)

# ---------------------------------------------------------------- priority
with tabs[3]:
    left, right = st.columns([1, 1.8])
    with left:
        st.markdown("**Weights, out of 100**")
        preset_w = score100.weights(cfg.get("score_weights"))
        w = {k: st.slider(k.title(), 0, 60, int(round(v)), 5, key=f"w_{k}") for k, v in preset_w.items()}
        applied = score100.weights(w)
        st.markdown("Applied: " + ", ".join(f"{k} {v:.0f}" for k, v in applied.items()) + ". Age never below 20.")
        st.markdown("<div class='eyebrow'>How the score is used</div>", unsafe_allow_html=True)
        st.markdown("Each sitting day: cases due are ranked by score × P(the hearing moves the case)^1.5 ÷ its expected "
                    "minutes. Bail first, overdue 30+ days forced in, half the day reserved for cases over four years, "
                    "cases waiting on a summons or warrant held back until it returns.")
        pts = live_scores(open_, w)
        bands = pd.cut(pts["score_100"], [0, 20, 40, 60, 80, 100], include_lowest=True,
                       labels=["0 to 20", "20 to 40", "40 to 60", "60 to 80", "80 to 100"]).value_counts().sort_index()
        bd = pd.DataFrame({"Band": bands.index.astype(str), "Cases": bands.values})
        st.altair_chart(alt.Chart(bd).mark_bar(color=BLUE).encode(x=alt.X("Band:N", sort=None, title=None), y="Cases:Q")
                        .properties(height=220), **FULL)
    with right:
        tbl = pd.DataFrame({"Case": open_["case_id"], "Score": pts["score_100"], "Age": pts["pts_age"].round(1),
                            "Readiness": pts["pts_readiness"].round(1), "Disposal": pts["pts_disposal"].round(1),
                            "Churn": pts["pts_churn"].round(1), "Urgency": pts["pts_urgency"].round(1),
                            "Years": open_["age_years"].round(1),
                            "Status": open_["status"], "Flags": flags})
        st.dataframe(tbl.sort_values("Score", ascending=False), hide_index=True, height=560, **FULL)

# ---------------------------------------------------------------- insight
with tabs[4]:
    spec = [("Listed cases the court reaches", "Reach rate", "%"),
            ("Heard cases that move forward", "Substantiveness", "%"),
            ("Cases over 4 years heard at least once", "Backlog 4+ heard", "%"),
            ("5+ year cases moved a stage", "Backlog 5+ advanced", "%"),
            ("Days from listing to a real hearing", "Predictability (days to hearing)", " days"),
            ("Listings started within 30 min of slot", "Started within slot", "%"),
            ("Hearings that moved a case, per day", "Effective / day", ""),
            ("Wasted listings", "Wasted trips", ""),
            ("Cases disposed", "Disposed", "")]

    def fmt(mm, k, unit):
        v = mm[k]
        if unit == "%":
            return f"{v:.0%}"
        return f"{v:.1f}{unit}" if isinstance(v, float) else f"{v:,}{unit}"
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(f"Cases disposed in {len(sitting_days)} days", f"{m['Disposed']:,}", f"{m['Disposed'] - bm['Disposed']:+,} vs today's rules")
    k2.metric("Listed cases reached", f"{m['Reach rate']:.0%}", f"{(m['Reach rate'] - bm['Reach rate']) * 100:+.0f} pts")
    k3.metric("Hearings that move a case, per day", f"{m['Effective / day']:.1f}",
              f"{m['Effective / day'] - bm['Effective / day']:+.1f}")
    k4.metric("Wasted listings", f"{m['Wasted trips']:,}", f"{m['Wasted trips'] - bm['Wasted trips']:+,}", delta_color="inverse")
    left, right = st.columns([1.2, 1])
    with left:
        st.dataframe(pd.DataFrame([{"Measure": l, "Today's rules": fmt(bm, k, un), "Samay": fmt(m, k, un)}
                                   for l, k, un in spec]), hide_index=True, height=360, **FULL)
        rows = []
        for label, pr in R.items():
            jj = pr["journey"]
            for key, lab in LISTING.items():
                g = jj[jj.listing == key]
                if len(g):
                    rows.append({"Approach": label, "Listing": lab, "Hearings": len(g),
                                 "Moved forward": f"{(g.outcome == 'substantive').mean():.0%}"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, height=250, **FULL)
    with right:
        lines = []
        for label in ["Today's rules", "Samay"]:
            dd = R[label]["daily"][["date", "substantive"]].copy()
            dd["Hearings that moved a case (cumulative)"] = dd["substantive"].cumsum()
            dd["Approach"] = label
            lines.append(dd)
        ld = pd.concat(lines)
        ld["date"] = pd.to_datetime(ld["date"])
        st.altair_chart(alt.Chart(ld).mark_line(strokeWidth=2.5).encode(
            x=alt.X("date:T", title=None), y="Hearings that moved a case (cumulative):Q",
            color=alt.Color("Approach:N", scale=alt.Scale(domain=["Today's rules", "Samay"], range=[ORANGE, BLUE]),
                            legend=alt.Legend(orient="bottom"))).properties(height=560), **FULL)

# ---------------------------------------------------------------- how Samay decides
with tabs[5]:
    box = st.container(height=640)
    with box:
        st.markdown(f"""
## The decision, each evening

For one judge and one sitting day, Samay decides which due cases to list, in which sitting, in what order and time window, and the next date for each case not listed or not moved. This bench runs with **{PRESET_OF.get(name, 'Recommended')}** rules.

## Step 1: read every case (the case model)

The last order is read for what happened (11 kinds of order), what the case is **waiting on** (summons, warrant, a party, a document), whether it is **blocked**, and how **ready** it is. Each hearing is labelled *first at stage* or *repeat #N*.

## Step 2: score every case on its own details (0 to 100)

| Factor | Points | How it is measured |
|---|---|---|
| Case age | 35 | Years since filing over the full-points age (mean + 2 sd of the docket) |
| Hearing readiness | 25 | Measured share of this hearing type that moves a case, reduced when required people were absent |
| Disposal proximity | 15 | Position in the 11 stages, Admission 0 to Judgement 10 |
| Hearing churn | 15 | Hearings held against the median expected by this stage |
| Court-set urgency | 10 | "Last chance" 10, "for judgment" 8, from the last order |

Points are added, never multiplied. The age weight can never fall below 20.

## Step 3: build the day (hybrid ranker)

1. Take every case due on or before today; hold back any case whose summons or warrant has not returned.
2. List bail first (liberty lane).
3. Force in cases overdue by 30+ days (up to 20% of the day).
4. Reserve {cfg['old_case_min_share']:.0%} of the minutes for cases over 4 years old (floor 30%).
5. Rank the rest by **score × P(moves forward)^1.5 ÷ expected minutes**.
6. Pack to {cfg['overbook_factor']:.2f}× the ~{cap:.0f} sitting minutes, morning for fresh cases, afternoon for the oldest; {cfg['changeover_minutes']:g}-min changeover; each case gets an estimated start time.
7. Two days before, a readiness check lets advocates admit they are not ready; the slot is refilled.

## Step 4: after the day

The next date follows what happened: moved forward → the reference gap for the next purpose; a party absent → sooner; summons pending → when it is expected back; court could not sit → the next working day. Never a flat 60 days. On leave or holidays, cases move to the next sitting with room.
""")
        params = [("Court day", b["name"], f"{b['start']} to {b['end']}") for b in blocks(cfg)]
        params += [("Court day", "Start", "between 10:30 and 11:00; lunch 12:30 to 13:30; rises 17:00"),
                   ("Court day", "Changeover between hearings", f"{cfg['changeover_minutes']:g} min"),
                   ("Court day", "Expected sitting minutes", f"{cap:.0f}"),
                   ("Court day", "Overbooking factor", f"{cfg['overbook_factor']}"),
                   ("Judge", "Rules", PRESET_OF.get(name, "Recommended")),
                   ("Judge", "Leave days", ", ".join(cfg.get("leave_dates", [])) or "none (government holidays already off)"),
                   ("Ranker", "Mode", cfg.get("ranking", "hybrid")),
                   ("Ranker", "Readiness power", cfg.get("hybrid_readiness_power", 1.5)),
                   ("Protected rules", "Share of the day for 4+ year cases", f"{cfg['old_case_min_share']:.0%}"),
                   ("Protected rules", "Overdue forced in after", f"{cfg.get('max_overdue_days', 30)} days"),
                   ("Protected rules", "Liberty lane", "Bail")]
        params += [("Priority score", f"{k.title()} weight", f"{v:.0f}") for k, v in preset_w.items()]
        st.dataframe(pd.DataFrame(params, columns=["Group", "Parameter", "Value"]).astype(str), hide_index=True,
                     height=38 + 35 * len(params), **FULL)
