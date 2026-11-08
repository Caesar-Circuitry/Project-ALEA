"""Launcher efficiency page (roadmap phase 6): measured vs sim-assumed wheel efficiency."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from alea.game.biobuzz import AIR_DRAG, TICKS_TO_IN_S
from alea.web.efficiency_demo import (
    SIM_ASSUMED_EFFICIENCY,
    column,
    mean_sd,
    per_burst_index,
    per_session,
    read_measurements_csv,
    synthetic_rows,
)

st.set_page_config(page_title="Launcher efficiency", layout="wide")
st.title("Launcher efficiency")

mode = st.sidebar.radio("Data", ["synthetic", "real"], key="efficiency_mode")
rows = None
if mode == "synthetic":
    rows = synthetic_rows()
else:
    path = st.sidebar.text_input("Measurement CSV path", key="efficiency_path")
    if path:
        try:
            rows = read_measurements_csv(path)
        except (OSError, ValueError) as exc:
            st.error(f"Could not load CSV: {exc}")
    else:
        st.info("Enter the path of a launcher measurement CSV in the sidebar.")

with st.expander("How to collect measurements", expanded=rows is None):
    st.write(
        "Follow the hive-shot-lab protocol in `docs/calibration-protocol.md`: film bursts of "
        "1-3 shots per session, log flywheel ticks, and run the hivelab fit to produce the CSV."
    )

if rows is not None and not rows:
    st.warning("The CSV has no rows.")
elif rows:
    eff = column(rows, "efficiency")
    m, s = mean_sd(eff)
    st.metric("Mean efficiency", f"{m:.3f}", f"{m - SIM_ASSUMED_EFFICIENCY:+.3f} vs sim")
    st.write(
        f"n = {eff.size}, sd = {s:.3f}. The sim assumes {SIM_ASSUMED_EFFICIENCY:.2f} "
        f"(TICKS_TO_IN_S = {TICKS_TO_IN_S:.5f} in/s per tick)."
    )

    left, right = st.columns(2)
    with left:
        st.subheader("Efficiency histogram")
        fig, ax = plt.subplots()
        ax.hist(eff, bins=12, color="C0")
        ax.axvline(SIM_ASSUMED_EFFICIENCY, color="C3", ls="--", label="sim assumed")
        ax.axvline(m, color="k", label="measured mean")
        ax.set_xlabel("efficiency (v_exit / wheel surface speed)")
        ax.set_ylabel("shots")
        ax.legend()
        st.pyplot(fig)
        plt.close(fig)
    with right:
        st.subheader("Efficiency vs flywheel speed")
        fig, ax = plt.subplots()
        ax.scatter(
            [r["flywheel_ticks_per_s_before"] for r in rows],
            [r["efficiency"] for r in rows],
            s=20,
        )
        ax.axhline(SIM_ASSUMED_EFFICIENCY, color="C3", ls="--")
        ax.set_xlabel("flywheel ticks/s before shot")
        ax.set_ylabel("efficiency")
        st.pyplot(fig)
        plt.close(fig)

    st.subheader("Per session")
    st.dataframe(pd.DataFrame(per_session(rows)), hide_index=True)
    st.subheader("Per burst index")
    st.dataframe(pd.DataFrame(per_burst_index(rows)), hide_index=True)

    st.subheader("Fitted drag")
    drag = column(rows, "drag_per_s")
    dm, ds = mean_sd(drag)
    st.write(f"Fitted drag_per_s: mean {dm:.3f}, sd {ds:.3f}; sim AIR_DRAG = {AIR_DRAG}.")
    fig, ax = plt.subplots()
    ax.hist(drag, bins=10, color="C2")
    ax.axvline(AIR_DRAG, color="C3", ls="--", label="AIR_DRAG")
    ax.set_xlabel("drag_per_s")
    ax.legend()
    st.pyplot(fig)
    plt.close(fig)
