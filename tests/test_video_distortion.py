"""Lens distortion, straight-edge clicks and robust loss in the camera fit (phase 2, stage 2.1)."""

import numpy as np
import pytest

from alea.video.calibration import (
    Calibration,
    ClickedLandmark,
    VideoInfo,
    calibrate,
    read_calibration,
    repeat_click_noise_px,
    write_calibration,
)
from alea.video.geometry import (
    Camera,
    LineObs,
    fit_camera,
    straight_line_deviation_px,
)
from alea.video.landmarks import edge_table, get_edge, landmarks_xyz_in

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
CENTRE = (70.65, 70.65, 0.0)
GRID = np.array([[x, y, 0.0] for x in np.linspace(10, 131, 5) for y in np.linspace(10, 131, 5)])
# airborne: three free-flight points at the hive cell height, plus the two hive mouths
AIR = np.array(
    [[40, 60, 49.0], [100, 80, 49.0], [70, 30, 49.0], [58, 54.47, 49.13], [83.5, 87.03, 49.13]]
)


def look_at(pos, f, w, h, k1=0.0, k2=0.0) -> Camera:
    p = np.asarray(pos, float)
    z = np.asarray(CENTRE) - p
    z /= np.linalg.norm(z)
    x = np.cross(z, [0, 0, 1.0])
    x /= np.linalg.norm(x)
    return Camera(f, np.stack([x, np.cross(z, x), z]), p, w / 2, h / 2, k1, k2)


# wide cameras (field fills the frame, where distortion bites) and a telephoto (field in the
# image centre, where it barely matters)
SCENES = {
    "wide_audience": ((70, -170, 110), 1000.0, 1920, 1080),
    "wide_corner": ((-120, -120, 100), 900.0, 1920, 1080),
    "telephoto": ((70, -400, 120), 1660.0, 1920, 1080),
}


def px_of(cam: Camera, p) -> tuple[float, float]:
    """Pixel (u, v) of one world point through `cam`."""
    u, v = cam.project(p)[0]
    return float(u), float(v)


def edge_obs(cam, rng, sigma, per_edge=6) -> LineObs:
    p0, p1, px = [], [], []
    for e in edge_table().values():
        for t in np.linspace(0.08, 0.92, per_edge):
            p = (1 - t) * np.array(e.a.xyz_in) + t * np.array(e.b.xyz_in)
            p0.append(e.a.xyz_in)
            p1.append(e.b.xyz_in)
            px.append(cam.project(p)[0] + rng.normal(0, sigma, 2))
    return LineObs(np.array(p0), np.array(p1), np.array(px))


def trial(cam, w, h, seed, mode, edges, sigma=1.0, robust=True, outlier=None):
    rng = np.random.default_rng(seed)
    world = landmarks_xyz_in(NAMES)
    px = cam.project(world) + rng.normal(0, sigma, (len(world), 2))
    if outlier is not None:
        px[outlier[0]] += outlier[1]
    ln = edge_obs(cam, rng, sigma) if edges else None
    fit = fit_camera(world, px, w, h, lines=ln, distortion=mode, robust=robust, compute_loo=False)
    c = fit.camera
    assert c is not None
    fl = [np.linalg.norm(c.point_on_plane_z(*px_of(cam, p), 0.0)[:2] - p[:2]) for p in GRID]
    ar = [np.linalg.norm(c.point_on_plane_z(*px_of(cam, p), p[2]) - p) for p in AIR]
    return {
        "floor": float(np.sqrt(np.mean(np.square(fl)))),
        "air": float(np.sqrt(np.mean(np.square(ar)))),
        "f": abs(c.f_px / cam.f_px - 1),
        "k1": c.k1,
    }


def sweep(cam, w, h, mode, edges, seeds=10, **kw):
    runs = [trial(cam, w, h, s, mode, edges, **kw) for s in range(seeds)]
    return {k: (float(np.mean([r[k] for r in runs])), float(np.max([r[k] for r in runs])))
            for k in runs[0]}  # fmt: skip


def row(label, r) -> str:
    return (
        f"{label}: floor {r['floor'][0]:.2f}/{r['floor'][1]:.2f} in, airborne "
        f"{r['air'][0]:.2f}/{r['air'][1]:.2f} in, f {r['f'][0]:.1%}/{r['f'][1]:.1%}, "
        f"k1 {r['k1'][0]:.3f}"
    )


