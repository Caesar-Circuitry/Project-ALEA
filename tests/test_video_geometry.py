"""Camera fit on a synthetic pinhole camera (roadmap phase 2, stage 2.1)."""

import numpy as np
import pytest

from alea.game import biobuzz as g
from alea.video.geometry import (
    Camera,
    GeometryError,
    camera_from_homography,
    fit_camera,
    fit_homography,
    floor_ellipse,
)
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


CAMERAS = {
    "audience": look_at([70, -400, 120], CENTRE),
    "corner": look_at([-250, -250, 140], CENTRE),
    "high_end": look_at([70, -300, 250], CENTRE),
}


def clicks(cam: Camera, names, sigma_px, seed) -> np.ndarray:
    rng = np.random.default_rng(seed)
    px = cam.project(landmarks_xyz_in(names))
    return px + rng.normal(0, sigma_px, px.shape)


def test_noise_free_recovers_camera_exactly() -> None:
    cam = CAMERAS["audience"]
    fit = fit_camera(landmarks_xyz_in(NAMES), clicks(cam, NAMES, 0, 0), W, H)
    assert fit.model == "pinhole_refined" and fit.camera is not None
    assert fit.rms_px < 1e-6
    assert fit.camera.f_px == pytest.approx(F, rel=1e-6)
    assert np.allclose(fit.camera.position_in, cam.position_in, atol=1e-3)
    assert not [w for w in fit.warnings if "k1" not in w]
    assert abs(fit.camera.k1) < 0.01  # prior keeps an unconstrained k1 near zero


@pytest.mark.parametrize("name", list(CAMERAS))
def test_synthetic_targets_one_pixel_noise(name: str) -> None:
    cam = CAMERAS[name]
    world = landmarks_xyz_in(NAMES)
    grid = np.array([[x, y, 0.0] for x in np.linspace(10, 131, 5) for y in np.linspace(10, 131, 5)])
    elev = np.array([[40.0, 60.0, 49.0], [100.0, 80.0, 49.0], [70, 30, 49.0]])
    rms, f_err, floor_rms, elev_rms, floor_max, elev_max = [], [], [], [], [], []
    for seed in range(30):
        px = clicks(cam, NAMES, 1.0, seed)
        fit = fit_camera(world, px, W, H, compute_loo=False)
        assert fit.camera is not None
        rms.append(fit.rms_px)
        f_err.append(abs(fit.camera.f_px / F - 1))
        fl, el = [], []
        for p in grid:  # exact pixel of a true point -> recovered position
            u, v = cam.project(p)[0]
            fl.append(np.linalg.norm(fit.camera.point_on_plane_z(u, v, 0.0)[:2] - p[:2]))
        for p in elev:
            u, v = cam.project(p)[0]
            el.append(np.linalg.norm(fit.camera.point_on_plane_z(u, v, 49.0) - p))
        floor_rms.append(np.sqrt(np.mean(np.square(fl))))
        elev_rms.append(np.sqrt(np.mean(np.square(el))))
        floor_max.append(max(fl))
        elev_max.append(max(el))
    print(
        f"{name}: rms_px mean {np.mean(rms):.2f} max {np.max(rms):.2f}; f err mean "
        f"{np.mean(f_err):.2%} max {np.max(f_err):.2%}; floor err rms {np.mean(floor_rms):.2f} "
        f"worst {np.max(floor_max):.2f} in; z=49 err rms {np.mean(elev_rms):.2f} "
        f"worst {np.max(elev_max):.2f} in"
    )
    # Plan targets hold for the typical trial (mean over seeds); the worst of 30 noise draws
    # (grid corner or one bad draw) gets a looser bound.
    assert np.mean(rms) <= 1.5 and np.max(rms) <= 2.0
    assert np.mean(f_err) <= 0.03 and np.max(f_err) <= 0.08
    assert np.mean(floor_rms) <= 2.0 and np.max(floor_max) <= 4.0
    assert np.mean(elev_rms) <= 2.0 and np.max(elev_max) <= 4.0


