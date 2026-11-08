"""Shared bits of the Streamlit app: the data-source selector and its session key."""

from __future__ import annotations

import streamlit as st

SOURCE_KEY = "data_source"
SOURCES = ("synthetic", "real")


def data_source() -> str:
    """Current data source, `synthetic` until the user picks `real`."""
    value = st.session_state.get(SOURCE_KEY, SOURCES[0])
    return value if value in SOURCES else SOURCES[0]


def data_source_selector() -> str:
    """Sidebar radio for synthetic / real; the choice lives in `st.session_state[SOURCE_KEY]`.

    The radio has its own widget key and is copied into SOURCE_KEY, because Streamlit forgets a
    widget's state on a page that does not draw it.
    """
    choice = st.sidebar.radio(
        "Data source",
        SOURCES,
        index=SOURCES.index(data_source()),
        key="_data_source_widget",
        help="synthetic: seeded fake data, no files needed. real: your results and database.",
    )
    st.session_state[SOURCE_KEY] = choice
    return choice
