"""
Two-role password gate.

Passwords are NEVER stored in this repo. They live in Streamlit secrets:

    local  ->  .streamlit/secrets.toml      (gitignored)
    cloud  ->  app settings -> Secrets

    APP_PASSWORD_VIEWER = "one-password"
    APP_PASSWORD_EDITOR = "a-different-password"

`viewer` can see everything. `editor` additionally gets the data-entry forms
(Add New Gate Zero, Add New Prototype).

This is a DEVELOPMENT stand-in for real accounts. It is a shared password per
role, not per-user identity, so it cannot tell you *who* changed a date - only
that someone with the editor password did. Real accountability needs named
logins, which is a reason to move this behind the company intranet before it
carries live data.
"""

from __future__ import annotations

import hmac
import os

import streamlit as st

_ROLE_KEY = "_auth_role"
_PLACEHOLDER = "change-me"

VIEWER = "viewer"
EDITOR = "editor"

_SECRET_FOR_ROLE = {
    VIEWER: "APP_PASSWORD_VIEWER",
    EDITOR: "APP_PASSWORD_EDITOR",
}


def _secret(name: str) -> str | None:
    """
    Read a password from Streamlit secrets, falling back to the environment.

    The environment fallback exists for container deployment: passing
    `-e APP_PASSWORD_EDITOR=...` is far simpler than mounting a secrets file
    into an image, and it keeps credentials out of the filesystem entirely.
    Secrets file wins when both are present, so local development is
    unaffected.
    """
    try:
        value = st.secrets[name]
        if value:
            return str(value)
    except Exception:
        pass

    value = os.environ.get(name, "").strip()
    return value or None


def _configured() -> dict[str, str]:
    """Map role -> password, ignoring anything unset or left as placeholder."""
    out: dict[str, str] = {}
    for role, key in _SECRET_FOR_ROLE.items():
        value = _secret(key)
        if value and value != _PLACEHOLDER:
            out[role] = value

    # Backwards compatible with the earlier single-password setup.
    legacy = _secret("APP_PASSWORD")
    if legacy and legacy != _PLACEHOLDER and VIEWER not in out:
        out[VIEWER] = legacy

    return out


def current_role() -> str | None:
    return st.session_state.get(_ROLE_KEY)


def is_editor() -> bool:
    return current_role() == EDITOR


def require_password() -> str:
    """
    Block the rest of the script until a valid password is entered.
    Returns the role. Call immediately after st.set_page_config().

    Fails closed: with nothing configured the app refuses to start.
    """
    role = current_role()
    if role:
        return role

    passwords = _configured()

    if not passwords:
        st.error(
            "No passwords are configured, so this app will not start.\n\n"
            "Set `APP_PASSWORD_VIEWER` and `APP_PASSWORD_EDITOR` in "
            "`.streamlit/secrets.toml` locally, or under Settings → Secrets "
            "on Streamlit Community Cloud."
        )
        st.stop()

    st.title("Manufacturing Dashboards")
    st.caption("Internal demo — synthetic data. Enter your password.")

    with st.form("login"):
        entered = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter")

    if submitted:
        for candidate_role, expected in passwords.items():
            # Constant-time compare so timing does not leak the password.
            if hmac.compare_digest(entered, expected):
                st.session_state[_ROLE_KEY] = candidate_role
                st.rerun()
        st.error("Incorrect password.")

    if EDITOR not in passwords:
        st.info(
            "Only a viewer password is configured. Add `APP_PASSWORD_EDITOR` "
            "to enable the data-entry forms."
        )

    st.stop()


def sidebar_badge() -> None:
    """Show the signed-in role, with a way to drop back to the login screen."""
    role = current_role()
    if not role:
        return
    label = "Editor — can add entries" if role == EDITOR else "Viewer — read only"
    st.sidebar.caption(f"Signed in as **{label}**")
    if st.sidebar.button("Sign out", width="stretch"):
        st.session_state.pop(_ROLE_KEY, None)
        st.rerun()
