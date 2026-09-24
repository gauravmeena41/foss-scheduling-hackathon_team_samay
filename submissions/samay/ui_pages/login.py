import streamlit as st

from ui_pages.shared import FULL, JUDGES, logo, page_setup

page_setup()
st.markdown("<style>section.stSidebar {display: none;}</style>", unsafe_allow_html=True)

left, mid, right = st.columns([1, 1.1, 1])
with mid:
    st.markdown("<div style='height: 16vh'></div>", unsafe_allow_html=True)
    st.markdown(logo(64) + "<div class='samay-sub' style='font-size:14px'>Court scheduling for a judge's docket. "
                "Justice Sehgal's 3,000-case docket is pre-loaded; the court master can upload any judge's Excel.</div>",
                unsafe_allow_html=True)
    role = st.radio("Sign in as", ["Judge", "Court master"], horizontal=True)
    if role == "Judge":
        name = st.selectbox("Judge", JUDGES)
    else:
        name = st.text_input("Name", value="Court master")
    if st.button("Sign in", type="primary", **FULL):
        st.session_state.user = {"role": role, "name": name.strip() or role}
        st.switch_page("ui_pages/judge.py" if role == "Judge" else "ui_pages/court_master.py")
    st.page_link("ui_pages/dashboard.py", label="Or open the full analytics dashboard →")
