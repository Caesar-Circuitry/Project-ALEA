"""Foreground blobs, geometric classification and floor positions of movers.

Position caveat: `floor_position_in` back-projects the blob's CONTACT pixel (bottom edge, middle)
onto the floor. That is the near edge of the robot; its centre is typically 6 to 9 in further
from the camera. Merged blobs, shadows and reflections move the contact by several inches.
Classification is a heuristic (decision 0013); identity and merged robots need a detector.
"""

import csv
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from alea.game import biobuzz as g
from alea.video.field.topdown import TopDownGrid
from alea.video.geometry import Camera, GeometryError

ImageArray = NDArray[np.uint8]

KIND_ROBOT = "robot"
KIND_PERSON = "person"
KIND_SMALL = "small_mover"
KIND_BALL = "ball"


@dataclass(frozen=True)
class Blob:
    bbox_px: tuple[int, int, int, int]  # x, y, w, h
    area_px: int
    contact_px: tuple[float, float]  # bottom-middle of the blob (u, v)


@dataclass(frozen=True)
class ClassifierConfig:
    """Rules for `classify_blob`. Lengths are inches at the contact depth, so they do not
    depend on the video resolution."""

    max_height_in: float = 30.0  # taller than this: person
    field_tol_in: float = 4.0  # contact further outside the field than this: person
    edge_margin_px: int = 3  # blob within this of the frame border: person
    robot_min_width_in: float = 12.0  # wide enough to be a robot (an 18 in robot is 18 to 22)


def foreground_mask(
    frame: ImageArray,
    background: ImageArray,
    thresh: int = 70,
    blur: int = 5,
    min_area_px: int = 250,
    region_mask: ImageArray | None = None,
) -> ImageArray:
    """255 where the blurred frame differs from the blurred background (sum of |diff| over
    channels > `thresh`), cleaned by open/close, components under `min_area_px` dropped."""
    import cv2

    k = max(1, blur | 1)
    fb = cv2.GaussianBlur(frame, (k, k), 0).astype(np.int16)
    bb = cv2.GaussianBlur(background, (k, k), 0).astype(np.int16)
    diff = np.abs(fb - bb)
    if diff.ndim == 3:
        diff = diff.sum(axis=2)
    fg = (diff > thresh).astype(np.uint8) * 255
    if region_mask is not None:
        fg[region_mask == 0] = 0
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(fg)
    keep = np.zeros(n, bool)
    keep[1:] = np.asarray(stats)[1:, cv2.CC_STAT_AREA] >= min_area_px
    lut = keep.astype(np.uint8) * 255
    return lut[np.asarray(labels, dtype=np.int64)]


def blobs(mask: ImageArray, min_area_px: int = 1) -> list[Blob]:
    """Connected components of a mask, with bbox, area and bottom-middle contact pixel."""
    import cv2

    n, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8))
    out: list[Blob] = []
    for i in range(1, n):
        x, y, w, h, area = (int(s) for s in stats[i])
        if area < min_area_px:
            continue
        ys, xs = np.nonzero(labels[y : y + h, x : x + w] == i)
        ys, xs = ys + y, xs + x
        v = float(np.percentile(ys, 97))
        sel = ys >= v - 4
        out.append(Blob((x, y, w, h), area, (float(np.median(xs[sel])), v)))
    return out


def floor_position_in(blob: Blob, camera: Camera) -> tuple[float, float]:
    """Field (x_in, y_in) of the blob's contact pixel on the floor, nan if it misses the floor.

    See the module caveat: this is the bottom edge, not the robot centre."""
    try:
        p = camera.point_on_plane_z(blob.contact_px[0], blob.contact_px[1], 0.0)
    except GeometryError:
        return float("nan"), float("nan")
    return float(p[0]), float(p[1])


def _px_per_in_at(camera: Camera, x_in: float, y_in: float) -> float:
    a = camera.project(np.array([[x_in, y_in, 0.0], [x_in + 1.0, y_in, 0.0]]))
    return float(np.linalg.norm(a[1] - a[0]))


def blob_height_in(blob: Blob, camera: Camera) -> float:
    """Height of the blob top above the floor, from the ray through the top-middle pixel taken
    at the horizontal range of the contact point. nan if undefined. Slightly under-estimates
    (the top edge is further than the contact), so it is a conservative person rule."""
    x_in, y_in = floor_position_in(blob, camera)
    if not np.isfinite(x_in):
        return float("nan")
    x, y, w, _ = blob.bbox_px
    origin, d = camera.ray(x + w / 2.0, float(y))
    range_in = float(np.hypot(x_in - origin[0], y_in - origin[1]))
    d_xy = float(np.hypot(d[0], d[1]))
    if d_xy < 1e-9:
        return float("nan")
    return float(origin[2] + (range_in / d_xy) * d[2])