def test_distort_undistort_roundtrip() -> None:
    cam = look_at((70, -170, 110), 1000.0, 1920, 1080, -0.25, 0.05)
    pts = np.array([[100.0, 80.0], [1800.0, 1000.0], [960.0, 540.0], [50.0, 1000.0]])
    assert np.allclose(cam.distort_px(cam.undistort_px(pts)), pts, atol=1e-6)
    assert np.allclose(cam.undistort_px(cam.project(landmarks_xyz_in(NAMES))),
                       cam.project_ideal(landmarks_xyz_in(NAMES)), atol=1e-6)  # fmt: skip
    # a ray through a distorted pixel hits the true 3D point
    p = np.array([60.0, 90.0, 49.13])
    u, v = cam.project(p)[0]
    assert np.allclose(cam.point_on_plane_z(u, v, 49.13), p, atol=1e-5)


@pytest.mark.parametrize("scene", ["wide_audience", "wide_corner"])
@pytest.mark.parametrize("k1", [-0.1, -0.25])
def test_distortion_terms_cut_airborne_error(scene: str, k1: float, capsys) -> None:
    pos, f, w, h = SCENES[scene]
    cam = look_at(pos, f, w, h, k1)
    before = sweep(cam, w, h, "none", True)
    after = sweep(cam, w, h, "auto", True)
    pts_before = sweep(cam, w, h, "none", False)
    pts_after = sweep(cam, w, h, "auto", False)
    with capsys.disabled():
        print(f"\n[{scene} k1={k1}] mean/worst over 10 seeds, 1 px noise, 1080p")
        print("  " + row("points+edges, no distortion", before))
        print("  " + row("points+edges, k1 fitted   ", after))
        print("  " + row("points only,  no distortion", pts_before))
        print("  " + row("points only,  k1 fitted   ", pts_after))
    assert after["air"][0] < 0.7 * before["air"][0]
    assert after["floor"][0] <= before["floor"][0]
    assert after["k1"][0] < -0.4 * abs(k1)  # right sign, a good part of it (the prior shrinks)
    assert abs(after["k1"][0] - k1) < 0.1
    assert pts_after["air"][0] < pts_before["air"][0]  # even without edge clicks


def test_zero_distortion_cameras_do_not_get_worse(capsys) -> None:
    for scene, (pos, f, w, h) in SCENES.items():
        cam = look_at(pos, f, w, h, 0.0)
        before = sweep(cam, w, h, "none", True)
        after = sweep(cam, w, h, "auto", True)
        with capsys.disabled():
            print(f"\n[{scene} k1=0]")
            print("  " + row("no distortion model", before))
            print("  " + row("k1 fitted (prior)  ", after))
        assert abs(after["k1"][0]) < 0.03
        assert after["floor"][0] <= 1.3 * before["floor"][0] + 0.1
        assert after["air"][0] <= before["air"][0] + 0.4
        assert after["f"][0] <= before["f"][0] + 0.01


def test_telephoto_distortion_is_harmless(capsys) -> None:
    pos, f, w, h = SCENES["telephoto"]
    cam = look_at(pos, f, w, h, -0.1)
    before = sweep(cam, w, h, "none", True)
    after = sweep(cam, w, h, "auto", True)
    with capsys.disabled():
        print("\n[telephoto k1=-0.1]  distortion is sub-pixel in the field region")
        print("  " + row("no distortion model", before))
        print("  " + row("k1 fitted (prior)  ", after))
    assert after["air"][0] <= before["air"][0] + 0.5


def test_720p_wide_camera(capsys) -> None:
    pos, f, w, h = SCENES["wide_audience"]
    s = 720 / 1080
    cam = look_at(pos, f * s, int(w * s), int(h * s), -0.1)
    before = sweep(cam, int(w * s), int(h * s), "none", True)
    after = sweep(cam, int(w * s), int(h * s), "auto", True)
    with capsys.disabled():
        print("\n[720p wide_audience k1=-0.1, 1 px noise]")
        print("  " + row("no distortion model", before))
        print("  " + row("k1 fitted (prior)  ", after))
    assert after["air"][0] < before["air"][0]
    assert after["air"][0] < 2.0


