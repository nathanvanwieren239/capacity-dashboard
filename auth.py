"""
Individual-login password gate.
 
Replaces the two-shared-password scheme with named accounts, stored in the
`users` table (see schema.sql). Same reason the CSV store became SQLite:
the previous version could tell you *that* someone with the editor password
made a change, never *who*. This closes that gap — the audit log now
records a real username.
 
Public API is unchanged from the shared-password version, so app.py and the
views do not need to change:
 
    auth.require_password()   -> still blocks until signed in, returns role
    auth.current_role()       -> still "viewer" or "editor"
    auth.is_editor()          -> unchanged
    auth.sidebar_badge()      -> unchanged
 
One addition — `current_username()` — returns the signed-in person's actual
username, for anything that wants to attribute a change to a person rather
than a role. The one caller that matters, `views/launch_page.py`, should
swap its `role = auth.current_role()` line for
`role = auth.current_username()` before passing it into `store.*` calls, so
the audit log's `role` column ends up holding a name instead of "editor".
See the merge notes for the exact line.
 
Passwords are salted SHA-256, not bcrypt/argon2 — deliberately simple. This
is an internal tool with a handful of known accounts behind a locked-down
network, not a public signup surface being defended against large-scale
offline brute-forcing. Worth revisiting if that ever changes.
"""
 
from __future__ import annotations
 
import hashlib
import hmac
import sqlite3
 
import streamlit as st
 
import db
 
_ROLE_KEY = "_auth_role"
_USER_KEY = "_auth_username"
 
VIEWER = "viewer"
EDITOR = "editor"
 
 
# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    import secrets
    salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${digest}"
 
 
def _verify(stored_hash: str, password: str) -> bool:
    salt, digest = stored_hash.split("$", 1)
    check = hashlib.sha256((salt + password).encode()).hexdigest()
    return hmac.compare_digest(check, digest)
 
 
# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------
def _find_user(username: str) -> sqlite3.Row | None:
    conn = db.connect()
    try:
        return conn.execute(
            "SELECT username, password_hash, role FROM users "
            "WHERE username = ? AND active = 1",
            (username,),
        ).fetchone()
    finally:
        conn.close()
 
 
# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
def current_role() -> str | None:
    return st.session_state.get(_ROLE_KEY)
 
 
def current_username() -> str:
    """Used when writing audit log entries — falls back to the role if,
    somehow, no username is on the session (shouldn't happen post-login)."""
    return st.session_state.get(_USER_KEY) or current_role() or "unknown"
 
 
def is_editor() -> bool:
    return current_role() == EDITOR
 
 
def require_password() -> str:
    """
    Block the rest of the script until a valid username/password is
    entered. Returns the role. Call immediately after st.set_page_config().
 
    Fails closed: with no users table populated, the app still starts (so
    the error is visible rather than a blank page) but nobody can sign in.
    """
    role = current_role()
    if role:
        return role
 
    st.title("Manufacturing Dashboards")
    st.caption("Internal — sign in with your assigned username.")
 
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
 
    if submitted:
        row = _find_user(username.strip())
        if row and _verify(row["password_hash"], password):
            st.session_state[_ROLE_KEY] = row["role"]
            st.session_state[_USER_KEY] = row["username"]
            st.rerun()
        else:
            st.error("Incorrect username or password.")
 
    st.stop()
 
 
def sidebar_badge() -> None:
    """Show the signed-in person, with a way to drop back to the login screen."""
    role = current_role()
    if not role:
        return
    label = f"{current_username()} — editor" if role == EDITOR else f"{current_username()} — viewer"
    st.sidebar.caption(f"Signed in as **{label}**")
    if st.sidebar.button("Sign out", width="stretch"):
        st.session_state.pop(_ROLE_KEY, None)
        st.session_state.pop(_USER_KEY, None)
        st.rerun()
 
