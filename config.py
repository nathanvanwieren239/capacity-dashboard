"""Shared constants for every page."""

from __future__ import annotations

from pathlib import Path

APP_DIR = Path(__file__).parent
ASSETS_DIR = APP_DIR / "assets"
DATA_DIR = APP_DIR / "data"

YEAR = 2026
CURRENT_WEEK = 33  # TODO: replace with date.today().isocalendar().week

# NN brand blues, sampled from the logo.
BRAND_BLUE = "#416AB9"
BRAND_LIGHT = "#35B0F1"

# Gate status colors, as specified in review:
#   complete -> green, in progress -> yellow, behind schedule -> red
GATE_COLORS = {
    "Complete": "#2CA02C",
    "In progress": "#E8A33D",
    "Behind": "#D62728",
}

# Project-level status is assessed separately from individual gate status.
PROJECT_STATUS_COLORS = {
    "Green": "#2CA02C",
    "Yellow": "#E8A33D",
    "Red": "#D62728",
}

PROJECT_STATUS_ICON = {"Green": "🟢", "Yellow": "🟡", "Red": "🔴"}

# Simple launches skip gates 1-3; marked so they read differently at a glance.
SIMPLE_LAUNCH_TAG = "◇ SIMPLE"
PROTOTYPE_TAG = "▷ PROTO"