def test_noise_two_pixels_still_sane() -> None:
    cam = CAMERAS["audience"]
    world = landmarks_xyz_in(NAMES)
    errs = []
    for seed in range(20):
        fit = fit_camera(world, clicks(cam, NAMES, 2.0, seed), W, H, compute_loo=False)
        assert fit.camera is not None
        u, v = cam.project([70, 70, 0.0])[0]
        errs.append(np.linalg.norm(fit.camera.point_on_plane_z(u, v, 0.0)[:2] - [70, 70]))
    assert max(errs) < 4.0


def test_floor_only_is_flagged_unrefined() -> None:
    cam = CAMERAS["audience"]
    names = [*NAMES[:4], "hive_frame_corner_xlo_ylo_zlo", "hive_frame_corner_xhi_yhi_zlo"]
    fit = fit_camera(landmarks_xyz_in(names), clicks(cam, names, 0.0, 0), W, H)
    assert fit.model == "pinhole_from_homography"
    assert any("unrefined" in w for w in fit.warnings)
    assert fit.camera is not None and fit.camera.f_px == pytest.approx(F, rel=1e-4)


def test_homography_and_camera_from_homography() -> None:
    cam = CAMERAS["corner"]
    xyz = landmarks_xyz_in(NAMES[:4])
    hmat = fit_homography(xyz[:, :2], cam.project(xyz))
    rec = camera_from_homography(hmat, W, H)
    assert rec.f_px == pytest.approx(F, rel=1e-6)
    assert np.allclose(rec.position_in, cam.position_in, atol=1e-3)


def test_leave_one_out_flags_misclick() -> None:
    cam = CAMERAS["audience"]
    px = clicks(cam, NAMES, 0.5, 3)
    px[5] += [10.0, 0.0]  # 10 px mis-click on wall_top_x141_y0
    fit = fit_camera(landmarks_xyz_in(NAMES), px, W, H)
    assert fit.loo_residuals_px[5] > 3.0
    assert fit.loo_residuals_px[5] == np.nanmax(fit.loo_residuals_px)
    assert any("leave-one-out" in w for w in fit.warnings)


def test_error_cases() -> None:
    cam = CAMERAS["audience"]
    three = NAMES[:3]
    with pytest.raises(GeometryError, match="at least 4"):
        fit_camera(landmarks_xyz_in(three), clicks(cam, three, 0, 0), W, H)
    xy = np.array([[0, 0], [30, 0], [60, 0], [141, 0]], float)
    with pytest.raises(GeometryError, match="collinear"):
        fit_homography(xy, np.array([[0, 0], [10, 1], [20, 2], [50, 5]], float))
    with pytest.raises(GeometryError, match="differ in length"):
        fit_homography(xy, xy[:3])
    with pytest.raises(GeometryError, match="at least 4"):  # elevated points only
        fit_camera(landmarks_xyz_in(NAMES[4:]), clicks(cam, NAMES[4:], 0, 0), W, H)


def test_ray_and_plane() -> None:
    cam = CAMERAS["audience"]
    p = np.array([60.0, 90.0, 49.13])
    u, v = cam.project(p)[0]
    assert np.allclose(cam.point_on_plane_z(u, v, 49.13), p, atol=1e-6)
    with pytest.raises(GeometryError):
        cam.point_on_plane_z(u, v, 1e6)  # plane behind the camera


def test_project_matches_opencv() -> None:
    cv2 = pytest.importorskip("cv2")
    cam = CAMERAS["corner"]
    world = landmarks_xyz_in(NAMES)
    rvec, _ = cv2.Rodrigues(cam.rotation)
    k = np.array([[F, 0, W / 2], [0, F, H / 2], [0, 0, 1.0]])
    tvec = -cam.rotation @ cam.position_in
    ref, _ = cv2.projectPoints(world, rvec, tvec, k, None)
    assert np.allclose(ref.reshape(-1, 2), cam.project(world), atol=1e-6)


def test_floor_ellipse_depth_worse_than_lateral() -> None:
    cam = CAMERAS["audience"]
    u, v = cam.project([70, 70, 0.0])[0]
    e = floor_ellipse(cam, u, v, 1.0)
    assert e.major_in > 2 * e.minor_in
    assert 0.1 < e.minor_in < 1.0
    assert abs(e.angle_deg - 90) < 10  # depth axis is along +y for this camera
