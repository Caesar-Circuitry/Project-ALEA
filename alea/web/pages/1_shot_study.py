"""Shot-study results explorer."""

from pathlib import Path

import streamlit as st

from alea.sim.results import (
    FACTORS,
    SCORE_KEY,
    describe,
    detect_fidelity,
    factor_effects,
    load_summary,
    worst_best,
)
from alea.web import common, study_demo

st.set_page_config(page_title="Shot study", layout="wide")
source = common.data_source_selector()
st.title("Shot study")

rows: list[dict] = []
if source == "synthetic":
    seed = st.sidebar.number_input("Seed", min_value=0, value=0, step=1)
    rows = study_demo.build_summary(int(seed))
    st.caption("Synthetic data: seeded fake results, not from the simulator.")
else:
    results_dir = st.text_input("Results directory", value="results/study")
    path = Path(results_dir)
    if not path.is_dir():
        st.info(f"No results directory at `{path}`. Run `just study` or pick another folder.")
    else:
        try:
            fidelity = detect_fidelity(path)
            if fidelity is None:
                st.info(f"`{path}` holds no study results yet.")
            else:
                rows = load_summary(path)
                st.caption(f"Fidelity: {fidelity}, {len(rows)} conditions.")
        except (ValueError, FileNotFoundError, KeyError) as exc:
            st.warning(f"Could not read results: {exc}")

if rows:
    st.subheader("Conditions")
    st.dataframe(rows, use_container_width=True)
    st.subheader("Factor effects (mean % scored of fired)")
    effects = factor_effects(rows)
    cols = st.columns(len(FACTORS))
    for col, (label, _key) in zip(cols, FACTORS, strict=True):
        with col:
            st.caption(label)
            st.bar_chart(
                {
                    "value": [str(v) for v, _ in effects[label]],
                    SCORE_KEY: [m for _, m in effects[label]],
                },
                x="value",
                y=SCORE_KEY,
            )
    worst, best = worst_best(rows)
    left, right = st.columns(2)
    with left:
        st.subheader("Worst conditions")
        for r in worst:
            st.write(describe(r))
    with right:
        st.subheader("Best conditions")
        for r in best:
            st.write(describe(r))
