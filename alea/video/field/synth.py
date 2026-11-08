"""Synthetic scene renderer for tests: grey tiled floor, dark walls, a cube robot, yellow
balls, an optional tall "person" box, Gaussian noise. Not a simulator of real footage."""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product

import numpy as np
from numpy.typing import NDArray

from alea.game import biobuzz as g
from alea.video.geometry import Camera

ImageArray = NDArray[np.uint8]

ROBOT_SIZE_IN = 18.0
PERSON_SIZE_IN = (20.0, 20.0, 66.0)  # x, y, height
ROBOT_BGR = (40, 60, 200)
PERSON_BGR = (60, 160, 60)
BALL_BGR = (0, 230, 255)
WALL_BGR = (45, 45, 50)
TILE_BGR = ((125, 125, 125), (135, 135, 135))
N_TILES = 6


@dataclass(frozen=True)
class FrameTruth:
    frame: int
    robot_centre_in: tuple[float, float] | None
    robot_contact_in: tuple[float, float] | None  # middle of the near bottom edge (x, y - half)
    balls_in: tuple[tuple[float, float], ...]
    person_centre_in: tuple[float, float] | None


def _fill(img: ImageArray, pts: NDArray, color: tuple[int, int, int]) -> None:
    import cv2

    cv2.fillPoly(img, [np.round(pts).astype(np.int32)], color)


def _box_hull(camera: Camera, cx: float, cy: float, sx: float, sy: float, h: float) -> NDArray:
    import cv2

    corners = [
        (cx + dx * sx / 2, cy + dy * sy / 2, z) for dx, dy, z in product((-1, 1), (-1, 1), (0, h))
    ]
    px = np.round(camera.project(np.array(corners))).astype(np.int32)
    return cv2.convexHull(px)


def render_frame(
    camera: Camera,
    image_shape: tuple[int, int],
    robot_xy_in: tuple[float, float] | None = None,
    ball_positions_in: Sequence[tuple[float, float]] = (),
    person_xy_in: tuple[float, float] | None = None,
    noise_sigma: float = 0.0,
    rng: np.random.Generator | None = None,
) -> ImageArray:
    """One BGR frame of shape (h, w, 3)."""
    import cv2

    h, w = image_shape
    img = np.empty((h, w, 3), np.uint8)
    img[:] = WALL_BGR
    s = g.FIELD_SIZE_IN
    t = s / N_TILES
    for i, j in product(range(N_TILES), repeat=2):
        quad = np.array(
            [[i * t, j * t, 0], [(i + 1) * t, j * t, 0], [(i + 1) * t, (j + 1) * t, 0],
             [i * t, (j + 1) * t, 0]]
        )  # fmt: skip
        _fill(img, camera.project(quad), TILE_BGR[(i + j) % 2])
    if person_xy_in is not None:
        hull = _box_hull(camera, *person_xy_in, *PERSON_SIZE_IN)
        cv2.fillPoly(img, [hull], PERSON_BGR)
    if robot_xy_in is not None:
        hull = _box_hull(camera, *robot_xy_in, ROBOT_SIZE_IN, ROBOT_SIZE_IN, ROBOT_SIZE_IN)
        cv2.fillPoly(img, [hull], ROBOT_BGR)
    r_in = g.POLLEN_RADIUS_IN
    for bx, by in ball_positions_in:
        c = camera.project(np.array([[bx, by, r_in], [bx + r_in, by, r_in]]))
        radius = max(2, round(float(np.linalg.norm(c[1] - c[0]))))
        cv2.circle(img, (round(c[0][0]), round(c[0][1])), radius, BALL_BGR, -1)
    if noise_sigma > 0:
        gen = rng if rng is not None else np.random.default_rng(0)
        noisy = img.astype(np.float64) + gen.normal(0, noise_sigma, img.shape)
        img = np.clip(noisy, 0, 255).astype(np.uint8)
    return img


def render_sequence(
    camera: Camera,
    robot_path: Sequence[tuple[float, float]] | None,
    ball_positions: Sequence[tuple[float, float]],
    n_frames: int,
    image_shape: tuple[int, int] = (360, 640),
    person_xy_in: tuple[float, float] | None = None,
    noise_sigma: float = 0.0,
    seed: int = 0,
) -> tuple[list[ImageArray], list[FrameTruth]]:
    """Frames and truth for a robot moving along the polyline `robot_path` (resampled to
    `n_frames` by arc position; None for no robot)."""
    rng = np.random.default_rng(seed)
    frames: list[ImageArray] = []
    truth: list[FrameTruth] = []
    path = None if robot_path is None else np.asarray(robot_path, np.float64)
    for k in range(n_frames):
        pos = None
        if path is not None:
            a = k / max(1, n_frames - 1) * (len(path) - 1)
            idx = np.arange(len(path))
            pos = (float(np.interp(a, idx, path[:, 0])), float(np.interp(a, idx, path[:, 1])))
        frames.append(
            render_frame(camera, image_shape, pos, ball_positions, person_xy_in, noise_sigma, rng)
        )
        contact = None if pos is None else (pos[0], pos[1] - ROBOT_SIZE_IN / 2)
        truth.append(FrameTruth(k, pos, contact, tuple(ball_positions), person_xy_in))
    return frames, truth
