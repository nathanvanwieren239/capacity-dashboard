"""
Shared-password gate for the dashboard.

The password is NEVER stored in this repo. It lives in Streamlit secrets:

    local  ->  .streamlit/secrets.toml      (gitignored)
    cloud  ->  app settings -> Secrets

Either way the contents are:

    APP_PASSWORD = "pick-something-long"

This is a single shared password, not per-user accounts. It stops casual
access to a link; it is not an identity system and there is no lockout on
repeated attempts. On Community Cloud it sits on top of the viewer allow-list
you get from deploying a private repo.
"""

from __future__ import annotations

import hmac

import streamlit as st

_SESSION_KEY = "_auth_ok"
_PLACEHOLDER = "change-me"


def _configured_password() -> str | None:
    """Read APP_PASSWORD, tolerating the case where no secrets file exists."""
    try:
        value = st.secrets["APP_PASSWORD"]
    except Exception:
        return None
    return str(value) if value else None


def require_password() -> None:
    """
    Block the rest of the script until the correct password is entered.

    Call immediately after st.set_page_config(), before anything renders.
    Fails closed: if no password is configured, the app refuses to run rather
    than silently serving to everyone.
    """
    if st.session_state.get(_SESSION_KEY):
        return

    expected = _configured_password()

    if expected is None:
        st.error(
            "No `APP_PASSWORD` is configured, so this app will not start.\n\n"
            "**Local:** create `.streamlit/secrets.toml` containing "
            "`APP_PASSWORD = \"...\"`\n\n"
            "**Community Cloud:** app menu → Settings → Secrets, paste the "
            "same line, then reboot the app."
        )
        st.stop()

    if expected == _PLACEHOLDER:
        st.error(
            "`APP_PASSWORD` is still set to the placeholder value. "
            "Change it to a real password before using this app."
        )
        st.stop()

    st.title("🏭 Manufacturing Capacity Dashboard")
    st.caption("Internal demo. Enter the shared password to continue.")

    with st.form("login"):
        entered = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter")

    if submitted:
        # Constant-time compare, so response timing does not leak the password.
        if hmac.compare_digest(entered, expected):
            st.session_state[_SESSION_KEY] = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()
