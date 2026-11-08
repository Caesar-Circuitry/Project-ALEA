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
    Camera,
    GeometryError,
    fit_camera,
    floor_ellipse,
    floor_point_from_homography,
)
from alea.video.landmarks import get_landmark, is_custom_id, landmarks_xyz_in

SCHEMA_VERSION = 1


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
    camera_setup_id: str = "",
) -> Calibration:
    """Fit ONE static camera to clicked landmarks (any visible subset, possibly pooled from
    several frames of the same video) and return the calibration record."""
    custom = [c for c in clicks if is_custom_id(c.name)]
    clicks = [c for c in clicks if not is_custom_id(c.name)]
    if not clicks:
        raise GeometryError("no landmark clicks")
    world = landmarks_xyz_in([c.name for c in clicks])
    pixels = np.array([[c.u_px, c.v_px] for c in clicks], dtype=np.float64)
    fit = fit_camera(world, pixels, video.width_px, video.height_px)
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
        warnings=[
            *fit.warnings,
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
