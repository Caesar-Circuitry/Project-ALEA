"""Overlay profile: where the widgets sit in the frame, per match phase, plus glyph templates.

All ROIs are FRACTIONS of the frame (``x0 < x1``, ``y0 < y1``, in 0..1), so the same profile
works at 720p and 1080p. The overlay swaps widgets between phases (an AUTO robot icon becomes a
TELEOP gamepad icon and shifts neighbours), so a profile has a base layout plus optional
per-phase overrides keyed ``auto``, ``teleop``, ``endgame``, ``post``.

A profile holds no footage: the banner anchor template is a small grayscale crop that the
operator makes locally, and the glyph templates are 12x20 shapes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA_VERSION = 1

ROI_NAMES = (
    "banner_anchor",
    "clock",
    "label",
    "red_score",
    "blue_score",
    "red_tips",
    "blue_tips",
    "red_lock",
    "blue_lock",
    "red_teams",
    "blue_teams",
)
PHASE_KEYS = ("auto", "teleop", "endgame", "post")


class ProfileError(ValueError):
    """The profile file is malformed or inconsistent."""


def layout_phase_key(phase: str) -> str:
    """Layout key for a match phase: the transition shows the TELEOP widgets (assumed)."""
    if phase == "transition":
        return "teleop"
    return phase if phase in PHASE_KEYS else "auto"


@dataclass(frozen=True)
class Roi:
    """A rectangle in frame fractions."""

    x0: float
    y0: float
    x1: float
    y1: float

    def validate(self, name: str = "roi") -> None:
        vals = (self.x0, self.y0, self.x1, self.y1)
        if not all(0.0 <= v <= 1.0 for v in vals) or self.x0 >= self.x1 or self.y0 >= self.y1:
            raise ProfileError(f"{name}: need 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1, got {vals}")

    def to_dict(self) -> dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Roi:
        try:
            return cls(float(d["x0"]), float(d["y0"]), float(d["x1"]), float(d["y1"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProfileError(f"bad ROI {d!r}") from exc

    @classmethod
    def from_pixels(cls, x0: int, y0: int, x1: int, y1: int, width: int, height: int) -> Roi:
        return cls(x0 / width, y0 / height, x1 / width, y1 / height)


@dataclass
class AnchorTemplate:
    """A small grayscale crop of a static banner element (logo) used to locate the overlay."""

    template: np.ndarray  # uint8, 2-D
    ref_frame_size_px: tuple[int, int]  # (width, height) of the frame it was cropped from
    nominal_top_left_frac: tuple[float, float]  # where it sat in that frame, as fractions
    min_score: float = 0.6
    scales: tuple[float, ...] = (1.0,)

    @classmethod
    def from_frame(
        cls,
        frame_gray: np.ndarray,
        rect_px: tuple[int, int, int, int],
        min_score: float = 0.6,
        scales: tuple[float, ...] = (1.0,),
    ) -> AnchorTemplate:
        x0, y0, x1, y1 = rect_px
        h, w = frame_gray.shape[:2]
        return cls(
            np.ascontiguousarray(frame_gray[y0:y1, x0:x1]).astype(np.uint8),
            (w, h),
            (x0 / w, y0 / h),
            min_score,
            scales,
        )

    def nominal_xy_px(self, width: int, height: int) -> tuple[float, float]:
        return self.nominal_top_left_frac[0] * width, self.nominal_top_left_frac[1] * height

    def to_dict(self) -> dict[str, Any]:
        return {
            "template": self.template.tolist(),
            "shape": list(self.template.shape),
            "ref_frame_size_px": list(self.ref_frame_size_px),
            "nominal_top_left_frac": list(self.nominal_top_left_frac),
            "min_score": self.min_score,
            "scales": list(self.scales),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AnchorTemplate:
        try:
            arr = np.asarray(d["template"], dtype=np.int64)
            if arr.ndim != 2 or list(arr.shape) != list(d["shape"]):
                raise ProfileError("anchor template shape mismatch")
            if arr.size == 0 or arr.min() < 0 or arr.max() > 255:
                raise ProfileError("anchor template values must be 0..255")
            rw, rh = d["ref_frame_size_px"]
            nx, ny = d["nominal_top_left_frac"]
            return cls(
                arr.astype(np.uint8),
                (int(rw), int(rh)),
                (float(nx), float(ny)),
                float(d.get("min_score", 0.6)),
                tuple(float(s) for s in d.get("scales", (1.0,))),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProfileError(f"bad anchor: {exc}") from exc


@dataclass
class OverlayProfile:
    """Everything needed to read one producer's overlay."""

    profile_id: str
    layout: dict[str, Roi]
    phase_layouts: dict[str, dict[str, Roi]] = field(default_factory=dict)
    anchor: AnchorTemplate | None = None
    glyphs: list[dict[str, Any]] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    def roi(self, name: str, phase: str | None = None) -> Roi:
        """ROI for ``name`` in ``phase``: the phase override if any, else the base layout."""
        if phase is not None:
            over = self.phase_layouts.get(layout_phase_key(phase), {})
            if name in over:
                return over[name]
        try:
            return self.layout[name]
        except KeyError as exc:
            raise ProfileError(f"profile {self.profile_id!r} has no ROI {name!r}") from exc

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ProfileError(f"unsupported schema_version {self.schema_version}")
        if not self.profile_id:
            raise ProfileError("profile_id is empty")
        if "clock" not in self.layout:
            raise ProfileError("base layout needs a 'clock' ROI")
        for name, roi in self.layout.items():
            if name not in ROI_NAMES:
                raise ProfileError(f"unknown ROI name {name!r}")
            roi.validate(name)
        for key, over in self.phase_layouts.items():
            if key not in PHASE_KEYS:
                raise ProfileError(f"unknown phase key {key!r}")
            for name, roi in over.items():
                if name not in ROI_NAMES:
                    raise ProfileError(f"unknown ROI name {name!r} in phase {key!r}")
                roi.validate(f"{key}.{name}")
        for g in self.glyphs:
            _check_glyph_entry(g)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "layout": {k: v.to_dict() for k, v in self.layout.items()},
            "phase_layouts": {
                p: {k: v.to_dict() for k, v in over.items()}
                for p, over in self.phase_layouts.items()
            },
            "anchor": self.anchor.to_dict() if self.anchor else None,
            "glyphs": self.glyphs,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OverlayProfile:
        try:
            prof = cls(
                profile_id=str(d["profile_id"]),
                layout={k: Roi.from_dict(v) for k, v in d["layout"].items()},
                phase_layouts={
                    p: {k: Roi.from_dict(v) for k, v in over.items()}
                    for p, over in d.get("phase_layouts", {}).items()
                },
                anchor=AnchorTemplate.from_dict(d["anchor"]) if d.get("anchor") else None,
                glyphs=list(d.get("glyphs", [])),
                schema_version=int(d["schema_version"]),
            )
        except (KeyError, TypeError, AttributeError) as exc:
            raise ProfileError(f"malformed profile: {exc!r}") from exc
        prof.validate()
        return prof

    def write(self, path: str | Path) -> None:
        self.validate()
        Path(path).write_text(json.dumps(self.to_dict(), indent=1) + "\n", encoding="utf-8")

    @classmethod
    def read(cls, path: str | Path) -> OverlayProfile:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProfileError(f"{path}: not JSON ({exc})") from exc
        return cls.from_dict(data)


