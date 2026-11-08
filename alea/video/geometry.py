"""Camera geometry from clicked field landmarks (roadmap phase 2, stage 2.1).

Pipeline: floor homography (normalised DLT) -> pinhole camera (f, R, position) assuming square
pixels and a centred principal point -> robust Levenberg-Marquardt refinement over all
landmark points (floor and elevated) and straight-edge points, optionally with Brown-Conrady
radial distortion (k1, k2) under a weak Gaussian prior around zero. Numpy only.

Conventions: world = field frame (inches, z up). Camera frame is OpenCV-like: x right, y down,
z forward. `x_cam = R @ (X - C)`, `x = x_cam/z_cam`, `r2 = x^2 + y^2`,
`u = cx + f * x * (1 + k1 r2 + k2 r2^2)` and likewise for v. Pixel (u_px, v_px) is measured
from the top-left corner; the principal point defaults to (width/2, height/2). k1, k2 are in
OpenCV's normalised-coordinate units (not image-size units).

Straight-edge clicks: a point clicked on a straight 3D edge (a wall top, a floor edge) is
undistorted and compared with the projected line through the edge's end points, so straight
edges identify distortion independently of pose.
"""

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import ArrayLike, NDArray

from alea.game import biobuzz as g

Array = NDArray[np.float64]

LOO_WARN_PX = 3.0
_FLOOR_TOL_IN = 1e-6

# Robust loss: Cauchy weights w = 1 / (1 + (r/c)^2), iteratively reweighted.
CAUCHY_PX = 2.5
IRLS_ROUNDS = 6
# Weak priors on distortion, in "click sigma" units (click noise assumed ~1 px): the prior row
# is k / sigma_k, so k1 stays near zero unless the data pull it away.
K1_PRIOR_SIGMA = 0.1
K2_PRIOR_SIGMA = 0.05
K1_POOR_SIGMA = 0.05  # warn when the posterior sigma of k1 exceeds this (prior is 0.1)
K1_LARGE = 0.3

MODEL_REFINED = "pinhole_refined"
MODEL_FROM_HOMOGRAPHY = "pinhole_from_homography"
MODEL_HOMOGRAPHY = "homography_floor"

