"""Kineticist - initial rates from plate-reader kinetics, checked and corrected by eye."""

from pathlib import Path

import streamlit as st

import session
from kineticist import theme  # also activates the Plotly template

ASSETS = Path(__file__).resolve().parent / "assets"

st.set_page_config(page_title="Kineticist", page_icon=str(ASSETS / "icon.svg"),
                   layout="wide")
st.logo(str(ASSETS / "logo.svg"), icon_image=str(ASSETS / "icon.svg"), size="large")

page = st.navigation([
    st.Page("app_pages/fits.py", title="Fits", icon=":material/grid_on:", default=True),
    st.Page("app_pages/rates.py", title="Rates", icon=":material/leaderboard:"),
    st.Page("app_pages/qc.py", title="Quality control", icon=":material/verified:"),
    st.Page("app_pages/export.py", title="Export", icon=":material/download:"),
    st.Page("app_pages/about.py", title="About", icon=":material/info:"),
], position="top")
st.html(theme.NAV_CSS)

session.init()
session.sidebar()
page.run()