def test_k2_flag_runs_and_stays_bounded() -> None:
    pos, f, w, h = SCENES["wide_corner"]
    cam = look_at(pos, f, w, h, -0.2, 0.05)
    r = trial(cam, w, h, 0, "k1k2", True)
    assert r["air"] < 3.0 and r["floor"] < 1.0


def test_straight_edge_check() -> None:
    pos, f, w, h = SCENES["wide_audience"]
    rng = np.random.default_rng(0)
    e = get_edge("edge_floor_ylo")
    ts = np.linspace(0.05, 0.95, 8)
    pts = [(1 - t) * np.array(e.a.xyz_in) + t * np.array(e.b.xyz_in) for t in ts]
    straight = look_at(pos, f, w, h, 0.0).project(np.array(pts)) + rng.normal(0, 0.5, (8, 2))
    curved_cam = look_at(pos, f, w, h, -0.25)
    curved = curved_cam.project(np.array(pts)) + rng.normal(0, 0.5, (8, 2))
    assert straight_line_deviation_px(straight) < 2.0
    assert straight_line_deviation_px(curved) > 2.0
    assert straight_line_deviation_px(curved_cam.undistort_px(curved)) < 2.0  # after correction
    # and calibrate() warns about it
    clicks = [ClickedLandmark(n, *px_of(curved_cam, landmarks_xyz_in([n])[0])) for n in NAMES]
    clicks += [ClickedLandmark("edge_floor_ylo", float(u), float(v)) for u, v in curved]
    cal = calibrate(clicks, VideoInfo(width_px=w, height_px=h))
    assert any("edge_floor_ylo" in x and "straight" in x for x in cal.warnings)


def test_robust_loss_survives_a_misclick(capsys) -> None:
    pos, f, w, h = SCENES["wide_audience"]
    cam = look_at(pos, f, w, h, 0.0)
    bad = (5, np.array([25.0, -15.0]))  # a 29 px mis-click on a wall-top corner
    plain = sweep(cam, w, h, "none", True, robust=False, outlier=bad)
    robust = sweep(cam, w, h, "none", True, robust=True, outlier=bad)
    clean = sweep(cam, w, h, "none", True, robust=True)
    with capsys.disabled():
        print("\n[mis-click 29 px on one landmark, wide_audience]")
        print("  " + row("squared loss", plain))
        print("  " + row("Cauchy loss ", robust))
        print("  " + row("no mis-click", clean))
    assert robust["air"][0] < 0.6 * plain["air"][0]
    assert robust["floor"][0] < plain["floor"][0]


def test_robust_loss_survives_a_bad_edge_click() -> None:
    pos, f, w, h = SCENES["wide_audience"]
    cam = look_at(pos, f, w, h, 0.0)
    rng = np.random.default_rng(1)
    world = landmarks_xyz_in(NAMES)
    px = cam.project(world) + rng.normal(0, 1.0, (len(world), 2))
    ln = edge_obs(cam, rng, 1.0)
    ln.pixels_px[3] += [0.0, 30.0]
    fit = fit_camera(world, px, w, h, lines=ln, distortion="none")
    assert fit.line_loo_residuals_px[3] > 3.0
    assert fit.line_residuals_px[3] == fit.line_residuals_px.max()
    assert fit.camera is not None
    assert fit.camera.f_px == pytest.approx(cam.f_px, rel=0.03)


def test_k1_warnings() -> None:
    pos, f, w, h = SCENES["telephoto"]
    cam = look_at(pos, f, w, h, 0.0)
    floor = NAMES[:4]
    px = cam.project(landmarks_xyz_in(floor))
    fit = fit_camera(landmarks_xyz_in(floor), px, w, h)
    assert any("distortion not estimated" in x for x in fit.warnings)
    assert fit.camera is not None and fit.camera.k1 == 0.0
    # off-floor points only, narrow view: k1 barely constrained -> warned, held near zero
    fit2 = fit_camera(landmarks_xyz_in(NAMES), cam.project(landmarks_xyz_in(NAMES)), w, h)
    assert any("k1 poorly constrained" in x for x in fit2.warnings)
    # straight edges identify it on a wide camera: no warning
    wcam = look_at(*SCENES["wide_corner"][:2], w, h, -0.15)
    rng = np.random.default_rng(2)
    wpx = wcam.project(landmarks_xyz_in(NAMES)) + rng.normal(0, 1.0, (len(NAMES), 2))
    fit3 = fit_camera(landmarks_xyz_in(NAMES), wpx, w, h, lines=edge_obs(wcam, rng, 1.0))
    assert not any("k1 poorly" in x for x in fit3.warnings)
    assert fit3.k1_sigma < 0.05


