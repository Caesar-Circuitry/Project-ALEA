"""Find the overlay banner in a frame and turn profile ROIs into pixel rectangles."""

from __future__ import annotations

from typing import Any

import numpy as np

from alea.video.overlay.glyphs import DEFAULT_ALLOWED, GlyphSet, read_number
from alea.video.overlay.profile import AnchorTemplate, OverlayProfile

DEFAULT_SCALES = (0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25)

# (score, x_px, y_px, scale): best normalised correlation, top-left corner, template scale
AnchorFix = tuple[float, float, float, float]


def _cv2() -> Any:
    import cv2

    return cv2


def to_gray(image: np.ndarray) -> np.ndarray:
    """Gray uint8 from a BGR frame (a 2-D array passes through)."""
    if image.ndim == 2:
        return np.ascontiguousarray(image, dtype=np.uint8)
    return _cv2().cvtColor(image, _cv2().COLOR_BGR2GRAY)


def locate_anchor(
    frame_gray: np.ndarray, template: np.ndarray, scales: tuple[float, ...] = DEFAULT_SCALES
) -> AnchorFix:
    """Best ``cv2.matchTemplate`` (TM_CCOEFF_NORMED) over ``scales`` of the template."""
    cv2 = _cv2()
    fh, fw = frame_gray.shape[:2]
    best: AnchorFix = (-1.0, 0.0, 0.0, 1.0)
    for s in scales:
        tw = max(2, round(template.shape[1] * s))
        th = max(2, round(template.shape[0] * s))
        if tw >= fw or th >= fh:
            continue
        interp = cv2.INTER_AREA if s < 1.0 else cv2.INTER_LINEAR
        tpl = template if s == 1.0 else cv2.resize(template, (tw, th), interpolation=interp)
        res = cv2.matchTemplate(frame_gray, tpl, cv2.TM_CCOEFF_NORMED)
        res = np.nan_to_num(res, nan=-1.0, posinf=-1.0, neginf=-1.0)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val > best[0]:
            best = (float(max_val), float(max_loc[0]), float(max_loc[1]), float(s))
    return best


def _anchor_template_for_frame(anchor: AnchorTemplate, width: int) -> np.ndarray:
    """The stored template rescaled when the video is a different size than its source."""
    ratio = width / anchor.ref_frame_size_px[0]
    if abs(ratio - 1.0) < 1e-3:
        return anchor.template
    cv2 = _cv2()
    th, tw = anchor.template.shape
    size = (max(2, round(tw * ratio)), max(2, round(th * ratio)))
    return cv2.resize(anchor.template, size, interpolation=cv2.INTER_AREA)


def find_overlay(image: np.ndarray, profile: OverlayProfile) -> AnchorFix | None:
    """Locate the profile's anchor; ``None`` if absent or below the anchor's ``min_score``."""
    if profile.anchor is None:
        return None
    gray = to_gray(image)
    tpl = _anchor_template_for_frame(profile.anchor, gray.shape[1])
    fix = locate_anchor(gray, tpl, profile.anchor.scales)
    return fix if fix[0] >= profile.anchor.min_score else None


def overlay_present(
    image: np.ndarray, profile: OverlayProfile, threshold: float | None = None
) -> bool:
    """True when the banner anchor is found. A profile without an anchor cannot tell: True."""
    if profile.anchor is None:
        return True
    gray = to_gray(image)
    tpl = _anchor_template_for_frame(profile.anchor, gray.shape[1])
    score = locate_anchor(gray, tpl, profile.anchor.scales)[0]
    return score >= (profile.anchor.min_score if threshold is None else threshold)


def roi_pixels(
    profile: OverlayProfile,
    roi_name: str,
    frame_shape: tuple[int, ...],
    anchor: AnchorFix | None = None,
    phase: str | None = None,
) -> tuple[int, int, int, int]:
    """Pixel rectangle ``(x0, y0, x1, y1)`` of an ROI, shifted and scaled by the anchor fix."""
    h, w = int(frame_shape[0]), int(frame_shape[1])
    roi = profile.roi(roi_name, phase)
    x0, y0, x1, y1 = roi.x0 * w, roi.y0 * h, roi.x1 * w, roi.y1 * h
    if anchor is not None and profile.anchor is not None:
        _, ax, ay, s = anchor
        nx, ny = profile.anchor.nominal_xy_px(w, h)
        x0, x1 = ax + s * (x0 - nx), ax + s * (x1 - nx)
        y0, y1 = ay + s * (y0 - ny), ay + s * (y1 - ny)
    ix0, iy0 = max(0, int(np.floor(x0))), max(0, int(np.floor(y0)))
    ix1, iy1 = min(w, int(np.ceil(x1))), min(h, int(np.ceil(y1)))
    return ix0, iy0, max(ix1, ix0 + 1), max(iy1, iy0 + 1)


def read_roi_number(
    image: np.ndarray,
    profile: OverlayProfile,
    glyphs: GlyphSet,
    roi_name: str,
    phase: str | None = None,
    anchor: AnchorFix | None = None,
    allowed: str = DEFAULT_ALLOWED,
) -> tuple[str, float]:
    """Text and confidence of one ROI."""
    gray = to_gray(image)
    x0, y0, x1, y1 = roi_pixels(profile, roi_name, gray.shape, anchor, phase)
    return read_number(gray[y0:y1, x0:x1], glyphs, allowed)
