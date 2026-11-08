"""Match reflection page (roadmap phase 6): renders a phase-5 reflection report."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from alea.web.reflection_demo import (
    SEVERITIES,
    load_report,
    synthetic_report,
    validate_report,
)

st.set_page_config(page_title="Match reflection", layout="wide")
st.title("Match reflection")
st.warning("match-reflection pipeline is a prototype (phase 5)")

mode = st.sidebar.radio("Data", ["synthetic", "real"], key="reflection_mode")
report = None
if mode == "synthetic":
    report = synthetic_report()
else:
    path = st.sidebar.text_input("Report JSON path", key="reflection_path")
    if path:
        try:
            report = load_report(path)
        except (OSError, ValueError) as exc:
            st.error(f"Could not load report: {exc}")
    else:
        st.info("Enter the path of a reflection report JSON file in the sidebar.")

if report is not None:
    problems = validate_report(report)
    if problems:
        st.error("Report has problems:\n\n" + "\n".join(f"- {p}" for p in problems))
        st.stop()

    match = report["match"]
    st.subheader(
        f"{match['event_code']} {match['match_label']} - {match['alliance']} alliance, "
        f"team {match['team_number']}"
    )
    st.write(report["summary"])

    st.header("Metrics")
    rows = []
    for name, m in report["metrics"].items():
        rows.append(
            {
                "metric": name + (" (inferred)" if m["source"] == "inferred" else ""),
                "measured": m["value"],
                "expected": m["expected"],
                "difference": m["value"] - m["expected"],
                "unit": m["unit"],
                "source": m["source"],
                "note": m["note"],
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True)

    st.header("Timeline")
    events = report["timeline"]
    kinds = sorted({e["kind"] for e in events})
    fig, ax = plt.subplots(figsize=(9, 0.6 * len(kinds) + 1.2))
    for e in events:
        y = kinds.index(e["kind"])
        inferred = e["source"] == "inferred"
        ax.scatter(
            e["t_s"],
            y,
            s=60,
            facecolors="none" if inferred else "C0",
            edgecolors="C0",
            linewidths=1.5,
        )
    ax.set_yticks(range(len(kinds)), kinds)
    ax.set_xlabel("time (s)")
    ax.set_title("filled = measured, hollow = inferred")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    st.header("Findings")
    for sev in SEVERITIES:
        group = [f for f in report["findings"] if f["severity"] == sev]
        if not group:
            continue
        st.subheader(sev.capitalize())
        for f in group:
            tag = " (inferred)" if f["source"] == "inferred" else ""
            with st.expander(f["title"] + tag):
                st.write(f"Evidence: {f['evidence']}")
                st.write(f"Suggestion: {f['suggestion']}")

    st.header("Gaps")
    if report["gaps"]:
        for g in report["gaps"]:
            st.write(f"- {g['what']}: {g['why_missing']} (filled by: {g['filled_by']})")
    else:
        st.write("No gaps reported.")

    st.header("Privacy")
    st.caption("Reports are text/JSON only. No video frames are stored in or shown from a report.")
