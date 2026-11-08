"""Calibration record: clicked landmarks, fitted camera, residuals, JSON I/O (phase 2, stage 2.1).

The JSON keeps the raw clicks so a better fit never needs re-clicking. Schema in
`.claude/` phase 2 plan section 3.2; `schema_version` is checked on read.
"""

import json
import math
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from alea.video.geometry import (
    DISTORTION_AUTO,
    STRAIGHT_WARN_PX,
    Camera,
    GeometryError,
    LineObs,
    fit_camera,
    floor_ellipse,
    floor_point_from_homography,
    straight_line_deviation_px,
)
from alea.video.landmarks import get_edge, get_landmark, is_custom_id, is_edge_id, landmarks_xyz_in

# Version 1 files (no distortion, no edge clicks) stay readable: the new fields are optional.
SCHEMA_VERSION = 1


def repeat_click_noise_px(clicks: "list[ClickedLandmark]") -> float | None:
    """Per-click noise (px, per axis) from landmarks clicked more than once.

    Clicks of one static landmark in several frames are independent observations of the same
    point: the fit already treats them as such (the weighted mean has sigma/sqrt(n)), and their
    scatter about the group mean gives the pooled estimate sqrt(sum d^2 / (N - groups) / 2).
    Returns None when no landmark was clicked twice.
    """
    groups: dict[str, list[tuple[float, float]]] = {}
    for c in clicks:
        groups.setdefault(c.name, []).append((c.u_px, c.v_px))
    ss, dof = 0.0, 0
    for pts in groups.values():
        if len(pts) < 2:
            continue
        a = np.array(pts)
        ss += float(((a - a.mean(axis=0)) ** 2).sum())
        dof += 2 * (len(pts) - 1)
    return math.sqrt(ss / dof) if dof else None


@dataclass(frozen=True)
class ClickedLandmark:
    """One click on a named landmark. The camera is static within a video, so clicks from
    several frames (`frame`) pool into one fit, and a landmark may appear more than once."""

    name: str
    u_px: float
    v_px: float
    frame: int | None = None
    residual_px: float | None = None  # filled by `calibrate`
    loo_residual_px: float | None = None
    floor_major_in: float | None = None  # 1-sigma floor ellipse (floor landmarks only)
    floor_minor_in: float | None = None
    floor_angle_deg: float | None = None


@dataclass
class VideoInfo:
    file: str = ""
    sha256: str = ""
    width_px: int = 1920
    height_px: int = 1080
    fps_nominal: float = 30.0
    frame_count: int = 0


@dataclass
class Calibration:
    video: VideoInfo
    landmarks: list[ClickedLandmark]
    model: str
    camera: Camera | None
    homography_floor: list[list[float]]
    rms_reprojection_px: float
    max_loo_residual_px: float | None
    max_floor_in: float | None
    k1_sigma: float | None = None  # posterior sigma of the radial distortion k1 (None: not fitted)
    click_noise_px: float | None = None  # per-click noise estimated from repeated clicks
    warnings: list[str] = field(default_factory=list)
    valid_frames: tuple[int, int] = (0, 0)
    camera_setup_id: str = ""  # e.g. event code + camera position; one calibration per setup
    calibration_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    operator: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    @property
    def landmark_ids(self) -> list[str]:
        return sorted({c.name for c in self.landmarks})

    def floor_point_in(self, u_px: float, v_px: float, z_in: float = 0.0) -> tuple[float, float]:
        """Field (x_in, y_in) of a pixel assumed to lie at height z_in."""
        if self.camera is None:
            if z_in != 0.0:
                raise GeometryError("homography-only calibration cannot place elevated points")
            x, y = floor_point_from_homography(np.array(self.homography_floor), u_px, v_px)
            return float(x), float(y)
        p = self.camera.point_on_plane_z(u_px, v_px, z_in)
        return float(p[0]), float(p[1])

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "calibration_id": self.calibration_id,
            "video": {
                "file": self.video.file,
                "sha256": self.video.sha256,
                "width_px": self.video.width_px,
                "height_px": self.video.height_px,
                "fps_nominal": self.video.fps_nominal,
                "frame_count": self.video.frame_count,
            },
            "valid_frames": list(self.valid_frames),
            "camera_setup_id": self.camera_setup_id,
            "landmark_ids": self.landmark_ids,
            "landmarks": [asdict(c) for c in self.landmarks],
            "model": self.model,
            "camera": self.camera.to_dict() if self.camera else None,
            "homography_floor": self.homography_floor,
            "rms_reprojection_px": self.rms_reprojection_px,
            "max_loo_residual_px": self.max_loo_residual_px,
            "max_floor_in": self.max_floor_in,
            "k1_sigma": self.k1_sigma,
            "click_noise_px": self.click_noise_px,
            "warnings": self.warnings,
            "operator": self.operator,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Calibration":
        if d.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported calibration schema_version {d.get('schema_version')!r}; "
                f"expected {SCHEMA_VERSION}"
            )
        v = d["video"]
        return cls(
            video=VideoInfo(
                file=v["file"],
                sha256=v["sha256"],
                width_px=int(v["width_px"]),
                height_px=int(v["height_px"]),
                fps_nominal=float(v["fps_nominal"]),
                frame_count=int(v["frame_count"]),
            ),
            landmarks=[ClickedLandmark(**c) for c in d["landmarks"]],
            camera_setup_id=d.get("camera_setup_id", ""),
            model=d["model"],
            camera=Camera.from_dict(d["camera"]) if d["camera"] else None,
            homography_floor=d["homography_floor"],
            rms_reprojection_px=d["rms_reprojection_px"],
            max_loo_residual_px=d["max_loo_residual_px"],
            max_floor_in=d["max_floor_in"],
            k1_sigma=d.get("k1_sigma"),
            click_noise_px=d.get("click_noise_px"),
            warnings=list(d["warnings"]),
            valid_frames=(int(d["valid_frames"][0]), int(d["valid_frames"][1])),
            calibration_id=d["calibration_id"],
            operator=d.get("operator", ""),
            created_at=d["created_at"],
        )


