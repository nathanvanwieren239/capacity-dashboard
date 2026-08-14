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

# Gate review / status colors.
STATUS_COLORS = {
    "Green": "#2CA02C",
    "Yellow": "#E8A33D",
    "Red": "#D62728",
    "Not started": "#C7CBD1",
    "Complete": "#5B7FCC",
}
