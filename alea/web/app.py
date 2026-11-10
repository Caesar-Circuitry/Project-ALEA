"""ALEA web app home page. Run: uv run streamlit run alea/web/app.py"""

import streamlit as st

from alea.web import common

st.set_page_config(page_title="ALEA", layout="wide")
source = common.data_source_selector()

st.title("ALEA")
st.write(
    "Strategy platform of FTC team 24331 Caesar Circuitry for BIOBUZZ 2026-27: a validated "
    "Monte Carlo shot simulator, robot log import, video review and match analysis."
)
st.info(f"Data source: **{source}**. Change it in the sidebar.")
st.subheader("Pages")
st.markdown(
    "- **Shot study**: explore simulated shot-study results by factor.\n"
    "- **Match logs**: flywheel velocity and detected launches from robot logs.\n"
    "- **Video review**: review match video with tracked events.\n"
    "- **Match reflection**: post-match reflection and driver critique.\n"
    "- **Launcher efficiency**: launcher efficiency across shots and matches."
)
if source == "synthetic":
    st.caption("Synthetic mode shows seeded fake data so every page works without files.")
