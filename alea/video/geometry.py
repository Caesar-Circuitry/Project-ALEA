"""Camera geometry from clicked field landmarks (roadmap phase 2, stage 2.1).

Pipeline: floor homography (normalised DLT) -> pinhole camera (f, R, position) assuming square
pixels and a centred principal point -> Gauss-Newton / Levenberg-Marquardt refinement over all
landmarks, floor and elevated. Numpy only.

Conventions: world = field frame (inches, z up). Camera frame is OpenCV-like: x right, y down,
z forward. `x_cam = R @ (X - C)`, `u = cx + f * x/z`, `v = cy + f * y/z`. Pixel (u_px, v_px) is
measured from the top-left corner; the principal point defaults to (width/2, height/2).
"""

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from alea.game import biobuzz as g

Array = NDArray[np.float64]

LOO_WARN_PX = 3.0
_FLOOR_TOL_IN = 1e-6

MODEL_REFINED = "pinhole_refined"
MODEL_FROM_HOMOGRAPHY = "pinhole_from_homography"
MODEL_HOMOGRAPHY = "homography_floor"


class GeometryError(ValueError):
    """The landmarks cannot define a camera (too few, collinear, behind the camera, ...)."""


# --- small helpers


def rotation_from_vector(w: Array) -> Array:
    """Rodrigues: rotation matrix for rotation vector `w` (radians)."""
    theta = float(np.linalg.norm(w))
    if theta < 1e-12:
        return np.eye(3)
    k = w / theta
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(theta) * kx + (1 - np.cos(theta)) * (kx @ kx)


def _orthonormalise(m: Array) -> Array:
    u, _, vt = np.linalg.svd(m)
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    return r


@dataclass(frozen=True)
class Camera:
    """Pinhole camera with square pixels and zero skew."""

    f_px: float
    rotation: Array  # world -> camera, 3x3
    position_in: Array  # camera centre in the field frame, (3,)
    cx_px: float
    cy_px: float

    def project(self, xyz_in: Array) -> Array:
        """Pixels (N, 2) for world points (N, 3) or (3,). Points behind the camera give nan."""
        pts = np.atleast_2d(np.asarray(xyz_in, dtype=np.float64))
        cam = (pts - self.position_in) @ self.rotation.T
        z = cam[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = self.cx_px + self.f_px * cam[:, 0] / z
            v = self.cy_px + self.f_px * cam[:, 1] / z
        out = np.stack([u, v], axis=1)
        out[z <= 0] = np.nan
        return out

    def ray(self, u_px: float, v_px: float) -> tuple[Array, Array]:
        """(origin, unit direction) in the field frame of the viewing ray through a pixel."""
        d_cam = np.array([(u_px - self.cx_px) / self.f_px, (v_px - self.cy_px) / self.f_px, 1.0])
        d = self.rotation.T @ d_cam
        return self.position_in.copy(), d / np.linalg.norm(d)

    def point_on_plane_z(self, u_px: float, v_px: float, z_in: float) -> Array:
        """World point (3,) where the pixel's ray meets the plane z = z_in."""
        origin, d = self.ray(u_px, v_px)
        if abs(d[2]) < 1e-12:
            raise GeometryError("ray is parallel to the plane")
        s = (z_in - origin[2]) / d[2]
        if s <= 0:
            raise GeometryError("plane is behind the camera along this ray")
        return origin + s * d

    def to_dict(self) -> dict:
        return {
            "f_px": float(self.f_px),
            "rotation": self.rotation.tolist(),
            "position_in": self.position_in.tolist(),
            "principal_point_px": [float(self.cx_px), float(self.cy_px)],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Camera":
        return cls(
            f_px=float(d["f_px"]),
            rotation=np.array(d["rotation"], dtype=np.float64),
            position_in=np.array(d["position_in"], dtype=np.float64),
            cx_px=float(d["principal_point_px"][0]),
            cy_px=float(d["principal_point_px"][1]),
        )


# --- floor homography


def _normalise(pts: Array) -> tuple[Array, Array]:
    c = pts.mean(axis=0)
    d = np.sqrt(((pts - c) ** 2).sum(axis=1)).mean()
    s = np.sqrt(2) / d if d > 0 else 1.0
    t = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1.0]])
    h = np.c_[pts, np.ones(len(pts))] @ t.T
    return h[:, :2], t


def check_not_collinear(xy: Array) -> None:
    """Raise GeometryError if the 2D points lie (nearly) on a line."""
    centred = xy - xy.mean(axis=0)
    sv = np.linalg.svd(centred, compute_uv=False)
    if sv[0] <= 0 or sv[1] / sv[0] < 1e-3:
        raise GeometryError("points are collinear")


