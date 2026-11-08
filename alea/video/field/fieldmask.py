"""Image-space masks for the field: floor polygon, robot-height prism, overlay band.

Geometry comes from `alea.video.landmarks` (which derives it from `alea.game`). Needs the
`video` extra (cv2, imported lazily).
"""

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from alea.game import biobuzz as g
from alea.video.geometry import Camera, GeometryError
from alea.video.landmarks import landmarks_xyz_in

Array = NDArray[np.float64]
MaskArray = NDArray[np.uint8]

_FLOOR_CORNERS = (
    "field_floor_corner_xlo_ylo",
    "field_floor_corner_xhi_ylo",
    "field_floor_corner_xhi_yhi",
    "field_floor_corner_xlo_yhi",
)


def _corners_xy_in(margin_in: float) -> Array:
    """Floor corners (4, 2) in order, pushed outward by `margin_in` on every side."""
    xy = landmarks_xyz_in(list(_FLOOR_CORNERS))[:, :2]
    centre = xy.mean(axis=0)
    sign = np.sign(xy - centre)
    return xy + sign * margin_in


def _project_checked(camera: Camera, xyz_in: Array) -> Array:
    px = camera.project(xyz_in)
    if not np.all(np.isfinite(px)):
        raise GeometryError("a field point is behind the camera")
    return px


def floor_polygon_px(camera: Camera, image_shape: tuple[int, ...], margin_in: float = 0.0) -> Array:
    """Pixel polygon (4, 2) of the field floor, optionally grown by `margin_in` per side.

    The polygon may leave the image (it is not clipped); `image_shape` is accepted so callers
    pass one shape everywhere and is only validated.
    """
    if len(image_shape) < 2 or image_shape[0] <= 0 or image_shape[1] <= 0:
        raise ValueError(f"bad image_shape {image_shape!r}")
    xy = _corners_xy_in(margin_in)
    xyz = np.column_stack([xy, np.zeros(len(xy))])
    return _project_checked(camera, xyz)


def prism_mask(
    camera: Camera,
    image_shape: tuple[int, ...],
    z_top_in: float = 20.0,
    exclude_rects_px: Sequence[tuple[int, int, int, int]] = (),
    margin_in: float = 0.0,
) -> MaskArray:
    """255 inside the hull of the floor and the same outline lifted to z = `z_top_in`.

    Covers robot bodies standing on the field. `exclude_rects_px` are (x0, y0, x1, y1) boxes
    set to 0 (flower posts, hive houses: not game values, supplied by the caller).
    `margin_in` grows the floor outline so people standing just outside the field are seen.
    """
    import cv2

    xy = _corners_xy_in(margin_in)
    low = np.column_stack([xy, np.zeros(len(xy))])
    high = np.column_stack([xy, np.full(len(xy), float(z_top_in))])
    pts = np.vstack([_project_checked(camera, low), _project_checked(camera, high)])
    hull = cv2.convexHull(np.round(pts).astype(np.int32))
    mask = np.zeros(image_shape[:2], np.uint8)
    cv2.fillPoly(mask, [hull], 255)
    for x0, y0, x1, y1 in exclude_rects_px:
        cv2.rectangle(mask, (int(x0), int(y0)), (int(x1), int(y1)), 0, -1)
    return mask


def floor_mask(camera: Camera, image_shape: tuple[int, ...], margin_in: float = 0.0) -> MaskArray:
    """255 inside the floor polygon only (for colour blobs lying on the floor)."""
    import cv2

    poly = np.round(floor_polygon_px(camera, image_shape, margin_in)).astype(np.int32)
    mask = np.zeros(image_shape[:2], np.uint8)
    cv2.fillPoly(mask, [poly], 255)
    return mask


def overlay_band_mask(image_shape: tuple[int, ...], top_px: int) -> MaskArray:
    """Usable-area mask: 0 in the top `top_px` rows (scoreboard / stream overlay), 255 below."""
    mask = np.full(image_shape[:2], 255, np.uint8)
    mask[: max(0, int(top_px))] = 0
    return mask


def field_size_in() -> float:
    """Field side length in inches (from alea.game)."""
    return float(g.FIELD_SIZE_IN)
