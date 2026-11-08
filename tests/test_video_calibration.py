"""Calibration records: fitting from clicks, JSON, degenerate input (roadmap phase 2, stage 2.1)."""

import numpy as np
import pytest

from alea.game import biobuzz as g
from alea.video.calibration import (
    Calibration,
    ClickedLandmark,
    VideoInfo,
    calibrate,
    read_calibration,
    write_calibration,
)
from alea.video.geometry import Camera, GeometryError
from alea.video.landmarks import landmarks_xyz_in

W, H = 1920, 1080
F = 1660.0
NAMES = [
    "field_floor_corner_xlo_ylo",
    "field_floor_corner_xhi_ylo",
    "field_floor_corner_xlo_yhi",
    "field_floor_corner_xhi_yhi",
    "field_wall_top_corner_xlo_ylo",
    "field_wall_top_corner_xhi_ylo",
    "field_wall_top_corner_xlo_yhi",
    "field_wall_top_corner_xhi_yhi",
    "hive_red_pivot",
    "hive_blue_pivot",
]
CENTRE = np.array([g.FIELD_SIZE_IN / 2, g.FIELD_SIZE_IN / 2, 0.0])


def look_at(position, target, f=F) -> Camera:
    pos = np.asarray(position, float)
    z = np.asarray(target, float) - pos
    z /= np.linalg.norm(z)
    x = np.cross(z, [0, 0, 1.0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return Camera(f, np.stack([x, y, z]), pos, W / 2, H / 2)


AUDIENCE = look_at([70, -400, 120], CENTRE)
INFO = VideoInfo(width_px=W, height_px=H)


def clicks_for(cam, names, sigma_px, seed, frame=None) -> list[ClickedLandmark]:
    rng = np.random.default_rng(seed)
    px = cam.project(landmarks_xyz_in(names)) + rng.normal(0, sigma_px, (len(names), 2))
    pairs = zip(names, px, strict=True)
    return [ClickedLandmark(n, float(u), float(v), frame) for n, (u, v) in pairs]


# --- JSON


def test_calibration_roundtrip(tmp_path) -> None:
    cl = clicks_for(AUDIENCE, NAMES, 1.0, 1, frame=10)
    info = VideoInfo("Q12.mp4", "abc", W, H, 29.97, 100)
    cal = calibrate(cl, info, (0, 100), "ab", camera_setup_id="USALTX-aud")
    path = tmp_path / "cal.json"
    write_calibration(cal, path)
    back = read_calibration(path)
    assert isinstance(back, Calibration)
    assert back.model == "pinhole_refined" and back.landmarks == cal.landmarks
    assert back.camera_setup_id == "USALTX-aud" and back.landmark_ids == sorted(NAMES)
    assert back.camera is not None and cal.camera is not None
    assert np.allclose(back.camera.rotation, cal.camera.rotation)
    assert back.floor_point_in(W / 2, H / 2) == pytest.approx(cal.floor_point_in(W / 2, H / 2))
    assert back.max_floor_in is not None and back.max_floor_in > 0
    assert all(c.residual_px is not None for c in back.landmarks)
    assert all(c.loo_residual_px is not None for c in back.landmarks)
    floor = [c for c in back.landmarks if c.name.startswith("field_floor")]
    assert all(c.floor_major_in and c.floor_minor_in for c in floor)
    assert all(c.floor_major_in is None for c in back.landmarks if c.name.startswith("field_wall"))


def test_json_carries_schema_version_and_setup_id() -> None:
    d = calibrate(clicks_for(AUDIENCE, NAMES, 0.5, 0), INFO, camera_setup_id="EVT-aud").to_dict()
    assert d["schema_version"] == 1 and d["camera_setup_id"] == "EVT-aud"
    assert d["landmark_ids"] == sorted(NAMES)


def test_bad_schema_and_empty(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version": 99}', encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        read_calibration(path)
    with pytest.raises(GeometryError, match="no landmark"):
        calibrate([], VideoInfo())


def test_version1_file_without_distortion_still_reads() -> None:
    cal = calibrate(clicks_for(AUDIENCE, NAMES, 0.0, 0), INFO)
    d = cal.to_dict()
    del d["camera"]["distortion"], d["k1_sigma"], d["click_noise_px"]
    back = Calibration.from_dict(d)
    assert back.camera is not None and back.camera.k1 == 0.0 and back.camera.k2 == 0.0
    assert back.k1_sigma is None and back.click_noise_px is None


# --- custom ids and degenerate input


def test_custom_ids_are_ignored_with_warning() -> None:
    cl = clicks_for(AUDIENCE, NAMES, 0.5, 0)
    cl.append(ClickedLandmark("custom_tile_seam_a", 900.0, 700.0))
    cal = calibrate(cl, INFO)
    assert len(cal.landmarks) == len(NAMES)
    assert any("custom_tile_seam_a" in w for w in cal.warnings)


def test_unknown_landmark_id_is_rejected() -> None:
    with pytest.raises(KeyError, match="unknown landmark"):
        calibrate([ClickedLandmark("not_a_landmark", 1.0, 1.0)], INFO)


def test_fewer_than_four_floor_points_raise() -> None:
    floor3 = NAMES[:3]
    with pytest.raises(GeometryError, match="at least 4 floor points"):
        calibrate(clicks_for(AUDIENCE, floor3, 0.0, 0), INFO)
    # elevated points do not make up for missing floor points
    with pytest.raises(GeometryError, match="at least 4 floor points"):
        calibrate(clicks_for(AUDIENCE, [*floor3, *NAMES[4:]], 0.0, 0), INFO)


def test_collinear_floor_points_raise() -> None:
    # four floor-corner clicks whose pixels lie on one line (a degenerate click session)
    cl = [ClickedLandmark(n, 100.0 + 50 * i, 200.0 + 10 * i) for i, n in enumerate(NAMES[:4])]
    with pytest.raises(GeometryError, match="collinear"):
        calibrate(cl, INFO)
    # world-space collinearity of floor landmarks is covered in test_video_geometry.py::
    # test_error_cases (fit_homography); the field has no 4 named floor points on one line.


# --- independent calibrations per event, varying subsets, pooling

EVENTS = {
    "wide_audience": look_at([70, -400, 120], CENTRE, 1660),
    "tele_far": look_at([-100, -600, 200], CENTRE, 3000),
    "corner_wide": look_at([-250, -250, 140], CENTRE, 1200),
    "high_end_zoomed": look_at([300, 70, 260], CENTRE, 2200),
}


@pytest.mark.parametrize("event", list(EVENTS))
def test_each_event_fits_independently(event: str) -> None:
    cam = EVENTS[event]
    cal = calibrate(clicks_for(cam, NAMES, 1.0, 5), INFO)
    assert cal.camera is not None
    assert cal.camera.f_px == pytest.approx(cam.f_px, rel=0.06)
    dist = np.linalg.norm(cam.position_in - CENTRE)
    assert np.linalg.norm(cal.camera.position_in - cam.position_in) < 0.1 * dist
    assert cal.rms_reprojection_px < 2.0


SUBSETS = {
    "corners_and_walls": NAMES[:8],
    "hive_heavy": [
        *NAMES[:4],
        "hive_red_pivot",
        "hive_blue_pivot",
        "hive_frame_corner_xlo_ylo_zhi",
        "hive_frame_corner_xhi_yhi_zhi",
        "hive_frame_corner_xhi_ylo_zhi",
    ],
    "near_half_only": [
        NAMES[0],
        NAMES[1],
        "field_wall_top_corner_xlo_ylo",
        "field_wall_top_corner_xhi_ylo",
        "hive_frame_corner_xlo_ylo_zlo",
        "hive_frame_corner_xhi_ylo_zlo",
        "hive_red_pivot",
    ],
}


@pytest.mark.parametrize("subset", list(SUBSETS))
def test_varying_landmark_subsets(subset: str) -> None:
    errs = []
    for seed in range(10):
        cal = calibrate(clicks_for(AUDIENCE, SUBSETS[subset], 0.7, seed), INFO)
        assert cal.camera is not None
        u, v = AUDIENCE.project([70, 70, 0.0])[0]
        errs.append(np.linalg.norm(np.array(cal.floor_point_in(u, v)) - np.array([70, 70])))
    assert np.mean(errs) < 3.0


def test_pooling_clicks_from_several_frames() -> None:
    first = clicks_for(AUDIENCE, NAMES[:6], 1.0, 1, frame=100)
    second = clicks_for(AUDIENCE, [*NAMES[2:8], "hive_red_pivot"], 1.0, 2, frame=900)
    cal = calibrate(first + second, INFO)  # overlapping landmarks are allowed
    assert cal.camera is not None and len(cal.landmarks) == 13
    assert {c.frame for c in cal.landmarks} == {100, 900}
    assert cal.camera.f_px == pytest.approx(F, rel=0.05)


def test_pooling_equals_one_frame_when_noise_free() -> None:
    one = calibrate(clicks_for(AUDIENCE, NAMES, 0.0, 0, frame=1), INFO)
    split = calibrate(
        clicks_for(AUDIENCE, NAMES[:6], 0.0, 0, frame=1)
        + clicks_for(AUDIENCE, NAMES[4:], 0.0, 0, frame=2),
        INFO,
    )
    assert one.camera is not None and split.camera is not None
    assert split.camera.f_px == pytest.approx(one.camera.f_px, rel=1e-5)
    assert np.allclose(split.camera.position_in, one.camera.position_in, atol=1e-2)


def test_repeated_frames_match_the_averaged_click() -> None:
    """Two equal-noise frames fit like one frame at the mean click (same weights, sigma/sqrt2)."""
    a = clicks_for(AUDIENCE, NAMES, 1.0, 11, frame=1)
    b = clicks_for(AUDIENCE, NAMES, 1.0, 12, frame=2)
    mean = [
        ClickedLandmark(x.name, (x.u_px + y.u_px) / 2, (x.v_px + y.v_px) / 2)
        for x, y in zip(a, b, strict=True)
    ]
    pooled = calibrate(a + b, INFO)
    averaged = calibrate(mean, INFO)
    assert pooled.camera is not None and averaged.camera is not None
    assert pooled.camera.f_px == pytest.approx(averaged.camera.f_px, rel=0.01)
    assert np.linalg.norm(pooled.camera.position_in - averaged.camera.position_in) < 2.0
    assert pooled.click_noise_px is not None and averaged.click_noise_px is None
