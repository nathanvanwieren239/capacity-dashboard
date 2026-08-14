"""
Manufacturing dashboards - skeletal build for internal review.

Run:  streamlit run app.py

Two pages:
    Machine Capacity   - machine hours vs. demand, by work center
    Launch Portfolio   - launch/prototype gate status and shared-resource load

Data on both pages is synthetic. See synthetic_data.py and launch_data.py
for the column contracts, capacity_model.py and launch_model.py for the math.
"""

from __future__ import annotations

import streamlit as st

import auth
from config import ASSETS_DIR

st.set_page_config(
    page_title="Manufacturing Dashboards",
    page_icon=str(ASSETS_DIR / "favicon.png")
    if (ASSETS_DIR / "favicon.png").exists()
    else "🏭",
    layout="wide",
)

# Nothing below this line renders until the password is accepted.
auth.require_password()

# --- branding, shown on every page ----------------------------------------
LOGO_WIDTH_PX = 190  # tune to taste; sidebar is ~300 px wide

logo = ASSETS_DIR / "logo.png"
if logo.exists():
    st.sidebar.image(str(logo), width=LOGO_WIDTH_PX)
else:
    st.sidebar.markdown("### `[ logo ]`")
    st.sidebar.caption("Drop logo.png in ./assets")

# --- navigation -----------------------------------------------------------
pages = [
    st.Page(
        "views/capacity_page.py",
        title="Machine Capacity",
        icon=":material/precision_manufacturing:",
        default=True,
    ),
    st.Page(
        "views/launch_page.py",
        title="Launch Portfolio",
        icon=":material/rocket_launch:",
    ),
]

st.navigation(pages).run()
