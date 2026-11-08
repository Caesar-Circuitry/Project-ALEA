"""Top-down (bird's-eye) view of the field floor through a calibrated camera.

Grid convention: top-down column u grows with field x, row v grows toward field y low, so
field y grows UP the picture (far side at the top, as seen from the audience). Pixel (u, v)
addresses a pixel centre: u = (x + margin) * px_per_in, v = (n - 1) - (y + margin) * px_per_in.
Only the floor (z = 0) is geometrically correct; anything above it smears away from the camera.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from alea.game import biobuzz as g
from alea.video.geometry import Camera

Array = NDArray[np.float64]
ImageArray = NDArray[np.uint8]


@dataclass(frozen=True)
class TopDownGrid:
    px_per_in: float = 3.0
    margin_in: float = 6.0

    @property
    def size_px(self) -> int:
        """Side length of the (square) top-down image in pixels."""
        return round((g.FIELD_SIZE_IN + 2 * self.margin_in) * self.px_per_in)


def topdown_to_field_in(u_px: float, v_px: float, grid: TopDownGrid) -> tuple[float, float]:
    """Top-down pixel -> field (x_in, y_in)."""
    x_in = u_px / grid.px_per_in - grid.margin_in
    y_in = (grid.size_px - 1 - v_px) / grid.px_per_in - grid.margin_in
    return float(x_in), float(y_in)


def field_to_topdown_px(x_in: float, y_in: float, grid: TopDownGrid) -> tuple[float, float]:
    """Field (x_in, y_in) -> top-down pixel (u_px, v_px). Inverse of `topdown_to_field_in`."""
    u_px = (x_in + grid.margin_in) * grid.px_per_in
    v_px = grid.size_px - 1 - (y_in + grid.margin_in) * grid.px_per_in
    return float(u_px), float(v_px)


def topdown_maps(
    camera: Camera, grid: TopDownGrid
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """`cv2.remap` maps (map_x, map_y), each (n, n): source pixel for every top-down pixel.

    Built from `camera.project` over the floor grid, so lens distortion is included.
    """
    n = grid.size_px
    v, u = np.mgrid[0:n, 0:n].astype(np.float64)
    x_in = u / grid.px_per_in - grid.margin_in
    y_in = (n - 1 - v) / grid.px_per_in - grid.margin_in
    xyz = np.stack([x_in.ravel(), y_in.ravel(), np.zeros(x_in.size)], axis=1)
    px = camera.project(xyz).reshape(n, n, 2)
    # points behind the camera are nan; send them outside the source image
    px = np.nan_to_num(px, nan=-1e6)
    return px[..., 0].astype(np.float32), px[..., 1].astype(np.float32)


def warp_topdown(
    image: NDArray, camera: Camera, grid: TopDownGrid, nearest: bool = False
) -> NDArray:
    """Remap a camera image (grayscale or colour) to the top-down floor view; 0 outside."""
    import cv2

    map_x, map_y = topdown_maps(camera, grid)
    interp = cv2.INTER_NEAREST if nearest else cv2.INTER_LINEAR
    return cv2.remap(image, map_x, map_y, interp, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def draw_field_outline(
    image_topdown: ImageArray,
    grid: TopDownGrid,
    color: tuple[int, int, int] = (0, 255, 0),
    thickness_px: int = 1,
) -> ImageArray:
    """Copy of a top-down BGR image with the field boundary drawn in."""
    import cv2

    out = np.ascontiguousarray(image_topdown.copy())
    s = g.FIELD_SIZE_IN
    p0 = field_to_topdown_px(0.0, 0.0, grid)
    p1 = field_to_topdown_px(s, s, grid)
    cv2.rectangle(
        out,
        (round(p0[0]), round(p0[1])),
        (round(p1[0]), round(p1[1])),
        color,
        thickness_px,
    )
    return out