DISTORTION_AUTO = "auto"  # k1 when off-floor points or edge clicks constrain it
DISTORTION_NONE = "none"
DISTORTION_K1K2 = "k1k2"


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
    """Pinhole camera with square pixels, zero skew and radial distortion k1, k2."""

    f_px: float
    rotation: Array  # world -> camera, 3x3
    position_in: Array  # camera centre in the field frame, (3,)
    cx_px: float
    cy_px: float
    k1: float = 0.0
    k2: float = 0.0

    @property
    def has_distortion(self) -> bool:
        return self.k1 != 0.0 or self.k2 != 0.0

    def distort_px(self, ideal_px: ArrayLike) -> Array:
        """Pinhole (undistorted) pixels -> distorted pixels."""
        p = np.atleast_2d(np.asarray(ideal_px, dtype=np.float64))
        x = (p[:, 0] - self.cx_px) / self.f_px
        y = (p[:, 1] - self.cy_px) / self.f_px
        r2 = x * x + y * y
        d = 1 + self.k1 * r2 + self.k2 * r2 * r2
        return np.stack([self.cx_px + self.f_px * x * d, self.cy_px + self.f_px * y * d], axis=1)

    def undistort_px(self, pixels_px: ArrayLike) -> Array:
        """Distorted pixels -> pinhole pixels (fixed-point inverse, fine for |k| < 0.5)."""
        p = np.atleast_2d(np.asarray(pixels_px, dtype=np.float64))
        if not self.has_distortion:
            return p.copy()
        xd = (p[:, 0] - self.cx_px) / self.f_px
        yd = (p[:, 1] - self.cy_px) / self.f_px
        x, y = xd.copy(), yd.copy()
        for _ in range(30):
            r2 = x * x + y * y
            d = 1 + self.k1 * r2 + self.k2 * r2 * r2
            x, y = xd / d, yd / d
        return np.stack([self.cx_px + self.f_px * x, self.cy_px + self.f_px * y], axis=1)

    def project_ideal(self, xyz_in: ArrayLike) -> Array:
        """Pinhole pixels (N, 2), ignoring distortion. Points behind the camera give nan."""
        pts = np.atleast_2d(np.asarray(xyz_in, dtype=np.float64))
        cam = (pts - self.position_in) @ self.rotation.T
        z = cam[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = self.cx_px + self.f_px * cam[:, 0] / z
            v = self.cy_px + self.f_px * cam[:, 1] / z
        out = np.stack([u, v], axis=1)
        out[z <= 0] = np.nan
        return out

    def project(self, xyz_in: ArrayLike) -> Array:
        """Pixels (N, 2) for world points (N, 3) or (3,), with distortion."""
        ideal = self.project_ideal(xyz_in)
        if not self.has_distortion:
            return ideal
        return self.distort_px(ideal)

    def ray(self, u_px: float, v_px: float) -> tuple[Array, Array]:
        """(origin, unit direction) in the field frame of the viewing ray through a pixel."""
        u, v = self.undistort_px([u_px, v_px])[0]
        d_cam = np.array([(u - self.cx_px) / self.f_px, (v - self.cy_px) / self.f_px, 1.0])
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
            "distortion": {"k1": float(self.k1), "k2": float(self.k2)},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Camera":
        dist = d.get("distortion") or {}
        return cls(
            f_px=float(d["f_px"]),
            rotation=np.array(d["rotation"], dtype=np.float64),
            position_in=np.array(d["position_in"], dtype=np.float64),
            cx_px=float(d["principal_point_px"][0]),
            cy_px=float(d["principal_point_px"][1]),
            k1=float(dist.get("k1", 0.0)),
            k2=float(dist.get("k2", 0.0)),
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


# --- observations and residuals


@dataclass(frozen=True)
class LineObs:
    """Clicked pixels, each on the straight 3D edge from p0_in[i] to p1_in[i]."""

    p0_in: Array  # (K, 3)
    p1_in: Array  # (K, 3)
    pixels_px: Array  # (K, 2)

    def __len__(self) -> int:
        return len(self.pixels_px)

    def without(self, i: int) -> "LineObs":
        keep = np.arange(len(self)) != i
        return LineObs(self.p0_in[keep], self.p1_in[keep], self.pixels_px[keep])

    @classmethod
    def empty(cls) -> "LineObs":
        return cls(np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((0, 2)))


def line_residuals_px(cam: Camera, lines: LineObs) -> Array:
    """Signed perpendicular distance (px) of undistorted clicks from the projected edges."""
    if len(lines) == 0:
        return np.zeros(0)
    a0 = cam.project_ideal(lines.p0_in)
    a1 = cam.project_ideal(lines.p1_in)
    q = cam.undistort_px(lines.pixels_px)
    d = a1 - a0
    n = np.hypot(d[:, 0], d[:, 1])
    with np.errstate(divide="ignore", invalid="ignore"):
        dist = (d[:, 0] * (q[:, 1] - a0[:, 1]) - d[:, 1] * (q[:, 0] - a0[:, 0])) / n
    return np.where(np.isfinite(dist), dist, 1e6)


def point_residuals_px(cam: Camera, world: Array, pixels: Array) -> Array:
    """(N, 2) reprojection residuals (projected minus clicked)."""
    r = cam.project(world) - pixels
    return np.where(np.isfinite(r), r, 1e6)


# --- robust refinement

_STEPS = np.array([0.0, 1e-7, 1e-7, 1e-7, 1e-4, 1e-4, 1e-4, 1e-5, 1e-5])


def _pack(cam: Camera) -> Array:
    return np.array([cam.f_px, 0, 0, 0, 0, 0, 0, cam.k1, cam.k2], dtype=np.float64)


def _unpack(cam0: Camera, p: Array) -> Camera:
    return Camera(
        float(p[0]),
        rotation_from_vector(p[1:4]) @ cam0.rotation,
        cam0.position_in + p[4:7],
        cam0.cx_px,
        cam0.cy_px,
        float(p[7]),
        float(p[8]),
    )


def _residual_vec(
    cam: Camera, world: Array, pixels: Array, lines: LineObs, free_k: tuple[bool, bool]
) -> Array:
    parts = [point_residuals_px(cam, world, pixels).ravel(), line_residuals_px(cam, lines)]
    if free_k[0]:
        parts.append(np.array([cam.k1 / K1_PRIOR_SIGMA]))
    if free_k[1]:
        parts.append(np.array([cam.k2 / K2_PRIOR_SIGMA]))
    return np.concatenate(parts)


def _weights(r: Array, n_pts: int, n_lines: int) -> Array:
    """Square-root Cauchy weights for each residual row (priors keep weight 1)."""
    sw = np.ones(len(r))
    pts = r[: 2 * n_pts].reshape(-1, 2)
    dist = np.hypot(pts[:, 0], pts[:, 1])
    sw[: 2 * n_pts] = np.repeat(np.sqrt(1 / (1 + (dist / CAUCHY_PX) ** 2)), 2)
    ln = np.abs(r[2 * n_pts : 2 * n_pts + n_lines])
    sw[2 * n_pts : 2 * n_pts + n_lines] = np.sqrt(1 / (1 + (ln / CAUCHY_PX) ** 2))
    return sw


def _lm(
    cam: Camera,
    world: Array,
    pixels: Array,
    lines: LineObs,
    free_k: tuple[bool, bool],
    sw: Array,
    max_iter: int,
) -> tuple[Camera, Array]:
    """Damped Gauss-Newton with fixed row weights `sw`; returns camera and weighted Jacobian."""
    free = [0, 1, 2, 3, 4, 5, 6] + ([7] if free_k[0] else []) + ([8] if free_k[1] else [])
    steps = _STEPS.copy()
    steps[0] = 1e-3 * cam.f_px
    lam = 1e-3
    r = sw * _residual_vec(cam, world, pixels, lines, free_k)
    cost = float(r @ r)
    jac = np.zeros((len(r), len(free)))
    for _ in range(max_iter):
        p0 = _pack(cam)
        jac = np.empty((len(r), len(free)))
        for col, k in enumerate(free):
            dp = np.zeros(9)
            dp[k] = steps[k]
            rp = sw * _residual_vec(_unpack(cam, p0 + dp), world, pixels, lines, free_k)
            rm = sw * _residual_vec(_unpack(cam, p0 - dp), world, pixels, lines, free_k)
            jac[:, col] = (rp - rm) / (2 * steps[k])
        jtj = jac.T @ jac
        grad = jac.T @ r
        improved = False
        delta = np.zeros(len(free))
        for _ in range(12):
            a = jtj + lam * np.diag(np.maximum(np.diag(jtj), 1e-12))
            try:
                delta = -np.linalg.solve(a, grad)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            trial = p0.copy()
            trial[free] += delta
            cand = _unpack(cam, trial)
            rt = sw * _residual_vec(cand, world, pixels, lines, free_k)
            ct = float(rt @ rt)
            if np.isfinite(ct) and ct < cost and trial[0] > 0:
                cam, r, cost = cand, rt, ct
                lam = max(lam / 5, 1e-12)
                improved = True
                break
            lam *= 5
        if not improved or float(np.linalg.norm(delta / (np.abs(p0[free]) + 1))) < 1e-10:
            break
    return cam, jac


def _refine(
    camera: Camera,
    world: Array,
    pixels: Array,
    lines: LineObs,
    fit_k1: bool,
    fit_k2: bool,
    robust: bool,
    rounds: int,
    max_iter: int = 60,
) -> tuple[Camera, Array]:
    """Robust (IRLS) refinement. Returns the camera and the sigma of each free parameter."""
    free_k = (fit_k1 or fit_k2, fit_k2)
    n_pts, n_lines = len(world), len(lines)
    n_prior = int(free_k[0]) + int(free_k[1])
    if not free_k[0]:
        camera = Camera(camera.f_px, camera.rotation, camera.position_in, camera.cx_px,
                        camera.cy_px, 0.0, 0.0)  # fmt: skip
    elif not free_k[1]:
        camera = Camera(camera.f_px, camera.rotation, camera.position_in, camera.cx_px,
                        camera.cy_px, camera.k1, 0.0)  # fmt: skip
    cam = camera
    sw = np.ones(2 * n_pts + n_lines + n_prior)
    jac = np.zeros((0, 0))
    for _ in range(rounds if robust else 1):
        cam, jac = _lm(cam, world, pixels, lines, free_k, sw, max_iter)
        if not robust:
            break
        r = _residual_vec(cam, world, pixels, lines, free_k)
        sw = _weights(r, n_pts, n_lines)
    # parameter sigmas from the weighted normal equations, scaled by the residual scale
    r = sw * _residual_vec(cam, world, pixels, lines, free_k)
    dof = max(len(r) - jac.shape[1], 1)
    scale = max(1.0, float(r @ r) / dof)
    try:
        cov = np.linalg.inv(jac.T @ jac) * scale
        sig = np.sqrt(np.maximum(np.diag(cov), 0.0))
    except np.linalg.LinAlgError:
        sig = np.full(jac.shape[1], np.nan)
    return (
        Camera(cam.f_px, _orthonormalise(cam.rotation), cam.position_in, cam.cx_px, cam.cy_px,
               cam.k1, cam.k2),
        sig,
    )  # fmt: skip


def refine_camera(
    camera: Camera,
    world_in: Array,
    pixels_px: Array,
    max_iter: int = 100,
    *,
    lines: LineObs | None = None,
    fit_k1: bool = False,
    fit_k2: bool = False,
    robust: bool = False,
) -> Camera:
    """Refine f, rotation, position (and k1, k2 if asked) on points and optional edge clicks."""
    world = np.asarray(world_in, dtype=np.float64).reshape(-1, 3)
    pixels = np.asarray(pixels_px, dtype=np.float64).reshape(-1, 2)
    ln = lines or LineObs.empty()
    if len(world) + len(ln) // 2 < 4:
        raise GeometryError("need at least 4 landmarks to refine a camera")
    cam, _ = _refine(camera, world, pixels, ln, fit_k1, fit_k2, robust, IRLS_ROUNDS, max_iter)
    return cam


# --- straight-edge distortion check (plan section 4.5)

STRAIGHT_WARN_PX = 2.0


def straight_line_deviation_px(pixels_px: ArrayLike) -> float:
    """Largest perpendicular distance (px) of points from their total-least-squares line.

    Clicks along one straight edge should be collinear; a deviation above STRAIGHT_WARN_PX
    points at lens distortion (or a mis-click). Needs at least 3 points.
    """
    p = np.asarray(pixels_px, dtype=np.float64).reshape(-1, 2)
    if len(p) < 3:
        raise GeometryError("need at least 3 points to test straightness")
    c = p - p.mean(axis=0)
    _, _, vt = np.linalg.svd(c)
    return float(np.abs(c @ vt[1]).max())


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
    line_residuals_px: Array = field(default_factory=lambda: np.zeros(0))  # (K,) |distance|
    line_loo_residuals_px: Array = field(default_factory=lambda: np.zeros(0))
    k1_sigma: float = float("nan")  # posterior sigma of k1 (nan when k1 was not fitted)
    k2_sigma: float = float("nan")

    @property
    def max_loo_px(self) -> float:
        both = np.concatenate([self.loo_residuals_px, self.line_loo_residuals_px])
        finite = both[np.isfinite(both)]
        return float(finite.max()) if len(finite) else float("nan")


def _homography_predict(h: Array, world: Array) -> Array:
    return apply_homography(h, world[:, :2])


def fit_camera(
    world_in: Array,
    pixels_px: Array,
    width_px: int,
    height_px: int,
    *,
    lines: LineObs | None = None,
    distortion: str = DISTORTION_AUTO,
    robust: bool = True,
    compute_loo: bool = True,
) -> CameraFit:
    """Fit a camera to clicked landmarks (floor points have z = 0) and optional edge clicks.

    `distortion`: "auto" fits k1 when off-floor points or edge clicks constrain it, "none"
    never fits it, "k1k2" also fits k2 (same condition). `robust` uses a Cauchy loss.
    """
    world = np.asarray(world_in, dtype=np.float64).reshape(-1, 3)
    pixels = np.asarray(pixels_px, dtype=np.float64).reshape(-1, 2)
    ln = lines or LineObs.empty()
    if len(world) != len(pixels):
        raise GeometryError("world points and pixels differ in length")
    if distortion not in (DISTORTION_AUTO, DISTORTION_NONE, DISTORTION_K1K2):
        raise GeometryError(f"unknown distortion mode {distortion!r}")
    floor = np.abs(world[:, 2]) <= _FLOOR_TOL_IN
    n_floor = int(floor.sum())
    if n_floor < 4:
        raise GeometryError(f"need at least 4 floor points, got {n_floor}")
    warnings: list[str] = []
    h = fit_homography(world[floor, :2], pixels[floor])
    fx = world[floor, :2]
    if min(np.ptp(fx[:, 0]), np.ptp(fx[:, 1])) < g.FIELD_SIZE_IN / 3:
        warnings.append("floor points span under a third of the field; depth is poorly determined")
    try:
        cam0: Camera | None = camera_from_homography(h, width_px, height_px)
    except GeometryError:
        cam0 = None
    if cam0 is None:
        warnings.append("camera recovery failed; only floor points can be placed")
        if len(ln):
            warnings.append("edge clicks ignored (no camera)")
        pred = _homography_predict(h, world)
        res = np.linalg.norm(pred - pixels, axis=1)
        nan = np.full(len(world), np.nan)
        rms = float(np.sqrt(np.mean(res**2)))
        return CameraFit(MODEL_HOMOGRAPHY, None, h, res, nan, rms, warnings)

    elevated = bool((~floor).any()) or (
        len(ln) > 0 and bool((np.abs(ln.p0_in[:, 2]) > _FLOOR_TOL_IN).any())
    )
    constrained = bool(elevated or len(ln))
    fit_k1 = distortion != DISTORTION_NONE and constrained
    fit_k2 = distortion == DISTORTION_K1K2 and constrained
    if distortion != DISTORTION_NONE and not constrained:
        warnings.append(
            "only floor points and no straight edges: lens distortion not estimated (k1 = 0)"
        )
    if not elevated:
        warnings.append("no off-floor landmark; focal length is unrefined")
    model = MODEL_REFINED if elevated else MODEL_FROM_HOMOGRAPHY

    cam, sig = _refine(cam0, world, pixels, ln, fit_k1, fit_k2, robust, IRLS_ROUNDS)
    k1_sigma = float(sig[7]) if fit_k1 and len(sig) > 7 else float("nan")
    k2_sigma = float(sig[8]) if fit_k2 and len(sig) > 8 else float("nan")
    if fit_k1 and (not np.isfinite(k1_sigma) or k1_sigma > K1_POOR_SIGMA):
        warnings.append(
            f"k1 poorly constrained (sigma {k1_sigma:.3f}); mostly the zero prior; "
            "click points along straight edges or off-floor landmarks to pin it"
        )
    if fit_k1 and abs(cam.k1) > K1_LARGE:
        warnings.append(f"large k1 = {cam.k1:.3f}; check clicks or lens model")

    res = np.linalg.norm(point_residuals_px(cam, world, pixels), axis=1)
    lres = np.abs(line_residuals_px(cam, ln))
    # leave-one-out: refit without one observation, warm-started from the full solution
    loo = np.full(len(world), np.nan)
    lloo = np.full(len(ln), np.nan)
    n_eq = 2 * len(world) + len(ln) if compute_loo else 0
    for i in range(len(world)):
        if n_eq - 2 < 10:
            break
        keep = np.arange(len(world)) != i
        cam_i, _ = _refine(cam, world[keep], pixels[keep], ln, fit_k1, fit_k2, robust, 1, 20)
        one_r = point_residuals_px(cam_i, world[i : i + 1], pixels[i : i + 1])
        loo[i] = float(np.linalg.norm(one_r))
    for j in range(len(ln)):
        if n_eq - 1 < 10:
            break
        cam_j, _ = _refine(cam, world, pixels, ln.without(j), fit_k1, fit_k2, robust, 1, 20)
        one = LineObs(ln.p0_in[j : j + 1], ln.p1_in[j : j + 1], ln.pixels_px[j : j + 1])
        lloo[j] = float(abs(line_residuals_px(cam_j, one)[0]))
    big = np.flatnonzero(np.nan_to_num(loo) > LOO_WARN_PX)
    if len(big):
        warnings.append(
            f"leave-one-out residual above {LOO_WARN_PX:g} px at point index "
            + ", ".join(str(int(i)) for i in big)
        )
    bigl = np.flatnonzero(np.nan_to_num(lloo) > LOO_WARN_PX)
    if len(bigl):
        warnings.append(
            f"leave-one-out residual above {LOO_WARN_PX:g} px at edge click index "
            + ", ".join(str(int(i)) for i in bigl)
        )
    all_res = np.concatenate([res, lres])
    rms = float(np.sqrt(np.mean(all_res**2)))
    return CameraFit(model, cam, h, res, loo, rms, warnings, lres, lloo, k1_sigma, k2_sigma)