def classify_blob(
    blob: Blob, camera: Camera, image_shape: tuple[int, ...], config: ClassifierConfig
) -> str:
    """'person' (touches frame edge, contact outside the field, or too tall), else 'robot'
    (wide enough) else 'small_mover'."""
    h_img, w_img = image_shape[:2]
    x, y, w, h = blob.bbox_px
    m = config.edge_margin_px
    if x <= m or y <= m or x + w >= w_img - m or y + h >= h_img - m:
        return KIND_PERSON
    fx, fy = floor_position_in(blob, camera)
    if not np.isfinite(fx):
        return KIND_PERSON
    tol, size = config.field_tol_in, g.FIELD_SIZE_IN
    if not (-tol <= fx <= size + tol and -tol <= fy <= size + tol):
        return KIND_PERSON
    height = blob_height_in(blob, camera)
    if np.isfinite(height) and height > config.max_height_in:
        return KIND_PERSON
    width_in = w / max(_px_per_in_at(camera, fx, fy), 1e-9)
    return KIND_ROBOT if width_in >= config.robot_min_width_in else KIND_SMALL


@dataclass(frozen=True)
class BallCandidate:
    u_px: float
    v_px: float
    radius_px: float
    area_px: int


def yellow_ball_candidates(
    frame: ImageArray,
    floor_mask: ImageArray,
    hsv_lo: tuple[int, int, int] = (18, 110, 150),
    hsv_hi: tuple[int, int, int] = (34, 255, 255),
    radius_px_range: tuple[float, float] = (1.5, 16.0),
) -> list[BallCandidate]:
    """Round yellow blobs (OpenCV HSV, H in 0..179) inside `floor_mask`. Filters on size,
    squareness and fill; tan trousers and benches can pass loose thresholds."""
    import cv2

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, np.array(hsv_lo, np.uint8), np.array(hsv_hi, np.uint8))
    m[floor_mask == 0] = 0
    n, _, stats, cen = cv2.connectedComponentsWithStats(m)
    lo, hi = radius_px_range
    out: list[BallCandidate] = []
    for i in range(1, n):
        _, _, w, h, area = (int(s) for s in stats[i])
        radius = float(np.sqrt(area / np.pi))
        if not lo <= radius <= hi or max(w, h) / max(1, min(w, h)) > 1.8 or area / (w * h) < 0.55:
            continue
        out.append(BallCandidate(float(cen[i][0]), float(cen[i][1]), radius, area))
    return out


def ball_position_in(cand: BallCandidate, camera: Camera) -> tuple[float, float]:
    """Field (x_in, y_in) of a ball centre, via the plane z = pollen radius."""
    try:
        p = camera.point_on_plane_z(cand.u_px, cand.v_px, g.POLLEN_RADIUS_IN)
    except GeometryError:
        return float("nan"), float("nan")
    return float(p[0]), float(p[1])


@dataclass(frozen=True)
class MoverRecord:
    frame: int
    t_s: float
    kind: str
    x_in: float
    y_in: float
    bbox_px: tuple[int, int, int, int]
    area_px: int
    confidence: float
    notes: str = field(default="")


_CSV_FIELDS = ("frame", "t_s", "kind", "x_in", "y_in", "bbox_px", "area_px", "confidence", "notes")


def write_movers_csv(records: Iterable[MoverRecord], path: Path) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(_CSV_FIELDS)
        for r in records:
            bbox = " ".join(str(v) for v in r.bbox_px)
            w.writerow(
                [
                    r.frame,
                    repr(r.t_s),
                    r.kind,
                    repr(r.x_in),
                    repr(r.y_in),
                    bbox,
                    r.area_px,
                    repr(r.confidence),
                    r.notes,
                ]
            )


def read_movers_csv(path: Path) -> list[MoverRecord]:
    out: list[MoverRecord] = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            bx, by, bw, bh = (int(v) for v in row["bbox_px"].split())
            out.append(
                MoverRecord(
                    int(row["frame"]),
                    float(row["t_s"]),
                    row["kind"],
                    float(row["x_in"]),
                    float(row["y_in"]),
                    (bx, by, bw, bh),
                    int(row["area_px"]),
                    float(row["confidence"]),
                    row["notes"],
                )
            )
    return out


def occupancy_fraction(
    masks: Iterable[ImageArray], grid: TopDownGrid | None = None
) -> NDArray[np.float64]:
    """Fraction of masks (top-down, same shape) that are set (> 0) in each cell. With `grid`,
    the mask shape is checked against it."""
    acc: NDArray[np.float64] | None = None
    n = 0
    for m in masks:
        if grid is not None and m.shape[:2] != (grid.size_px, grid.size_px):
            raise ValueError(f"mask shape {m.shape} does not match the grid")
        acc = (m > 0).astype(np.float64) if acc is None else acc + (m > 0)
        n += 1
    if acc is None:
        raise ValueError("no masks")
    return acc / n


def blobs_to_records(
    frame_index: int,
    t_s: float,
    found: Sequence[Blob],
    camera: Camera,
    image_shape: tuple[int, ...],
    config: ClassifierConfig,
) -> list[MoverRecord]:
    out: list[MoverRecord] = []
    for b in found:
        kind = classify_blob(b, camera, image_shape, config)
        x_in, y_in = floor_position_in(b, camera)
        out.append(
            MoverRecord(
                frame_index, t_s, kind, x_in, y_in, b.bbox_px, b.area_px,
                0.5, "contact point is the bottom edge, not the centre",
            )
        )  # fmt: skip
    return out