def test_pooled_repeat_clicks_average_down(capsys) -> None:
    pos, f, w, h = SCENES["wide_audience"]
    cam = look_at(pos, f, w, h, 0.0)
    world = landmarks_xyz_in(NAMES)
    single, pooled = [], []
    for seed in range(10):
        rng = np.random.default_rng(seed)
        for n_frames, out in ((1, single), (4, pooled)):
            wl = np.tile(world, (n_frames, 1))
            px = cam.project(wl) + rng.normal(0, 1.5, (len(wl), 2))
            c = fit_camera(wl, px, w, h, distortion="none", compute_loo=False).camera
            assert c is not None
            err = [np.linalg.norm(c.point_on_plane_z(*px_of(cam, p), 49.0) - p) for p in AIR[:3]]
            out.append(np.sqrt(np.mean(np.square(err))))
    with capsys.disabled():
        print(
            "\n[pooling 4 frames of clicks, 1.5 px noise] airborne error "
            f"{np.mean(single):.2f} in (1 frame) -> {np.mean(pooled):.2f} in (4 frames)"
        )
    assert np.mean(pooled) < 0.7 * np.mean(single)


def test_repeat_click_noise_estimate() -> None:
    rng = np.random.default_rng(3)
    clicks = []
    for n in NAMES:
        for frame in range(5):
            u, v = 500 + rng.normal(0, 1.2), 400 + rng.normal(0, 1.2)
            clicks.append(ClickedLandmark(n, u, v, frame))
    assert repeat_click_noise_px(clicks) == pytest.approx(1.2, rel=0.2)
    assert repeat_click_noise_px(clicks[::5]) is None  # every landmark clicked once


def test_calibration_json_with_distortion_and_edges(tmp_path) -> None:
    pos, f, w, h = SCENES["wide_corner"]
    cam = look_at(pos, f, w, h, -0.15)
    rng = np.random.default_rng(4)
    world = landmarks_xyz_in(NAMES)
    px = cam.project(world) + rng.normal(0, 1.0, (len(NAMES), 2))
    pairs = zip(NAMES, px, strict=True)
    clicks = [ClickedLandmark(n, float(u), float(v), 7) for n, (u, v) in pairs]
    ln = edge_obs(cam, rng, 1.0)
    names = [n for n, e in edge_table().items() for _ in range(6)]
    edge_pairs = zip(names, ln.pixels_px, strict=True)
    clicks += [ClickedLandmark(n, float(u), float(v), 7) for n, (u, v) in edge_pairs]
    cal = calibrate(clicks, VideoInfo(width_px=w, height_px=h), camera_setup_id="EVT-wide")
    assert cal.camera is not None and cal.camera.k1 < -0.05
    assert cal.k1_sigma is not None
    assert set(edge_table()) <= set(cal.landmark_ids)
    path = tmp_path / "cal.json"
    write_calibration(cal, path)
    back = read_calibration(path)
    assert isinstance(back, Calibration) and back.camera is not None
    assert back.camera.k1 == pytest.approx(cal.camera.k1) and back.k1_sigma == cal.k1_sigma
    edge_records = [c for c in back.landmarks if c.name.startswith("edge_")]
    assert len(edge_records) == 48 and all(c.residual_px is not None for c in edge_records)


def test_snap_corner_improves_a_click() -> None:
    cv2 = pytest.importorskip("cv2")
    from alea.video.subpixel import snap_corner

    img = np.zeros((120, 160), np.uint8)
    img[:60, :80] = 255  # bright quadrant: its corner is the saddle at (80, 60)
    img[60:, 80:] = 255
    img = cv2.GaussianBlur(img, (0, 0), 1.2)
    u, v = snap_corner(img, 82.0, 58.0)
    assert np.hypot(u - 79.5, v - 59.5) < 0.6  # pixel centres: edge between pixels 79 and 80
    assert snap_corner(img, 82.0, 58.0, max_shift_px=0.1) == (82.0, 58.0)
    assert snap_corner(img, 2.0, 2.0) == (2.0, 2.0)  # too close to the border