def _finite_or_none(x: float) -> float | None:
    return float(x) if math.isfinite(x) else None


def calibrate(
    clicks: list[ClickedLandmark],
    video: VideoInfo,
    valid_frames: tuple[int, int] = (0, 0),
    operator: str = "",
    sigma_px: float | None = None,
    camera_setup_id: str = "",
    distortion: str = DISTORTION_AUTO,
) -> Calibration:
    """Fit ONE static camera to clicked landmarks (any visible subset, possibly pooled from
    several frames of the same video) and return the calibration record."""
    custom = [c for c in clicks if is_custom_id(c.name)]
    rest = [c for c in clicks if not is_custom_id(c.name)]
    edge_clicks = [c for c in rest if is_edge_id(c.name)]
    clicks = [c for c in rest if not is_edge_id(c.name)]
    if not clicks:
        raise GeometryError("no landmark clicks")
    world = landmarks_xyz_in([c.name for c in clicks])
    pixels = np.array([[c.u_px, c.v_px] for c in clicks], dtype=np.float64)
    lines = LineObs.empty()
    if edge_clicks:
        edges = [get_edge(c.name) for c in edge_clicks]
        lines = LineObs(
            np.array([e.a.xyz_in for e in edges], dtype=np.float64),
            np.array([e.b.xyz_in for e in edges], dtype=np.float64),
            np.array([[c.u_px, c.v_px] for c in edge_clicks], dtype=np.float64),
        )
    fit = fit_camera(
        world, pixels, video.width_px, video.height_px, lines=lines, distortion=distortion
    )
    straight_warnings: list[str] = []
    for edge_id in sorted({c.name for c in edge_clicks}):
        pts = [(c.u_px, c.v_px) for c in edge_clicks if c.name == edge_id]
        if len(pts) >= 5 and (dev := straight_line_deviation_px(pts)) > STRAIGHT_WARN_PX:
            straight_warnings.append(
                f"clicks on {edge_id} deviate {dev:.1f} px from a straight line "
                "(lens distortion or a mis-click)"
            )
    noise_px = repeat_click_noise_px(clicks)
    if sigma_px is None:
        sigma_px = noise_px if noise_px is not None else 1.0
    out: list[ClickedLandmark] = []
    for c, r, loo in zip(clicks, fit.residuals_px, fit.loo_residuals_px, strict=True):
        extra: dict[str, float | None] = {}
        if fit.camera is not None and get_landmark(c.name).on_floor:
            e = floor_ellipse(fit.camera, c.u_px, c.v_px, sigma_px)
            extra = {
                "floor_major_in": e.major_in,
                "floor_minor_in": e.minor_in,
                "floor_angle_deg": e.angle_deg,
            }
        out.append(replace(c, residual_px=float(r), loo_residual_px=_finite_or_none(loo), **extra))
    edge_fit = zip(edge_clicks, fit.line_residuals_px, fit.line_loo_residuals_px, strict=True)
    for c, r, loo in edge_fit:
        out.append(replace(c, residual_px=float(r), loo_residual_px=_finite_or_none(loo)))
    majors = [c.floor_major_in for c in out if c.floor_major_in is not None]
    return Calibration(
        video=video,
        landmarks=out,
        model=fit.model,
        camera=fit.camera,
        homography_floor=fit.homography.tolist(),
        rms_reprojection_px=fit.rms_px,
        max_loo_residual_px=_finite_or_none(fit.max_loo_px),
        max_floor_in=float(max(majors)) if majors else None,
        k1_sigma=_finite_or_none(fit.k1_sigma),
        click_noise_px=noise_px,
        warnings=[
            *fit.warnings,
            *straight_warnings,
            *(
                [f"ignored custom landmark ids (no coordinates in alea.game): {names}"]
                if (names := sorted({c.name for c in custom}))
                else []
            ),
        ],
        valid_frames=valid_frames,
        camera_setup_id=camera_setup_id,
        operator=operator,
    )


def write_calibration(cal: Calibration, path: Path) -> None:
    path.write_text(json.dumps(cal.to_dict(), indent=2) + "\n", encoding="utf-8")


def read_calibration(path: Path) -> Calibration:
    return Calibration.from_dict(json.loads(path.read_text(encoding="utf-8")))
