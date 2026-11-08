"""Glyph reader for big fixed-font numerals, with no OCR engine (roadmap phase 2, stage 2.2b).

Pipeline: Otsu binarise the ROI, split it into glyph boxes by connected components and column
projection, normalise each box to 12x20, and classify by normalised cross-correlation against
templates the operator taught once from a labelled countdown. Glyph boxes share the vertical
extent of the whole text line, so a colon keeps its dots at the right height.
Limitation: glyphs that touch (no empty pixel column between them) merge into one box.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable
from typing import Any

import numpy as np

GLYPH_W = 12
GLYPH_H = 20
DEFAULT_ALLOWED = "0123456789:"
DIGIT_ASPECT = 0.8  # typical digit width / line height; a wider run is split (touching glyphs)
SPLIT_RATIO = 1.5
MIN_CONTRAST = 60  # gray levels between brightest and darkest pixel for an ROI to hold text


def _cv2() -> Any:
    import cv2

    return cv2


def binarise(
    roi_gray: np.ndarray, light_on_dark: bool = True, min_contrast: int = MIN_CONTRAST
) -> np.ndarray:
    """Otsu threshold; text is 255. An ROI with no contrast (no text) returns all zeros."""
    cv2 = _cv2()
    gray = np.ascontiguousarray(roi_gray, dtype=np.uint8)
    if gray.size == 0:
        return np.zeros_like(gray)
    smooth = cv2.GaussianBlur(gray, (3, 3), 0)
    if int(smooth.max()) - int(smooth.min()) < min_contrast:
        return np.zeros_like(gray)
    flag = cv2.THRESH_BINARY if light_on_dark else cv2.THRESH_BINARY_INV
    _, out = cv2.threshold(gray, 0, 255, flag | cv2.THRESH_OTSU)
    return out


def segment_glyphs(
    binary: np.ndarray, min_area_px: int = 5, min_rel_area: float = 0.04
) -> list[tuple[int, int, int, int]]:
    """Glyph boxes ``(x, y, w, h)`` left to right; ``y``/``h`` span the whole text line."""
    cv2 = _cv2()
    mask = (binary > 0).astype(np.uint8)
    if not mask.any():
        return []
    _, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    areas = stats[1:, cv2.CC_STAT_AREA]
    floor = max(min_area_px, int(min_rel_area * int(areas.max())))
    keep_ids = [i + 1 for i, a in enumerate(areas) if a >= floor]
    if not keep_ids:
        return []
    clean = np.isin(labels, keep_ids)
    cols = clean.any(axis=0)
    rows = np.flatnonzero(clean.any(axis=1))
    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    ink = clean.sum(axis=0)
    line_h = y1 - y0
    exp_w = DIGIT_ASPECT * line_h
    boxes: list[tuple[int, int, int, int]] = []
    x = 0
    width = cols.shape[0]
    while x < width:
        if not cols[x]:
            x += 1
            continue
        start = x
        while x < width and cols[x]:
            x += 1
        run_w = x - start
        n_parts = round(run_w / exp_w) if run_w > SPLIT_RATIO * exp_w else 1
        # touching glyphs: cut a wide run at the emptiest column near each expected boundary
        cuts = [start]
        for k in range(1, n_parts):
            ideal = start + k * run_w / n_parts
            lo = max(cuts[-1] + 1, int(ideal - 0.25 * exp_w))
            hi = min(x - 1, int(ideal + 0.25 * exp_w))
            if hi < lo:
                continue
            cuts.append(min(range(lo, hi + 1), key=lambda c: (ink[c], abs(c - ideal))))
        cuts.append(x)
        boxes.extend((a, y0, b - a, line_h) for a, b in itertools.pairwise(cuts))
    return boxes


def normalise_crop(crop: np.ndarray) -> np.ndarray:
    """Resize a glyph crop to 12x20 and scale to 0..1 (float32, shape (20, 12))."""
    cv2 = _cv2()
    arr = np.asarray(crop)
    if arr.size == 0:
        return np.zeros((GLYPH_H, GLYPH_W), dtype=np.float32)
    arr = (arr > 0).astype(np.uint8) * 255 if arr.max() <= 1 else arr.astype(np.uint8)
    small = cv2.resize(arr, (GLYPH_W, GLYPH_H), interpolation=cv2.INTER_AREA)
    return small.astype(np.float32) / 255.0


def _unit(vec: np.ndarray) -> np.ndarray:
    v = vec.astype(np.float32).ravel()
    v = v - float(v.mean())
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-6 else np.zeros_like(v)


class GlyphSet:
    """Templates per character; classify by normalised cross-correlation."""

    def __init__(self) -> None:
        self._entries: list[tuple[str, np.ndarray]] = []  # (char, uint8 template 20x12)
        self._units: list[np.ndarray] = []

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def chars(self) -> str:
        return "".join(sorted({c for c, _ in self._entries}))

    def _add(self, char: str, template_u8: np.ndarray) -> None:
        self._entries.append((char, template_u8))
        self._units.append(_unit(template_u8.astype(np.float32) / 255.0))

    def learn(self, crops_with_labels: Iterable[tuple[np.ndarray, str]]) -> None:
        """Add one template per character: the mean of that character's crops in this call."""
        groups: dict[str, list[np.ndarray]] = {}
        for crop, char in crops_with_labels:
            if len(char) != 1:
                raise ValueError(f"label must be a single character, got {char!r}")
            groups.setdefault(char, []).append(normalise_crop(crop))
        for char, items in groups.items():
            mean = np.mean(items, axis=0)
            self._add(char, np.clip(np.rint(mean * 255.0), 0, 255).astype(np.uint8))

    def classify_scored(
        self, crop: np.ndarray, allowed: str | None = None
    ) -> tuple[str, float, float]:
        """``(char, best_ncc, margin)``; margin is best minus the best of any other character."""
        if not self._entries:
            raise ValueError("empty GlyphSet: learn or load glyphs first")
        x = _unit(normalise_crop(crop))
        best: dict[str, float] = {}
        for (char, _), unit in zip(self._entries, self._units, strict=True):
            if allowed is not None and char not in allowed:
                continue
            s = float(np.dot(x, unit))
            if s > best.get(char, -2.0):
                best[char] = s
        if not best:
            raise ValueError("no templates for the allowed characters")
        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
        top_char, top = ranked[0]
        margin = top - ranked[1][1] if len(ranked) > 1 else top
        return top_char, top, margin

    def classify(self, crop: np.ndarray, allowed: str | None = None) -> tuple[str, float]:
        """``(char, confidence_margin)``."""
        char, _, margin = self.classify_scored(crop, allowed)
        return char, margin

    def to_entries(self) -> list[dict[str, Any]]:
        return [
            {"char": c, "template": t.tolist(), "shape": [GLYPH_H, GLYPH_W]}
            for c, t in self._entries
        ]

    @classmethod
    def from_entries(cls, entries: Iterable[dict[str, Any]]) -> GlyphSet:
        gs = cls()
        for e in entries:
            gs._add(str(e["char"]), np.asarray(e["template"], dtype=np.uint8))
        return gs


def read_number(
    roi_gray: np.ndarray,
    glyphs: GlyphSet,
    allowed: str = DEFAULT_ALLOWED,
    min_ncc: float = 0.5,
    light_on_dark: bool = True,
) -> tuple[str, float]:
    """Read the glyphs in an ROI. Confidence is the smallest per-glyph margin, 0 if a glyph
    correlates below ``min_ncc`` with every template or if the ROI holds no text."""
    binary = binarise(roi_gray, light_on_dark=light_on_dark)
    boxes = segment_glyphs(binary)
    if not boxes:
        return "", 0.0
    chars: list[str] = []
    conf = 1.0
    for x, y, w, h in boxes:
        char, top, margin = glyphs.classify_scored(binary[y : y + h, x : x + w], allowed)
        chars.append(char)
        conf = min(conf, margin if top >= min_ncc else 0.0)
    return "".join(chars), conf
