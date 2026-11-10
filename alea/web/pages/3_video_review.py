"""Video review viewer: shots, ball tracks and calibration from phase 2 JSON (roadmap phase 6).

Pixel space only. Derived inches are not computed here; phase 2.3 analyze does that.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from alea.web import video_demo

st.set_page_config(page_title="Video review", layout="wide")
st.title("Video review")
st.caption(
    "Pixel-space viewer for shots, ball tracks and calibration. Derived inches are not "
    "computed here; phase 2.3 analyze does that."
)

mode = st.sidebar.radio("Data source", ["synthetic", "real"], index=0)

shots: list[dict] = []
landmarks: list[dict] = []
calibration: dict = {}


def _try(label: str, path: str, loader, default):
    if not path.strip():
        return default
    p = Path(path.strip())
    if not p.is_file():
        st.warning(f"{label}: file not found: {p}")
        return default
    try:
        return loader(p)
    except (ValueError, OSError) as e:
        st.error(f"{label}: could not read {p.name}: {e}")
        return default


if mode == "synthetic":
    seed = int(st.sidebar.number_input("Seed", value=0, step=1))
    shots = video_demo.make_shots(seed=seed)
    landmarks = video_demo.make_landmarks(seed=seed)
    calibration = video_demo.make_calibration(seed=seed)
else:
    shots_path = st.sidebar.text_input("shots.jsonl path", "")
    lm_path = st.sidebar.text_input("landmarks.jsonl path", "")
    cal_path = st.sidebar.text_input("calibration.json path", "")
    shots = _try("Shots", shots_path, video_demo.load_jsonl, [])
    landmarks = _try("Landmarks", lm_path, video_demo.load_jsonl, [])
    calibration = _try("Calibration", cal_path, video_demo.load_json, {})
    if not (shots or landmarks or calibration):
        st.info("Enter at least one file path in the sidebar.")


def _g(d: object, key: str, default=None) -> Any:
    return d.get(key, default) if isinstance(d, dict) else default


st.header("Shots")
if not shots:
    st.info("No shots loaded.")
else:
    rows = [
        {
            "observation_id": _g(s, "observation_id", ""),
            "match_label": _g(s, "match_label", ""),
            "alliance": _g(s, "alliance", ""),
            "team_number": _g(s, "team_number"),
            "launch_frame": _g(_g(s, "launch", {}), "frame"),
            "n_track_points": len(_g(s, "ball_track", []) or []),
            "landing_kind": _g(_g(s, "landing", {}), "kind", ""),
            "outcome_result": _g(_g(s, "outcome", {}), "result", ""),
        }
        for s in shots
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    ids = [str(r["observation_id"]) or f"shot {i}" for i, r in enumerate(rows)]
    if st.session_state.get("selected_shot") not in ids:
        st.session_state["selected_shot"] = ids[0]
    st.selectbox("Selected shot", ids, key="selected_shot")
    shot = shots[ids.index(st.session_state["selected_shot"])]

    track = _g(shot, "ball_track", []) or []
    fig, ax = plt.subplots(figsize=(7, 4))
    pts = [(_g(t, "u_px"), _g(t, "v_px")) for t in track]
    pts = [(u, v) for u, v in pts if u is not None and v is not None]
    if pts:
        ax.plot([p[0] for p in pts], [p[1] for p in pts], "o-", color="#1f77b4", label="ball track")
    robot: dict = _g(shot, "robot", {}) or {}
    if _g(robot, "u_px") is not None and _g(robot, "v_px") is not None:
        ax.plot(robot["u_px"], robot["v_px"], "s", color="#d62728", label="robot click")
    landing: dict = _g(shot, "landing", {}) or {}
    if _g(landing, "u_px") is not None and _g(landing, "v_px") is not None:
        ax.plot(
            landing["u_px"],
            landing["v_px"],
            "x",
            color="#2ca02c",
            ms=10,
            mew=2,
            label=f"landing ({_g(landing, 'kind', 'unknown')})",
        )
    ax.set_xlabel("u (px)")
    ax.set_ylabel("v (px, down)")
    ax.invert_yaxis()
    ax.grid(True, alpha=0.3)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(loc="best")
    ax.set_title(str(st.session_state["selected_shot"]))
    st.pyplot(fig)
    plt.close(fig)

st.header("Calibration")
if not calibration:
    st.info("No calibration loaded.")
else:
    cam = _g(calibration, "camera", {}) or {}
    f_px = _g(cam, "f_px")
    rms = _g(calibration, "rms_reprojection_px")
    loo = _g(calibration, "max_loo_residual_px")
    c1, c2, c3 = st.columns(3)
    c1.metric("Focal length (px)", "n/a" if f_px is None else f"{f_px:.1f}")
    c2.metric("Reprojection RMS (px)", "n/a" if rms is None else f"{rms:.2f}")
    c3.metric("Max leave-one-out (px)", "n/a" if loo is None else f"{loo:.2f}")
    st.json(
        {
            k: _g(cam, k)
            for k in ("f_px", "rotation", "position_in", "principal_point_px", "distortion")
        },
        expanded=False,
    )
    for w in _g(calibration, "warnings", []) or []:
        st.warning(str(w))

st.subheader("Landmark clicks")
if landmarks:
    st.dataframe(
        pd.DataFrame(
            [
                {k: _g(r, k) for k in ("frame", "t_pts_s", "landmark_id", "u_px", "v_px")}
                for r in landmarks
            ]
        ),
        width="stretch",
        hide_index=True,
    )
else:
    st.info("No landmark clicks loaded.")
