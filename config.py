"""Shared constants for every page."""

from __future__ import annotations

from datetime import date
from pathlib import Path

APP_DIR = Path(__file__).parent
ASSETS_DIR = APP_DIR / "assets"
DATA_DIR = APP_DIR / "data"


def today() -> date:
    """Single source of 'now', so it can be pinned for testing."""
    return date.today()


# Sites currently in scope for the launch tracker.
PLANTS = ["Kentwood", "Marshall", "Wellington", "North Attleboro"]

DIVISIONS = ["MS", "PS"]

# NN brand blues, sampled from the logo.
BRAND_BLUE = "#416AB9"
BRAND_LIGHT = "#35B0F1"

# How far ahead a gate counts as "coming up" rather than simply open.
DUE_SOON_DAYS = 14

# Gate status colours.
#   complete    -> green
#   behind      -> red
#   due soon    -> light blue, the NN secondary brand colour
#   in progress -> yellow
GATE_COLORS = {
    "Complete": "#2CA02C",
    "In progress": "#E8A33D",
    "Due soon": "#35B0F1",
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

# Legacy: the capacity page still works in manufacturing weeks. It is labelled
# future state because it runs on entirely invented data.
CAPACITY_YEAR = 2026
CAPACITY_CURRENT_WEEK = 33
