from datetime import date, timedelta

import pandas as pd
import streamlit as st

from ui_pages.shared import (COURT_OF, FULL, GAP_DAYS, JUDGES, LISTING, OUTCOME, SAMPLE_XLSX, day_list, docket,
                             dockets, hearing_label, hearing_table, leave_of, page_setup, plans, require, save_docket,
                             sidebar)

page_setup()
u = require("Court master")
sidebar()

st.markdown("<div class='eyebrow'>Registry</div>", unsafe_allow_html=True)
st.markdown("# Court master")
tabs = st.tabs(["Judges", "Files", "Run a day", "New complaint"])

# ---------------------------------------------------------------- judges dashboard
with tabs[0]:
    cols = st.columns(len(JUDGES))
    for col, jname in zip(cols, JUDGES):
        d = docket(jname)
        lv = leave_of(jname)
        if d is None:
            body = "<div class='empty'>No docket yet. Add one on the Files tab.</div>"
        else:
            R, cases, cfg = plans(d["path"], jname, tuple(lv))
            m, bm = R["Samay"]["metrics"], R["Today's rules"]["metrics"]
            body = ("<div class='kv'>"
                    f"<div><div class='k'>Cases on file</div><div class='v'>{d['cases']:,}</div></div>"
                    f"<div><div class='k'>Listed a day</div><div class='v'>{m['Listed / day']:.0f}</div></div>"
                    f"<div><div class='k'>Listed cases reached</div><div class='v'>{m['Reach rate']:.0%}</div></div>"
                    f"<div><div class='k'>Heard cases that move</div><div class='v'>{m['Substantiveness']:.0%}</div></div>"
                    f"<div><div class='k'>Disposed in 60 days</div><div class='v'>{m['Disposed']:,}</div></div>"
                    f"<div><div class='k'>Against today's rules</div><div class='v'>{m['Disposed'] - bm['Disposed']:+,}</div></div>"
                    "</div>"
                    f"<div class='muted' style='margin-top:10px'>Leave: {', '.join(lv) if lv else 'none'}</div>")
        col.markdown(f"<div class='card'><h3>{jname}</h3><div class='muted'>{COURT_OF[jname]}, sitting 10:30 to 12:30 "
                     f"and 13:30 to 17:00</div>{body}</div>", unsafe_allow_html=True)
    st.markdown("")
    loaded = [jn for jn in JUDGES if docket(jn) is not None]
    if loaded:
        st.markdown("<div class='eyebrow'>Next sitting day</div>", unsafe_allow_html=True)
        cols = st.columns(len(loaded))
        for col, jname in zip(cols, loaded):
            R, cases, cfg = plans(docket(jname)["path"], jname, tuple(leave_of(jname)))
            wd = R["Samay"]["workdays"]
            if not wd:
                col.markdown(f"**{jname}**: nothing ready to list.")
                continue
            dl = day_list(R["Samay"]["journey"], wd[0], cfg)
            col.markdown(f"**{jname}**, {wd[0]:%A %d %B}: {len(dl)} matters, "
                         f"{float(dl['exp_minutes'].sum()):.0f} planned minutes, {dl['advocate_id'].nunique()} advocates")

