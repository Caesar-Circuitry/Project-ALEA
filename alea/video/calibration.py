"""Calibration record: clicked landmarks, fitted camera, residuals, JSON I/O (phase 2, stage 2.1).

The JSON keeps the raw clicks so a better fit never needs re-clicking. Schema in
`.claude/` phase 2 plan section 3.2; `schema_version` is checked on read.
"""

import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from alea.video.geometry import (
    Camera,
    GeometryError,
    fit_camera,
    floor_ellipse,
    floor_point_from_homography,
)
from alea.video.landmarks import get_landmark, landmarks_xyz_in

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ClickedLandmark:
    name: str
    u_px: float
    v_px: float


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
    residuals_px: dict[str, float] = field(default_factory=dict)
    loo_residuals_px: dict[str, float | None] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    valid_frames: tuple[int, int] = (0, 0)
    calibration_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    operator: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))

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
            "landmarks": [
                {"name": c.name, "u_px": c.u_px, "v_px": c.v_px} for c in self.landmarks
            ],
            "model": self.model,
            "camera": self.camera.to_dict() if self.camera else None,
            "homography_floor": self.homography_floor,
            "rms_reprojection_px": self.rms_reprojection_px,
            "max_loo_residual_px": self.max_loo_residual_px,
            "max_floor_in": self.max_floor_in,
            "residuals_px": self.residuals_px,
            "loo_residuals_px": self.loo_residuals_px,
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
            landmarks=[ClickedLandmark(c["name"], c["u_px"], c["v_px"]) for c in d["landmarks"]],
            model=d["model"],
            camera=Camera.from_dict(d["camera"]) if d["camera"] else None,
            homography_floor=d["homography_floor"],
            rms_reprojection_px=d["rms_reprojection_px"],
            max_loo_residual_px=d["max_loo_residual_px"],
            max_floor_in=d["max_floor_in"],
            residuals_px=d.get("residuals_px", {}),
            loo_residuals_px=d.get("loo_residuals_px", {}),
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
    sigma_px: float = 1.0,
) -> Calibration:
    """Fit a camera to clicked landmarks and return the full calibration record."""
    if len({c.name for c in clicks}) != len(clicks):
        raise GeometryError("a landmark was clicked more than once")
    world = landmarks_xyz_in([c.name for c in clicks])
    pixels = np.array([[c.u_px, c.v_px] for c in clicks], dtype=np.float64)
    fit = fit_camera(world, pixels, video.width_px, video.height_px)
    max_floor_in: float | None = None
    if fit.camera is not None:
        majors = [
            floor_ellipse(fit.camera, c.u_px, c.v_px, sigma_px).major_in
            for c in clicks
            if get_landmark(c.name).on_floor
        ]
        max_floor_in = float(max(majors))
    return Calibration(
        video=video,
        landmarks=list(clicks),
        model=fit.model,
        camera=fit.camera,
        homography_floor=fit.homography.tolist(),
        rms_reprojection_px=fit.rms_px,
        max_loo_residual_px=_finite_or_none(fit.max_loo_px),
        max_floor_in=max_floor_in,
        residuals_px={c.name: float(r) for c, r in zip(clicks, fit.residuals_px, strict=True)},
        loo_residuals_px={
            c.name: _finite_or_none(r) for c, r in zip(clicks, fit.loo_residuals_px, strict=True)
        },
        warnings=list(fit.warnings),
        valid_frames=valid_frames,
        operator=operator,
    )


def write_calibration(cal: Calibration, path: Path) -> None:
    path.write_text(json.dumps(cal.to_dict(), indent=2) + "\n", encoding="utf-8")


def read_calibration(path: Path) -> Calibration:
    return Calibration.from_dict(json.loads(path.read_text(encoding="utf-8")))
