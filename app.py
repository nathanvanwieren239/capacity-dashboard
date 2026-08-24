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

# Nothing below this line renders until a valid password is accepted.
auth.require_password()


# Take the day's backup on first use. A no-op once today's exists, so the
# cost is one filesystem check per session. Deliberately never fatal: a
# backup problem should be visible, not something that stops people working.
@st.cache_resource
def _daily_backup_once():
    try:
        import daily_backup

        made = daily_backup.run_daily()
        return {"ok": True, "snapshot": str(made) if made else None}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


_BACKUP_STATUS = _daily_backup_once()
if not _BACKUP_STATUS["ok"]:
    st.sidebar.warning(
        f"Daily backup did not run: {_BACKUP_STATUS['error']}", icon="⚠️"
    )

# --- branding, shown on every page ----------------------------------------
LOGO_WIDTH_PX = 190  # tune to taste; sidebar is ~300 px wide

logo = ASSETS_DIR / "logo.png"
if logo.exists():
    st.sidebar.image(str(logo), width=LOGO_WIDTH_PX)
else:
    st.sidebar.markdown("### `[ logo ]`")
    st.sidebar.caption("Drop logo.png in ./assets")

auth.sidebar_badge()

# --- navigation -----------------------------------------------------------
pages = [
    st.Page(
        "views/launch_page.py",
        title="Launch Portfolio",
        icon=":material/rocket_launch:",
        default=True,
    ),
    st.Page(
        "views/capacity_page.py",
        title="Machine Capacity (future state)",
        icon=":material/science:",
    ),
]

st.navigation(pages).run()