# ---------------------------------------------------------------- files
with tabs[1]:
    left, right = st.columns([1.15, 1])
    with left:
        jname = st.selectbox("Judge", JUDGES, key="upload_judge")
        up = st.file_uploader("Add the judge's docket (Excel or CSV)", type=["xlsx", "xls", "csv"], key=f"up_{jname}")
        if up is not None:
            path, n, problems, notes = save_docket(up.name, up.getvalue())
            if problems:
                st.error("The file needs fixing:\n\n" + "\n".join(f"- {p}" for p in problems))
            else:
                cur = docket(jname)
                if cur is None or cur["path"] != path:
                    dockets()[jname] = {"path": path, "name": up.name, "cases": n}
                    st.rerun()          # refresh the Judges cards and Run a day with the new docket
                st.success(f"Docket for {jname}: {n:,} cases from {up.name}.")
                if notes:
                    st.info(" ".join(notes))
        st.download_button("Download the sample Excel template", SAMPLE_XLSX.read_bytes(), file_name="sample_cases.xlsx")
        lv_opts = [(date(2026, 9, 24) + timedelta(days=i)).isoformat() for i in range(90)
                   if (date(2026, 9, 24) + timedelta(days=i)).weekday() < 5]
        chosen = st.multiselect(f"{jname}'s leave (on top of government holidays)", lv_opts, default=leave_of(jname),
                                key=f"leave_{jname}")
        st.session_state.setdefault("leave", {})[jname] = chosen
        d = docket(jname)
        if d is None:
            st.markdown("No docket loaded for this judge.")
        else:
            st.markdown(f"**{d['name']}**: {d['cases']:,} cases, planned for the next 60 sitting days from 24 September 2026.")
            if st.button("Remove this docket"):
                dockets().pop(jname, None)
                st.rerun()
            st.dataframe(pd.read_csv(d["path"]).iloc[:, :9], hide_index=True, height=280, **FULL)
    with right:
        st.markdown("<div class='eyebrow'>What Samay reads</div>", unsafe_allow_html=True)
        st.markdown("A docket needs these columns. Header spellings are forgiving (\"Case No\", \"Next Purpose\"), "
                    "dates may be dd/mm/yyyy, and blank or duplicate rows are skipped with a note.")
        st.dataframe(pd.DataFrame([
            {"Column": "case_number", "Meaning": "the case's number"},
            {"Column": "filing_date", "Meaning": "date the case was filed"},
            {"Column": "purpose_of_next_hearing", "Meaning": "what the next hearing is for"},
            {"Column": "current_stage", "Meaning": "stage the case is at (optional)"},
            {"Column": "advocate_id", "Meaning": "advocate on record (optional)"},
            {"Column": "last_hearing_summary", "Meaning": "the last order: who was present, what the court said"},
            {"Column": "total_hearings_held", "Meaning": "hearings so far (optional)"},
            {"Column": "hearings_<type>", "Meaning": "hearings held per type (optional)"}]),
            hide_index=True, height=330, **FULL)
        st.markdown("<div class='eyebrow'>How the rows look</div>", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([
            {"case_number": "ST/819/2023", "filing_date": "2023-01-09", "advocate_id": "ADV-005",
             "current_stage": "Evidence Accused", "purpose_of_next_hearing": "Evidence Accused",
             "last_hearing_summary": "Present: Complainant, Complainant's Advocate, Accused Advocate. Absent: Accused. "
                                     "For defence evidence, last chance.", "total_hearings_held": 35},
            {"case_number": "ST/7/2025", "filing_date": "2025-08-14", "advocate_id": "ADV-011",
             "current_stage": "Appearance", "purpose_of_next_hearing": "Warrant",
             "last_hearing_summary": "Present: Complainant's Advocate. Absent: Accused. Issue NBW to accused. "
                                     "Take steps. For return of warrant.", "total_hearings_held": 6}]),
            hide_index=True, height=110, **FULL)

# ---------------------------------------------------------------- run a day
with tabs[2]:
    loaded = [jn for jn in JUDGES if docket(jn) is not None]
    if not loaded:
        st.markdown("Add a docket first.")
    else:
        top = st.columns([1.2, 1.6, 1, 1])
        jname = top[0].selectbox("Judge", loaded, key="run_judge")
        R, cases, cfg = plans(docket(jname)["path"], jname, tuple(leave_of(jname)))
        j = R["Samay"]["journey"]
        sitting_days = R["Samay"]["workdays"]
        if not sitting_days:
            st.markdown("Nothing ready to list for this judge.")
            st.stop()
        day = top[1].selectbox("Court date", sitting_days, format_func=lambda x: x.strftime("%A %d %B %Y"))
        todays = day_list(j, day, cfg)
        marks = st.session_state.setdefault("marks", {})
        key = (jname, day)
        done = sum(1 for c in todays.case_number if (key, c) in marks)
        top[2].metric("On the list", len(todays))
        top[3].metric("Recorded", done)
        left, right = st.columns([1.9, 1])
        with right:
            st.progress(done / max(1, len(todays)))
            pending = [c for c in todays.case_number if (key, c) not in marks]
            if pending:
                td = todays.drop_duplicates("case_number").set_index("case_number")
                cur = st.selectbox("Now calling", pending, format_func=lambda c: f"{td.loc[c].start}  {c}")
                r = td.loc[cur]
                st.markdown(f"**{hearing_label(r.hearing_type)}**  \n{LISTING[r.listing]}, advocate "
                            f"{r.advocate_id}, score {r.score:.0f}")
                choice = st.radio("Outcome", list(OUTCOME.values()), label_visibility="collapsed")
                if st.button("Record outcome", type="primary", **FULL):
                    marks[(key, cur)] = next(k for k, v in OUTCOME.items() if v == choice)
                    st.rerun()
            else:
                st.success("Every matter on the list is recorded.")
            if done and st.button("Undo last record", **FULL):
                last = [c for c in todays.case_number if (key, c) in marks][-1]
                marks.pop((key, last))
                st.rerun()
        with left:
            from model import load_reference
            ref = load_reference()
            outcome_text = {}
            for r in todays.itertuples():
                mark = marks.get((key, r.case_number))
                if mark == "substantive":
                    outcome_text[r.case_number] = (OUTCOME[mark], "reference gap for the next purpose")
                elif mark:
                    gap = GAP_DAYS[mark] if mark != "unready" else int(ref.at[r.hearing_type, "gap_days"])
                    outcome_text[r.case_number] = (OUTCOME[mark], f"{gap} days" + (", or when process returns" if mark == "process" else ""))
            st.markdown(hearing_table(todays, cfg, height=560, show_why=False, show_outcome=outcome_text),
                        unsafe_allow_html=True)

