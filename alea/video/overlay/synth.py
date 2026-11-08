"""Synthetic overlay streams for tests and demos (no real footage anywhere).

Draws a fake FTC-style banner (logo block, big ``M:SS`` clock, score / tip / lock numerals, an
icon that grows from AUTO to TELEOP) over a noisy gradient field with moving "people", writes
an MJPG AVI, and returns the exact truth. The clock model follows the assumption stated in the
README: the displayed value is ``ceil(seconds remaining)``, it counts 2:30 -> 2:00 in AUTO,
optionally holds 2:00 for the transition, then counts 2:00 -> 0:00 and holds 0:00.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from alea.video.overlay.glyphs import GlyphSet, binarise, segment_glyphs
from alea.video.overlay.profile import AnchorTemplate, OverlayProfile, Roi, layout_phase_key

AUTO_S = 30.0
TELEOP_S = 120.0
ENDGAME_S = 30.0
CLOCK_START_S = 150
FONT_SCALE_TO_ROI = 0.7  # text cap height as a fraction of ROI height
BANNER_BGR = (30, 28, 26)
ALLIANCE_BGR = {"red": (20, 20, 120), "blue": (120, 40, 20)}
ICON_BGR = {"red": (40, 40, 235), "blue": (235, 110, 40)}
TEAM_FIELDS = {"red": "red_teams", "blue": "blue_teams"}

# --- layouts ----------------------------------------------------------------------------------

_W0, _H0 = 320, 180
_TOP_PX = {
    "banner_anchor": (4, 3, 44, 19),
    "red_teams": (50, 3, 100, 15),
    "label": (105, 3, 215, 15),
    "blue_teams": (220, 3, 270, 15),
    "red_tips": (6, 20, 20, 40),
    "red_lock": (24, 20, 38, 40),
    "red_score": (46, 20, 76, 40),
    "clock": (125, 18, 195, 43),
    "blue_score": (244, 20, 274, 40),
    "blue_lock": (282, 20, 296, 40),
    "blue_tips": (298, 20, 312, 40),
}
_TELEOP_PX = {"red_score": (60, 20, 90, 40), "blue_score": (230, 20, 260, 40)}


def _roi(px: tuple[int, int, int, int], dy: float = 0.0, sy: float = 1.0) -> Roi:
    x0, y0, x1, y1 = px
    return Roi(x0 / _W0, (y0 * sy + dy) / _H0, x1 / _W0, (y1 * sy + dy) / _H0)


def synthetic_layout(variant: str = "top") -> OverlayProfile:
    """Two layouts with the same widgets: banner on top, or at the bottom with bigger text."""
    if variant == "top":
        dy, sy = 0.0, 1.0
    elif variant == "bottom":
        dy, sy = 122.0, 1.15
    else:
        raise ValueError(f"variant must be 'top' or 'bottom', got {variant!r}")
    layout = {n: _roi(px, dy, sy) for n, px in _TOP_PX.items()}
    teleop = {n: _roi(px, dy, sy) for n, px in _TELEOP_PX.items()}
    return OverlayProfile(
        f"synth-{variant}-v1", layout, {"teleop": teleop, "endgame": dict(teleop)}
    )


def _cv2() -> Any:
    import cv2

    return cv2


def _px(roi: Roi, width: int, height: int) -> tuple[int, int, int, int]:
    return (
        round(roi.x0 * width),
        round(roi.y0 * height),
        round(roi.x1 * width),
        round(roi.y1 * height),
    )


def _logo(w: int, h: int) -> np.ndarray:
    """A fixed, distinctive block pattern standing in for the banner logo (BGR)."""
    rng = np.random.default_rng(1234)
    cells = rng.integers(0, 2, size=(4, 10)).astype(np.uint8) * 200 + 30
    cv2 = _cv2()
    gray = cv2.resize(cells, (w, h), interpolation=cv2.INTER_NEAREST)
    bgr = np.stack([gray, np.clip(gray.astype(int) + 20, 0, 255).astype(np.uint8), gray], axis=2)
    return bgr


def _put_text(
    img: np.ndarray,
    text: str,
    rect: tuple[int, int, int, int],
    center: bool = False,
    color: tuple[int, int, int] = (240, 240, 240),
) -> None:
    cv2 = _cv2()
    x0, y0, x1, y1 = rect
    target = FONT_SCALE_TO_ROI * (y1 - y0)
    thick = 1 if target < 14 else 2
    (_, cap), _ = cv2.getTextSize("0", cv2.FONT_HERSHEY_SIMPLEX, 1.0, thick)
    scale = target / cap
    (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    ox = x0 + ((x1 - x0 - tw) // 2 if center else 2)
    oy = y0 + (y1 - y0 + round(target)) // 2
    cv2.putText(img, text, (ox, oy), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def make_noise_pool(rng: np.random.Generator, width: int, height: int, n: int = 6, sigma=4.0):
    return [rng.normal(0.0, sigma, size=(height, width, 3)).astype(np.float32) for _ in range(n)]


def render_frame(
    width: int,
    height: int,
    layout: OverlayProfile,
    clock_s: int | None,
    scores: dict[str, int],
    tips: dict[str, int],
    locks: dict[str, int],
    label: str,
    teams: dict[str, Sequence[int]],
    phase: str,
    rng: np.random.Generator,
    noise_pool: list[np.ndarray] | None = None,
    t_s: float = 0.0,
    clock_text: str | None = None,
) -> np.ndarray:
    """One BGR frame. ``clock_s=None`` draws the field only (dead air, no overlay)."""
    cv2 = _cv2()
    xs = np.linspace(40, 120, width, dtype=np.float32)[None, :]
    ys = np.linspace(60, 20, height, dtype=np.float32)[:, None]
    base = xs * 0.5 + ys
    img = np.stack([base * 0.8, base, base * 0.6], axis=2).astype(np.float32)
    img = np.clip(img, 0, 255).astype(np.uint8)
    # moving "people" along the bottom edge and sides (deterministic in t_s, random look)
    prng = np.random.default_rng(99)
    for _ in range(5):
        px0, speed = prng.uniform(0, width), prng.uniform(-6, 6)
        pw, ph = int(prng.integers(8, 16)), int(prng.integers(30, 55))
        shade = int(prng.integers(10, 60))
        x = int((px0 + speed * t_s) % width)
        cv2.rectangle(img, (x, height - ph), (x + pw, height), (shade, shade, shade + 10), -1)
    if clock_s is not None or clock_text is not None:
        phase_key = layout_phase_key(phase)
        rois = {n: _px(layout.roi(n, phase_key), width, height) for n in layout.layout}
        ymin = min(r[1] for r in rois.values()) - 3
        ymax = max(r[3] for r in rois.values()) + 3
        cv2.rectangle(img, (0, ymin), (width, ymax), BANNER_BGR, -1)
        ax0, ay0, ax1, ay1 = rois["banner_anchor"]
        img[ay0:ay1, ax0:ax1] = _logo(ax1 - ax0, ay1 - ay0)
        text = clock_text if clock_text is not None else _fmt_clock(int(clock_s or 0))
        _put_text(img, text, rois["clock"], center=True)
        _put_text(img, label, rois["label"], center=True, color=(200, 200, 200))
        for alliance in ("red", "blue"):
            sx0, sy0, sx1, sy1 = rois[f"{alliance}_score"]
            cv2.rectangle(img, (sx0, sy0), (sx1, sy1), ALLIANCE_BGR[alliance], -1)
            _put_text(img, str(scores[alliance]), rois[f"{alliance}_score"])
            _put_text(img, str(tips[alliance]), rois[f"{alliance}_tips"])
            _put_text(img, str(locks[alliance]), rois[f"{alliance}_lock"])
            _put_text(
                img,
                " ".join(str(t) for t in teams[alliance]),
                rois[TEAM_FIELDS[alliance]],
                color=(200, 200, 200),
            )
            # icon between the lock numeral and the score; wider in TELEOP (the score shifts)
            lock = rois[f"{alliance}_lock"]
            if alliance == "red":
                ix0, ix1 = lock[2] + 2, sx0 - 2
            else:
                ix0, ix1 = sx1 + 2, lock[0] - 2
            if ix1 > ix0:
                cv2.rectangle(img, (ix0, sy0 + 2), (ix1, sy1 - 2), ICON_BGR[alliance], -1)
    out = img.astype(np.float32)
    if noise_pool:
        out += noise_pool[int(rng.integers(len(noise_pool)))]
    else:
        out += rng.normal(0.0, 4.0, size=out.shape).astype(np.float32)
    return np.clip(out, 0, 255).astype(np.uint8)


def render_results_frame(width: int, height: int, scores: dict[str, int]) -> np.ndarray:
    """A results card with no banner: big scores centred (must never read as a clock)."""
    cv2 = _cv2()
    img = np.full((height, width, 3), (45, 35, 30), dtype=np.uint8)
    text = f"{scores['red']} - {scores['blue']}"
    cv2.putText(
        img,
        text,
        (width // 4, height // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.6,
        (240, 240, 240),
        3,
        cv2.LINE_AA,
    )
    return img


def _fmt_clock(clock_s: int) -> str:
    return f"{clock_s // 60}:{clock_s % 60:02d}"


# --- helpers that seed glyphs and the anchor --------------------------------------------------


def render_roi_gray(
    layout: OverlayProfile,
    roi_name: str,
    text: str,
    rng: np.random.Generator,
    phase: str = "auto",
    size: tuple[int, int] = (_W0, _H0),
    noise_sigma: float = 5.0,
) -> np.ndarray:
    """Gray crop of one ROI with ``text`` drawn the way the synthetic overlay draws it."""
    w, h = size
    img = np.full((h, w, 3), BANNER_BGR, dtype=np.uint8)
    rect = _px(layout.roi(roi_name, phase), w, h)
    if roi_name.endswith("_score"):
        cv2 = _cv2()
        cv2.rectangle(img, rect[:2], rect[2:], ALLIANCE_BGR[roi_name.split("_")[0]], -1)
    _put_text(img, text, rect, center=roi_name == "clock")
    noisy = img.astype(np.float32) + rng.normal(0.0, noise_sigma, img.shape).astype(np.float32)
    gray = _cv2().cvtColor(np.clip(noisy, 0, 255).astype(np.uint8), _cv2().COLOR_BGR2GRAY)
    return gray[rect[1] : rect[3], rect[0] : rect[2]]


def learn_glyphs_from_synthetic(
    layout: OverlayProfile, size: tuple[int, int] = (_W0, _H0), seed: int = 0
) -> GlyphSet:
    """Render each of ``0123456789:`` once per numeral style (clock, score), between two 8s so
    the text-line extent is right, and learn them. In real use the operator labels a countdown."""
    rng = np.random.default_rng(seed)
    gs = GlyphSet()
    for roi_name in ("clock", "red_score", "red_tips"):
        crops: list[tuple[np.ndarray, str]] = []
        narrow = roi_name.endswith("_tips")  # one digit fits; no 8-context needed
        for ch in "0123456789" if narrow else "0123456789:":
            text = ch if narrow else f"8{ch}8"
            gray = render_roi_gray(layout, roi_name, text, rng, size=size, noise_sigma=2.0)
            binary = binarise(gray)
            boxes = segment_glyphs(binary)
            if len(boxes) != len(text):
                raise RuntimeError(
                    f"expected {len(text)} glyph boxes for {text!r}, got {len(boxes)}"
                )
            x, y, w, h = boxes[len(boxes) // 2]
            crops.append((binary[y : y + h, x : x + w], ch))
        gs.learn(crops)
    return gs


def make_synthetic_profile(variant: str = "top", size: tuple[int, int] = (_W0, _H0)):
    """Layout plus anchor template plus learned glyphs: a ready-to-use synthetic profile."""
    layout = synthetic_layout(variant)
    w, h = size
    rng = np.random.default_rng(5)
    frame = render_frame(
        w,
        h,
        layout,
        150,
        {"red": 0, "blue": 0},
        {"red": 0, "blue": 0},
        {"red": 5, "blue": 5},
        "Q1",
        {"red": [1, 2], "blue": [3, 4]},
        "auto",
        rng,
    )
    gray = _cv2().cvtColor(frame, _cv2().COLOR_BGR2GRAY)
    rect = _px(layout.roi("banner_anchor"), w, h)
    layout.anchor = AnchorTemplate.from_frame(gray, rect, min_score=0.6, scales=(1.0,))
    layout.glyphs = learn_glyphs_from_synthetic(layout, size).to_entries()
    layout.validate()
    return layout


# --- timeline ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class DeadAir:
    duration_s: float


@dataclass(frozen=True)
class ScoreChange:
    """``delta`` added to an alliance's ``score`` / ``tips`` / ``lock`` at ``t_play_s`` after
    the clock leaves 2:30 (the transition hold counts)."""

    t_play_s: float
    alliance: str
    field: str
    delta: int
    kind: str = "unknown"


@dataclass(frozen=True)
class Flicker:
    """A wrong red/blue score shown for ``n_frames`` frames starting at ``t_play_s``."""

    t_play_s: float
    alliance: str
    wrong_score: int
    n_frames: int = 3


@dataclass(frozen=True)
class MatchSpec:
    label: str
    teams: dict[str, Sequence[int]] = field(
        default_factory=lambda: {"red": [30403, 7842], "blue": [35722, 25114]}
    )
    pre_hold_s: float = 4.0
    transition_hold_s: float = 8.0  # 0 = the clock does not hold at 2:00
    post_hold_s: float = 5.0
    results_s: float = 3.0
    changes: tuple[ScoreChange, ...] = ()
    flickers: tuple[Flicker, ...] = ()


def tip(t_play_s: float, alliance: str) -> tuple[ScoreChange, ...]:
    """A hive tip: +20 score, +1 tips, -1 lock, all at once."""
    return (
        ScoreChange(t_play_s, alliance, "score", 20, "tip"),
        ScoreChange(t_play_s, alliance, "tips", 1, "tip"),
        ScoreChange(t_play_s, alliance, "lock", -1, "tip"),
    )


@dataclass
class SynthTruth:
    fps: float
    size: tuple[int, int]
    n_frames: int
    duration_s: float
    matches: list[dict[str, Any]]
    events: list[dict[str, Any]]


def clock_state(spec: MatchSpec, tp: float) -> tuple[int, str]:
    """Displayed clock seconds and phase at ``tp`` seconds after the clock leaves 2:30."""
    hold = spec.transition_hold_s
    if tp < 0:
        return CLOCK_START_S, "auto"
    if tp < AUTO_S:
        return math.ceil(CLOCK_START_S - tp - 1e-9), "auto"
    if tp < AUTO_S + hold:
        return int(TELEOP_S), "transition"
    rem = TELEOP_S - (tp - AUTO_S - hold)
    if rem <= 1e-9:
        return 0, "post"
    return math.ceil(rem - 1e-9), "endgame" if rem <= ENDGAME_S else "teleop"


def write_synthetic_stream(
    path: str | Path,
    timeline: Sequence[DeadAir | MatchSpec],
    layout: OverlayProfile | None = None,
    fps: float = 10.0,
    size: tuple[int, int] = (_W0, _H0),
    seed: int = 0,
) -> SynthTruth:
    """Render ``timeline`` to an MJPG AVI at ``path`` and return the exact truth."""
    cv2 = _cv2()
    layout = layout or synthetic_layout("top")
    w, h = size
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
    if not writer.isOpened():
        raise RuntimeError("OpenCV build has no MJPG writer")
    rng = np.random.default_rng(seed)
    pool = make_noise_pool(rng, w, h)
    matches: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    frame_i = 0

    def emit(img: np.ndarray) -> None:
        nonlocal frame_i
        writer.write(img)
        frame_i += 1

    for item in timeline:
        t0 = frame_i / fps
        if isinstance(item, DeadAir):
            for _ in range(round(item.duration_s * fps)):
                emit(
                    render_frame(
                        w, h, layout, None, _Z, _Z, _Z, "", _T, "auto", rng, pool, frame_i / fps
                    )
                )
            continue
        spec = item
        hold = spec.transition_hold_s
        t_end_play = CLOCK_START_S + hold  # tp when the clock reaches 0:00
        n_pre = round(spec.pre_hold_s * fps)
        n_play = round(t_end_play * fps)
        n_post = round(spec.post_hold_s * fps)
        first_frame = frame_i
        total = n_pre + n_play + n_post
        for k in range(total):
            tp = (k - n_pre) / fps
            t_abs = frame_i / fps
            clock, phase = clock_state(spec, tp) if k < n_pre + n_play else (0, "post")
            state = {
                "score": {"red": 0, "blue": 0},
                "tips": {"red": 0, "blue": 0},
                "lock": {"red": 5, "blue": 5},
            }
            for c in spec.changes:
                if tp >= c.t_play_s - 1e-9:
                    state[c.field][c.alliance] += c.delta
            scores = dict(state["score"])
            for fl in spec.flickers:
                if 0 <= tp - fl.t_play_s < fl.n_frames / fps - 1e-9:
                    scores[fl.alliance] = fl.wrong_score
            emit(
                render_frame(
                    w,
                    h,
                    layout,
                    clock,
                    scores,
                    state["tips"],
                    state["lock"],
                    spec.label,
                    spec.teams,
                    phase,
                    rng,
                    pool,
                    t_abs,
                )
            )
        for c in spec.changes:
            k_change = n_pre + math.ceil(c.t_play_s * fps - 1e-9)
            tp_frame = (k_change - n_pre) / fps
            state_old = _state_at(spec, c.t_play_s - 1e-6, c.field, c.alliance)
            _, phase = clock_state(spec, tp_frame) if k_change < n_pre + n_play else (0, "post")
            events.append(
                {
                    "match_label": spec.label,
                    "alliance": c.alliance,
                    "field": c.field,
                    "old": state_old,
                    "new": state_old + c.delta,
                    "delta": c.delta,
                    "t_pts_s": (first_frame + k_change) / fps,
                    "phase": phase,
                    "kind": c.kind,
                }
            )
        play_start = t0 + spec.pre_hold_s
        final = {
            a: sum(c.delta for c in spec.changes if c.field == "score" and c.alliance == a)
            for a in ("red", "blue")
        }
        matches.append(
            {
                "match_label": spec.label,
                "start_pts_s": t0,
                "play_start_pts_s": play_start,
                "play_end_pts_s": play_start + t_end_play,
                "end_pts_s": t0 + total / fps,
                "transition_hold_s": hold,
                "teams": {k: list(v) for k, v in spec.teams.items()},
                "final_score": final,
            }
        )
        for _ in range(round(spec.results_s * fps)):
            emit(render_results_frame(w, h, final))
    writer.release()
    return SynthTruth(fps, size, frame_i, frame_i / fps, matches, events)


_Z = {"red": 0, "blue": 0}
_T: dict[str, Sequence[int]] = {"red": [], "blue": []}


def _state_at(spec: MatchSpec, tp: float, field_name: str, alliance: str) -> int:
    base = 5 if field_name == "lock" else 0
    return base + sum(
        c.delta
        for c in spec.changes
        if c.field == field_name and c.alliance == alliance and c.t_play_s <= tp
    )
