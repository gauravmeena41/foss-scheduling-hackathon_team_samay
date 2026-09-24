"""Samay: sign in as a judge or the court master; the full analytics dashboard is one click away.   streamlit run app.py

Front end only; the scheduling, ranking and simulation all come from src/.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

# Streamlit keeps imported modules alive between reruns; reload the engine (then the shared page code)
# so a `git pull` is always picked up without restarting the server.
import importlib  # noqa: E402

for _m in ["score100", "orders", "efiling", "model", "intake", "config", "priority", "packer", "next_date",
           "agents", "baseline", "metrics", "brief", "simulate", "ui_pages.shared"]:
    if _m in sys.modules:
        importlib.reload(sys.modules[_m])

st.set_page_config(page_title="Samay", page_icon=":material/gavel:", layout="wide")

pages = st.navigation([
    st.Page("ui_pages/login.py", title="Sign in", default=True),
    st.Page("ui_pages/judge.py", title="Judge"),
    st.Page("ui_pages/court_master.py", title="Court master"),
    st.Page("ui_pages/dashboard.py", title="Analytics dashboard"),
], position="hidden")
pages.run()
