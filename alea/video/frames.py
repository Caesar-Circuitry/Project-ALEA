"""Video frame access with per-frame presentation timestamps (roadmap phase 2).

``VideoReader`` wraps ``cv2.VideoCapture`` headless. Frame index times nominal fps is only
used for seeking; physics must use the presentation time of each frame, because recordings of
livestreams are often variable frame rate with duplicated frames.
"""

from __future__ import annotations

import bisect
import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

import numpy as np

# A frame interval this far from the median interval (as a fraction) marks a variable rate.
VFR_TOLERANCE = 0.25


class VideoError(RuntimeError):
    """The video could not be opened, or a frame could not be read."""


@dataclass(frozen=True)
class VideoInfo:
    """Container-level facts about a video."""

    path: Path
    width_px: int
    height_px: int
    fps_nominal: float
    frame_count: int


@dataclass(frozen=True)
class Frame:
    """One decoded frame (BGR, as OpenCV delivers it) and its presentation time."""

    index: int
    t_pts_s: float
    image_bgr: np.ndarray


@dataclass(frozen=True)
class TimestampStats:
    """Summary of a presentation-timestamp table."""

    n_frames: int
    median_dt_s: float
    fps_median: float
    min_dt_s: float
    max_dt_s: float
    n_duplicate: int  # frames whose timestamp does not advance
    variable_frame_rate: bool


def analyze_timestamps(
    t_pts_s: Sequence[float], tolerance: float = VFR_TOLERANCE
) -> TimestampStats:
    """Median rate, duplicates and a variable-frame-rate flag for a timestamp table."""
    t = np.asarray(t_pts_s, dtype=float)
    if t.size < 2:
        return TimestampStats(int(t.size), math.nan, math.nan, math.nan, math.nan, 0, False)
    dt = np.diff(t)
    median = float(np.median(dt))
    n_dup = int(np.count_nonzero(dt <= 0.0))
    if median > 0.0:
        vfr = bool(np.any(np.abs(dt - median) > tolerance * median)) or n_dup > 0
        fps = 1.0 / median
    else:
        vfr, fps = True, math.nan
    return TimestampStats(int(t.size), median, fps, float(dt.min()), float(dt.max()), n_dup, vfr)


def nearest_frame(t_pts_s: Sequence[float], t_s: float) -> int:
    """Index of the frame whose presentation time is closest to ``t_s`` (table is sorted)."""
    if len(t_pts_s) == 0:
        raise ValueError("empty timestamp table")
    i = bisect.bisect_left(t_pts_s, t_s)
    if i == 0:
        return 0
    if i == len(t_pts_s):
        return len(t_pts_s) - 1
    return i if t_pts_s[i] - t_s < t_s - t_pts_s[i - 1] else i - 1


def file_sha256(path: Path, chunk_bytes: int = 1 << 20) -> str:
    """SHA-256 of a file, streamed."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def _import_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise VideoError(
            "OpenCV is not installed; run `uv sync --extra video` (or `just sync`)"
        ) from exc
    return cv2


class VideoReader:
    """Random-access reader: ``reader.read(i)`` returns a ``Frame`` with its presentation time.

    ``timestamps_s()`` decodes the whole file once (grab only) and caches the table; use it for
    time-to-frame lookups and variable-frame-rate checks.
    """

    def __init__(self, path: str | Path) -> None:
        self._cv2 = _import_cv2()
        self.path = Path(path)
        if not self.path.is_file():
            raise VideoError(f"{self.path} does not exist")
        self._cap = self._cv2.VideoCapture(str(self.path))
        if not self._cap.isOpened():
            self._cap.release()
            raise VideoError(f"cannot open {self.path} (no decoder for this codec?)")
        cv2 = self._cv2
        fps = float(self._cap.get(cv2.CAP_PROP_FPS))
        self.info = VideoInfo(
            path=self.path,
            width_px=int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height_px=int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            fps_nominal=fps if fps > 0.0 and math.isfinite(fps) else math.nan,
            frame_count=max(int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT)), 0),
        )
        self._timestamps: list[float] | None = None

    @property
    def frame_count(self) -> int:
        if self._timestamps is not None:
            return len(self._timestamps)
        return self.info.frame_count

    def _pts_s(self, index: int) -> float:
        """Presentation time of the frame just decoded; falls back to index / fps."""
        t_s = float(self._cap.get(self._cv2.CAP_PROP_POS_MSEC)) / 1000.0
        if (t_s <= 0.0 or not math.isfinite(t_s)) and index > 0:
            return index / self.info.fps_nominal if math.isfinite(self.info.fps_nominal) else 0.0
        return t_s

    def read(self, index: int) -> Frame:
        """Seek to ``index`` and decode it."""
        if index < 0 or (self.frame_count and index >= self.frame_count):
            raise IndexError(f"frame {index} out of range 0..{self.frame_count - 1}")
        self._cap.set(self._cv2.CAP_PROP_POS_FRAMES, index)
        ok, image = self._cap.read()
        if not ok or image is None:
            raise VideoError(f"cannot decode frame {index} of {self.path}")
        return Frame(index, self._pts_s(index), image)

    def timestamps_s(self) -> list[float]:
        """Presentation time of every frame, from one sequential pass (cached)."""
        if self._timestamps is None:
            self._cap.set(self._cv2.CAP_PROP_POS_FRAMES, 0)
            table: list[float] = []
            while self._cap.grab():
                table.append(self._pts_s(len(table)))
            self._timestamps = table
        return self._timestamps

    def timestamp_stats(self) -> TimestampStats:
        return analyze_timestamps(self.timestamps_s())

    def frame_at_time(self, t_s: float) -> int:
        """Frame index nearest to presentation time ``t_s``."""
        return nearest_frame(self.timestamps_s(), t_s)

    def sha256(self) -> str:
        return file_sha256(self.path)

    def close(self) -> None:
        self._cap.release()

    def __enter__(self) -> VideoReader:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
