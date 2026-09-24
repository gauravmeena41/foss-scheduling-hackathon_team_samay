"""Samay prototype UI: sign in, then the judge's page or the court master's page.   streamlit run ui.py

Front end only; the scheduling, ranking and simulation all come from src/ (same engine as app.py).
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

st.set_page_config(page_title="Samay", page_icon=":material/gavel:", layout="wide")

pages = st.navigation([
    st.Page("ui_pages/login.py", title="Sign in", default=True),
    st.Page("ui_pages/judge.py", title="Judge"),
    st.Page("ui_pages/court_master.py", title="Court master"),
], position="hidden")
pages.run()
