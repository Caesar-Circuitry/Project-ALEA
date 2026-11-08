"""Median background of a static-camera clip, an adaptive variant, and a static-camera check.

Memory is bounded: `median_background` keeps at most `max_samples` frames (uniform reservoir
sampling), never the whole clip. A pixel is background if it shows the same thing in most
sampled frames, so anything that sits still for more than half of the clip (a parked robot, a
standing volunteer) becomes part of the background and disappears from the foreground. Use
`windowed_median_background` (a median per time window) or an empty-field image from before
the match when robots park.
"""

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

ImageArray = NDArray[np.uint8]


def _median(frames: Sequence[ImageArray]) -> ImageArray:
    stack = np.stack(frames, axis=0)
    return np.median(stack, axis=0).astype(np.uint8)


def median_background(
    frames_iter: Iterable[ImageArray],
    every: int = 1,
    exclude_mask: NDArray[np.uint8] | None = None,
    max_samples: int = 64,
    seed: int = 0,
) -> ImageArray:
    """Per-pixel median over every `every`-th frame, keeping at most `max_samples` of them.

    Memory is about `max_samples` frames. Where `exclude_mask` > 0 the output is set to 0
    (caller ignores those pixels, e.g. a stream overlay).
    """
    if every < 1 or max_samples < 1:
        raise ValueError("every and max_samples must be >= 1")
    rng = np.random.default_rng(seed)
    reservoir: list[ImageArray] = []
    seen = 0
    for i, frame in enumerate(frames_iter):
        if i % every:
            continue
        seen += 1
        if len(reservoir) < max_samples:
            reservoir.append(frame.copy())
        else:
            j = int(rng.integers(0, seen))
            if j < max_samples:
                reservoir[j] = frame.copy()
    if not reservoir:
        raise ValueError("no frames")
    bg = _median(reservoir)
    if exclude_mask is not None:
        bg[exclude_mask > 0] = 0
    return bg


@dataclass(frozen=True)
class WindowBackground:
    start: int  # first frame index of the window (inclusive)
    stop: int  # last frame index (exclusive)
    image: ImageArray


def windowed_median_background(
    frames: Sequence[ImageArray], window: int, step: int
) -> Iterator[WindowBackground]:
    """Median of each `window`-frame slice, advancing by `step`. A robot parked for less than
    half a window stays foreground; use windows longer than any move and shorter than a park."""
    if window < 1 or step < 1:
        raise ValueError("window and step must be >= 1")
    n = len(frames)
    start = 0
    while start < n:
        stop = min(n, start + window)
        yield WindowBackground(start, stop, _median(frames[start:stop]))
        if stop == n:
            break
        start += step


@dataclass(frozen=True)
class StaticReport:
    max_dx_px: float
    max_dy_px: float
    threshold_px: float
    n_frames: int

    @property
    def static(self) -> bool:
        return max(self.max_dx_px, self.max_dy_px) <= self.threshold_px


def _gray32(image: NDArray, rows: tuple[int, int]) -> NDArray[np.float32]:
    import cv2

    strip = image[rows[0] : rows[1]]
    if strip.ndim == 3:
        strip = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    return strip.astype(np.float32)


def camera_static_check(
    frames: Iterable[ImageArray],
    reference: ImageArray,
    strip_rows: tuple[int, int],
    threshold_px: float = 2.0,
) -> StaticReport:
    """Max |dx|, |dy| of a horizontal strip against `reference`, by phase correlation.

    Pick a strip of fixed structure (rails, wall), not a region robots cross. The measured
    shift includes noise; the spike saw 1.2 px on a steady clip.
    """
    import cv2

    ref = _gray32(reference, strip_rows)
    window = cv2.createHanningWindow((ref.shape[1], ref.shape[0]), cv2.CV_32F)
    max_dx = max_dy = 0.0
    n = 0
    for frame in frames:
        (dx, dy), _ = cv2.phaseCorrelate(ref, _gray32(frame, strip_rows), window)
        max_dx, max_dy = max(max_dx, abs(dx)), max(max_dy, abs(dy))
        n += 1
    return StaticReport(float(max_dx), float(max_dy), float(threshold_px), n)