def fit_homography(floor_xy_in: Array, pixels_px: Array) -> Array:
    """3x3 H with pixel ~ H @ [x_in, y_in, 1], by normalised DLT (>= 4 points)."""
    xy = np.asarray(floor_xy_in, dtype=np.float64).reshape(-1, 2)
    px = np.asarray(pixels_px, dtype=np.float64).reshape(-1, 2)
    if len(xy) != len(px):
        raise GeometryError("floor points and pixels differ in length")
    if len(xy) < 4:
        raise GeometryError(f"need at least 4 floor points, got {len(xy)}")
    check_not_collinear(xy)
    check_not_collinear(px)
    xn, tw = _normalise(xy)
    pn, tp = _normalise(px)
    rows = []
    for (x, y), (u, v) in zip(xn, pn, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.array(rows))
    hn = vt[-1].reshape(3, 3)
    h = np.linalg.inv(tp) @ hn @ tw
    return h / np.linalg.norm(h)


def apply_homography(h: Array, xy: Array) -> Array:
    p = np.c_[np.atleast_2d(xy), np.ones(len(np.atleast_2d(xy)))] @ h.T
    return p[:, :2] / p[:, 2:3]


def floor_point_from_homography(h: Array, u_px: float, v_px: float) -> Array:
    """Floor (x_in, y_in) for a pixel using only the floor homography."""
    p = np.linalg.inv(h) @ np.array([u_px, v_px, 1.0])
    return p[:2] / p[2]


# --- camera from homography


def camera_from_homography(h: Array, width_px: int, height_px: int) -> Camera:
    """Recover (f, R, position) from a floor homography; square pixels, centred principal point."""
    cx, cy = width_px / 2.0, height_px / 2.0
    hc = np.array([[1, 0, -cx], [0, 1, -cy], [0, 0, 1.0]]) @ h  # columns: (p, q, c)
    h1, h2, h3 = hc[:, 0], hc[:, 1], hc[:, 2]
    estimates = []
    den_a = h1[2] * h2[2]
    if abs(den_a) > 1e-12:
        estimates.append(-(h1[0] * h2[0] + h1[1] * h2[1]) / den_a)
    den_b = h1[2] ** 2 - h2[2] ** 2
    if abs(den_b) > 1e-12:
        estimates.append(((h2[0] ** 2 + h2[1] ** 2) - (h1[0] ** 2 + h1[1] ** 2)) / den_b)
    good = [e for e in estimates if e > 1e-6]
    if not good:
        raise GeometryError("focal length is not recoverable from the floor homography")
    f = float(np.sqrt(np.mean(good)))
    kinv = np.diag([1 / f, 1 / f, 1.0])
    a1, a2, a3 = kinv @ h1, kinv @ h2, kinv @ h3
    lam = 2.0 / (np.linalg.norm(a1) + np.linalg.norm(a2))
    if a3[2] < 0:
        lam = -lam
    r1, r2, t = lam * a1, lam * a2, lam * a3
    rot = _orthonormalise(np.stack([r1, r2, np.cross(r1, r2)], axis=1))
    return Camera(f, rot, -rot.T @ t, cx, cy)


# --- refinement


def _unpack(cam0: Camera, p: Array) -> Camera:
    return Camera(
        float(p[0]),
        rotation_from_vector(p[1:4]) @ cam0.rotation,
        cam0.position_in + p[4:7],
        cam0.cx_px,
        cam0.cy_px,
    )


def _residual(cam0: Camera, p: Array, world: Array, pixels: Array) -> Array:
    proj = _unpack(cam0, p).project(world)
    r = (proj - pixels).ravel()
    return np.where(np.isfinite(r), r, 1e6)


def refine_camera(
    camera: Camera, world_in: Array, pixels_px: Array, max_iter: int = 100
) -> Camera:
    """Levenberg-Marquardt (damped Gauss-Newton) over f, rotation and position."""
    world = np.asarray(world_in, dtype=np.float64).reshape(-1, 3)
    pixels = np.asarray(pixels_px, dtype=np.float64).reshape(-1, 2)
    if len(world) < 4:
        raise GeometryError("need at least 4 landmarks to refine a camera")
    cam = camera
    steps = np.array([1e-3 * cam.f_px, 1e-7, 1e-7, 1e-7, 1e-4, 1e-4, 1e-4])
    lam = 1e-3
    p0 = np.array([cam.f_px, 0, 0, 0, 0, 0, 0], dtype=np.float64)
    r = _residual(cam, p0, world, pixels)
    cost = float(r @ r)
    for _ in range(max_iter):
        p0 = np.array([cam.f_px, 0, 0, 0, 0, 0, 0], dtype=np.float64)
        jac = np.empty((len(r), 7))
        for k in range(7):
            dp = np.zeros(7)
            dp[k] = steps[k]
            jac[:, k] = (
                _residual(cam, p0 + dp, world, pixels) - _residual(cam, p0 - dp, world, pixels)
            ) / (2 * steps[k])
        jtj = jac.T @ jac
        grad = jac.T @ r
        improved = False
        for _ in range(12):
            a = jtj + lam * np.diag(np.maximum(np.diag(jtj), 1e-12))
            try:
                delta = -np.linalg.solve(a, grad)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            trial = p0 + delta
            rt = _residual(cam, trial, world, pixels)
            ct = float(rt @ rt)
            if np.isfinite(ct) and ct < cost and trial[0] > 0:
                cam, r, cost = _unpack(cam, trial), rt, ct
                lam = max(lam / 5, 1e-12)
                improved = True
                break
            lam *= 5
        if not improved or float(np.linalg.norm(delta / (np.abs(p0) + 1))) < 1e-10:
            break
    return Camera(cam.f_px, _orthonormalise(cam.rotation), cam.position_in, cam.cx_px, cam.cy_px)


