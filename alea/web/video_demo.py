"""Synthetic video-review artefacts and loaders for the web viewer (phase 6).

Plain dicts in the phase 2 JSON shapes (schema_version 1): `shots.jsonl`, `landmarks.jsonl`,
`calibration.json`. Parsed with `json` only so this does not depend on `alea.video`.
Pixel coordinates only; derived inches are not computed here.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

SCHEMA_VERSION = 1
_FPS_HZ = 30.0
_WIDTH_PX = 1280
_HEIGHT_PX = 720


def _check_schema(d: object, where: str) -> dict:
    if not isinstance(d, dict):
        raise ValueError(f"{where}: expected a JSON object, got {type(d).__name__}")
    if d.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"{where}: unsupported schema_version {d.get('schema_version')!r}; "
            f"expected {SCHEMA_VERSION}"
        )
    return d


def load_jsonl(path: str | Path) -> list[dict]:
    """Read a JSONL file; every record must carry `schema_version == 1`."""
    p = Path(path)
    out: list[dict] = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{p.name}:{n}: invalid JSON ({e.msg})") from e
        out.append(_check_schema(rec, f"{p.name}:{n}"))
    return out


def load_json(path: str | Path) -> dict:
    """Read a JSON object with `schema_version == 1`."""
    p = Path(path)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{p.name}: invalid JSON ({e.msg})") from e
    return _check_schema(d, p.name)


def write_jsonl(path: str | Path, records: list[dict]) -> None:
    Path(path).write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def make_shots(n_shots: int = 4, seed: int = 0) -> list[dict]:
    """Shot observations whose ball track is a pixel-space parabola (v down)."""
    rng = np.random.default_rng(seed)
    kinds = ["hive_cell", "floor", "hive_frame", "wall"]
    shots: list[dict] = []
    for i in range(n_shots):
        n_pts = int(rng.integers(8, 13))
        launch_frame = int(rng.integers(100, 400))
        u0 = float(rng.uniform(250, 500))
        v0 = float(rng.uniform(450, 560))
        du = float(rng.uniform(25, 40))  # px per track step
        rise = float(rng.uniform(150, 260))  # apex height above launch, px
        s = np.linspace(0.0, 1.0, n_pts)
        u = u0 + du * np.arange(n_pts)
        v = v0 - rise * 4.0 * s * (1.0 - s) + 0.3 * rise * s  # up, then back down
        step = 2
        track = [
            {
                "frame": launch_frame + step * k,
                "t_pts_s": round((launch_frame + step * k) / _FPS_HZ, 6),
                "u_px": round(float(u[k] + rng.normal(0, 0.5)), 2),
                "v_px": round(float(v[k] + rng.normal(0, 0.5)), 2),
                "source": "click",
            }
            for k in range(n_pts)
        ]
        last = track[-1]
        shots.append(
            {
                "schema_version": SCHEMA_VERSION,
                "observation_id": f"demo-{i + 1:03d}",
                "robot": {
                    "frame": launch_frame,
                    "u_px": round(u0 - 40.0, 2),
                    "v_px": round(v0 + 60.0, 2),
                    "click_kind": "top_plate_centre",
                    "click_z_in": 16.0,
                },
                "launch": {
                    "frame": launch_frame,
                    "t_pts_s": round(launch_frame / _FPS_HZ, 6),
                    "confidence_frames": 1,
                },
                "ball_track": track,
                "landing": {
                    "frame": last["frame"] + step,
                    "u_px": round(last["u_px"] + du * 0.5, 2),
                    "v_px": round(last["v_px"] + 15.0, 2),
                    "kind": kinds[i % len(kinds)],
                    "z_in_assumed": 0.0,
                },
                "outcome": {
                    "result": "made" if i % 2 == 0 else "miss",
                    "target": "hive_cell",
                    "notes": "synthetic",
                },
                "event_code": "DEMO",
                "match_label": f"Q{i + 1}",
                "alliance": "red" if i % 2 == 0 else "blue",
                "team_number": 24331,
            }
        )
    return shots


def make_landmarks(seed: int = 0) -> list[dict]:
    rng = np.random.default_rng(seed + 1)
    ids = [
        "field_floor_corner_xlo_ylo",
        "field_floor_corner_xhi_ylo",
        "field_floor_corner_xhi_yhi",
        "field_floor_corner_xlo_yhi",
        "hive_red_pivot",
    ]
    base = [(200, 640), (1080, 640), (900, 300), (380, 300), (640, 250)]
    return [
        {
            "schema_version": SCHEMA_VERSION,
            "frame": 0,
            "t_pts_s": 0.0,
            "landmark_id": lid,
            "u_px": round(float(u + rng.normal(0, 1.0)), 2),
            "v_px": round(float(v + rng.normal(0, 1.0)), 2),
        }
        for lid, (u, v) in zip(ids, base, strict=True)
    ]


def make_calibration(seed: int = 0) -> dict:
    rng = np.random.default_rng(seed + 2)
    return {
        "schema_version": SCHEMA_VERSION,
        "calibration_id": "demo-cal",
        "video": {
            "file": "demo.mp4",
            "width_px": _WIDTH_PX,
            "height_px": _HEIGHT_PX,
            "fps_nominal": _FPS_HZ,
        },
        "model": "pinhole_k1k2",
        "camera": {
            "f_px": 1050.0 + float(rng.normal(0, 5)),
            "rotation": [[1.0, 0.0, 0.0], [0.0, -0.8, -0.6], [0.0, 0.6, -0.8]],
            "position_in": [72.0, -40.0, 60.0],
            "principal_point_px": [_WIDTH_PX / 2, _HEIGHT_PX / 2],
            "distortion": {"k1": -0.05, "k2": 0.01},
        },
        "rms_reprojection_px": 1.4,
        "max_loo_residual_px": 3.1,
        "warnings": ["synthetic data: not a real calibration"],
        "camera_setup_id": "DEMO-cam1",
    }
