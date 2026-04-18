"""Standalone launcher for conference_material_view — for mockup verification."""
from pathlib import Path
import sys
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

st.set_page_config(
    layout="wide",
    page_title="多職種退院調整・連休対策カンファ",
    initial_sidebar_state="collapsed",
)

from views.conference_material_view import render_conference_material_view

render_conference_material_view(today=date(2026, 4, 17))