# --- uncertainty


@dataclass(frozen=True)
class FloorEllipse:
    """1-sigma floor position ellipse for a pixel error (semi-axes in inches)."""

    major_in: float
    minor_in: float
    angle_deg: float  # direction of the major axis from +x


def floor_ellipse(
    camera: Camera, u_px: float, v_px: float, sigma_px: float = 1.0, z_in: float = 0.0
) -> FloorEllipse:
    """Map an isotropic `sigma_px` click error through the back-projection Jacobian."""
    h = 0.5
    cols = []
    for du, dv in ((h, 0.0), (0.0, h)):
        a = camera.point_on_plane_z(u_px + du, v_px + dv, z_in)[:2]
        b = camera.point_on_plane_z(u_px - du, v_px - dv, z_in)[:2]
        cols.append((a - b) / (2 * h))
    jac = np.stack(cols, axis=1)
    cov = sigma_px**2 * jac @ jac.T
    evals, evecs = np.linalg.eigh(cov)
    major = evecs[:, 1]
    return FloorEllipse(
        float(np.sqrt(max(evals[1], 0.0))),
        float(np.sqrt(max(evals[0], 0.0))),
        float(np.degrees(np.arctan2(major[1], major[0])) % 180.0),
    )


# --- full fit


@dataclass
class CameraFit:
    """Result of `fit_camera`."""

    model: str
    camera: Camera | None
    homography: Array
    residuals_px: Array  # (N,) per-point reprojection distance
    loo_residuals_px: Array  # (N,) leave-one-out distance, nan when not computable
    rms_px: float
    warnings: list[str] = field(default_factory=list)

    @property
    def max_loo_px(self) -> float:
        finite = self.loo_residuals_px[np.isfinite(self.loo_residuals_px)]
        return float(finite.max()) if len(finite) else float("nan")


def _predict(fit_cam: Camera | None, h: Array, world: Array) -> Array:
    if fit_cam is not None:
        return fit_cam.project(world)
    return apply_homography(h, world[:, :2])


def _solve(
    world: Array, pixels: Array, width_px: int, height_px: int, floor: Array
) -> tuple[Camera | None, Array]:
    h = fit_homography(world[floor, :2], pixels[floor])
    try:
        cam0 = camera_from_homography(h, width_px, height_px)
        cam = refine_camera(cam0, world, pixels)
    except GeometryError:
        return None, h
    return cam, h


def fit_camera(world_in: Array, pixels_px: Array, width_px: int, height_px: int) -> CameraFit:
    """Fit a camera to clicked landmarks (floor points have z = 0)."""
    world = np.asarray(world_in, dtype=np.float64).reshape(-1, 3)
    pixels = np.asarray(pixels_px, dtype=np.float64).reshape(-1, 2)
    if len(world) != len(pixels):
        raise GeometryError("world points and pixels differ in length")
    floor = np.abs(world[:, 2]) <= _FLOOR_TOL_IN
    n_floor = int(floor.sum())
    if n_floor < 4:
        raise GeometryError(f"need at least 4 floor points, got {n_floor}")
    warnings: list[str] = []
    cam, h = _solve(world, pixels, width_px, height_px, floor)
    fx = world[floor, :2]
    if min(np.ptp(fx[:, 0]), np.ptp(fx[:, 1])) < g.FIELD_SIZE_IN / 3:
        warnings.append("floor points span under a third of the field; depth is poorly determined")
    if cam is None:
        model = MODEL_HOMOGRAPHY
        warnings.append("camera recovery failed; only floor points can be placed")
    elif n_floor == len(world):
        model = MODEL_FROM_HOMOGRAPHY
        warnings.append("no off-floor landmark; focal length is unrefined")
    else:
        model = MODEL_REFINED
    pred = _predict(cam, h, world)
    res = np.linalg.norm(pred - pixels, axis=1)
    loo = np.full(len(world), np.nan)
    for i in range(len(world)):
        keep = np.ones(len(world), bool)
        keep[i] = False
        if int((keep & floor).sum()) < 4:
            continue
        try:
            cam_i, h_i = _solve(world[keep], pixels[keep], width_px, height_px, floor[keep])
        except GeometryError:
            continue
        if (cam is None) != (cam_i is None):
            continue
        p = _predict(cam_i, h_i, world[i : i + 1])
        loo[i] = float(np.linalg.norm(p[0] - pixels[i]))
    big = np.flatnonzero(np.nan_to_num(loo) > LOO_WARN_PX)
    if len(big):
        warnings.append(
            f"leave-one-out residual above {LOO_WARN_PX:g} px at point index "
            + ", ".join(str(int(i)) for i in big)
        )
    rms = float(np.sqrt(np.mean(res**2)))
    return CameraFit(model, cam, h, res, loo, rms, warnings)
