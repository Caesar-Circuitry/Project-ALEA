"""Optional sub-pixel snapping of clicked corners (phase 2, stage 2.1). Needs the `video` extra.

A hand click on a field corner or tile seam is good to 1 to 2 px; `cv2.cornerSubPix` moves it
to the local saddle / corner within `window_px`, typically to 0.3 to 0.5 px on sharp corners. It
only helps where the image really has a corner: never snap blurred or occluded points, and
compare the result with the click (`max_shift_px`) before trusting it.
"""

import numpy as np
from numpy.typing import NDArray


def snap_corner(
    gray: NDArray,
    u_px: float,
    v_px: float,
    window_px: int = 5,
    max_shift_px: float = 3.0,
) -> tuple[float, float]:
    """Return (u_px, v_px) refined by cornerSubPix, or the click itself if it moved too far."""
    import cv2

    img = np.ascontiguousarray(gray, dtype=np.uint8)
    pts = np.array([[[u_px, v_px]]], dtype=np.float32)
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 40, 0.001)
    h, w = img.shape[:2]
    m = window_px + 1
    if not (m <= u_px < w - m and m <= v_px < h - m):
        return float(u_px), float(v_px)  # too close to the border for the search window
    refined = cv2.cornerSubPix(img, pts, (window_px, window_px), (-1, -1), crit)
    u, v = float(refined[0, 0, 0]), float(refined[0, 0, 1])
    if np.hypot(u - u_px, v - v_px) > max_shift_px:
        return float(u_px), float(v_px)
    return u, v