def _check_glyph_entry(g: dict[str, Any]) -> None:
    try:
        char, tpl, shape = g["char"], g["template"], g["shape"]
        arr = np.asarray(tpl)
    except (KeyError, TypeError) as exc:
        raise ProfileError(f"bad glyph entry: {exc!r}") from exc
    if not isinstance(char, str) or len(char) != 1:
        raise ProfileError(f"glyph char must be one character, got {char!r}")
    if arr.ndim != 2 or list(arr.shape) != list(shape):
        raise ProfileError(f"glyph {char!r}: template shape {arr.shape} != {shape}")
    if arr.size == 0 or arr.min() < 0 or arr.max() > 255:
        raise ProfileError(f"glyph {char!r}: values must be 0..255")


def default_template_profile(profile_id: str = "template-v1") -> OverlayProfile:
    """Starting ROIs for ``profile-init``: a guess the operator edits by eye on a screenshot."""
    layout = {
        "banner_anchor": Roi(0.02, 0.01, 0.14, 0.09),
        "label": Roi(0.33, 0.02, 0.67, 0.08),
        "clock": Roi(0.43, 0.09, 0.57, 0.22),
        "red_teams": Roi(0.15, 0.02, 0.32, 0.08),
        "blue_teams": Roi(0.68, 0.02, 0.85, 0.08),
        "red_tips": Roi(0.03, 0.11, 0.07, 0.20),
        "red_lock": Roi(0.09, 0.11, 0.13, 0.20),
        "red_score": Roi(0.30, 0.10, 0.41, 0.21),
        "blue_score": Roi(0.59, 0.10, 0.70, 0.21),
        "blue_lock": Roi(0.87, 0.11, 0.91, 0.20),
        "blue_tips": Roi(0.93, 0.11, 0.97, 0.20),
    }
    # The TELEOP gamepad icon is wider than the AUTO robot icon, so scores shift (a guess).
    teleop = {
        "red_score": Roi(0.32, 0.10, 0.43, 0.21),
        "blue_score": Roi(0.57, 0.10, 0.68, 0.21),
    }
    return OverlayProfile(profile_id, layout, {"teleop": teleop, "endgame": dict(teleop)})