# ---------------------------------------------------------------- new complaint
with tabs[3]:
    st.markdown("<div class='sub'>Scrutiny of a new s.138 NI Act complaint before it is registered: the statutory "
                "timeline and the papers, so it is not listed only to be adjourned.</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    cheque = c1.date_input("Cheque date", date(2026, 5, 2))
    presented = c1.date_input("Presented to the bank", date(2026, 7, 20))
    memo = c2.date_input("Return memo received", date(2026, 7, 24))
    sent = c2.date_input("Demand notice sent", date(2026, 8, 10))
    received = c3.date_input("Notice received by the drawer", date(2026, 8, 14))
    filed = c3.date_input("Complaint filed", date(2026, 9, 30))
    pay_by = received + timedelta(days=15)
    limit = pay_by + timedelta(days=30)
    rows = [("Cheque presented", presented, cheque + timedelta(days=90), "within 3 months of the cheque date (RBI validity)"),
            ("Demand notice sent", sent, memo + timedelta(days=30), "s.138(b): within 30 days of the return memo"),
            ("Drawer's 15 days to pay", pay_by, pay_by, "s.138(c): cause of action arises after 15 days"),
            ("Complaint filed", filed, limit, "s.142(b): within one month of the cause of action")]
    tl = pd.DataFrame([{"Step": s, "Date": d_, "Deadline": dl, "In time": "Yes" if d_ <= dl else "No", "Rule": rule}
                       for s, d_, dl, rule in rows])
    delay = max(0, (filed - limit).days)
    left, right = st.columns([1.3, 1])
    with left:
        st.dataframe(tl.astype(str), hide_index=True, **FULL)
        d1, d2 = st.columns(2)
        docs = {k: d1.checkbox(k, value=v) for k, v in [
            ("Cheque (original)", True), ("Bank return memo", True), ("Demand notice + postal proof", True),
            ("Complainant's affidavit (s.145)", True), ("Vakalat", False), ("s.141 averments (company drawer)", False)]}
        summons = {k: d2.checkbox(k, value=v) for k, v in [("Accused's address", True), ("Phone", False), ("Email", False)]}
        company = d2.toggle("The drawer is a company")
        outside = d2.toggle("The accused lives outside this court's area", value=True)
    with right:
        missing = [k for k, v in docs.items() if not v and (company or "s.141" not in k)]
        miss_sum = [] if summons["Accused's address"] else ["accused's address for summons"]
        ok = not missing and not miss_sum and (delay == 0)
        st.markdown(f"**Status:** {'Ready to register and list' if ok else 'Return for curing before listing'}")
        if delay:
            st.markdown(f"Filed {delay} days after limitation ended. The condonation petition is filed with the "
                        "complaint and decided at admission.")
        if outside:
            st.markdown("Accused outside the court's area: s.225 BNSS enquiry affidavit with the complaint.")
        if summons["Phone"] or summons["Email"]:
            st.markdown("Phone or email given: summons can go electronically, so the appearance date can be earlier.")
        if missing or miss_sum:
            st.markdown("**To cure:** " + "; ".join(missing + miss_sum))
