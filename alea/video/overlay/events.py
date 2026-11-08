"""Overlay events: debounced score / tips / lock changes with frame-exact times.

Each change of an alliance's score, tips or lock numeral is accepted only after the new value
reads identically in ``stable_samples`` consecutive samples, is refined by bisection at the
native frame rate, assigned a match phase from the clock model, and decomposed into known
score increments. The output is ``overlay_events.jsonl`` (one record per change) and the raw
5 Hz readings as a CSV for audit. Records carry ``t_old_pts_s`` / ``t_new_pts_s`` (the overlay
lags the physical event by the scorer's delay, so this is when the OVERLAY changed).

UNVERIFIED on real footage: that the displayed clock excludes the 8 s transition, the meaning
of the house (tips of 4) and lock (nectar locked) icons, and that tips/lock are single numerals
in their own ROI (the "/4" text must sit outside the ROI).
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from alea.video.frames import VideoReader
from alea.video.overlay.glyphs import GlyphSet
from alea.video.overlay.locate import find_overlay, read_roi_number
from alea.video.overlay.profile import OverlayProfile

SCHEMA_VERSION = 1
ALLIANCES = ("red", "blue")
FIELDS = ("score", "tips", "lock")
PHASES = ("auto", "transition", "teleop", "endgame", "post")
KINDS = ("tip", "leave", "park", "flower", "garden", "penalty", "adjustment", "unknown")
FIELD_RANGE = {"score": (0, 999), "tips": (0, 9), "lock": (0, 5)}
MIN_MARGIN = 0.15
CONF_FULL_MARGIN = 0.5  # a glyph margin this large counts as full confidence
CLOCK_START_S = 150.0
AUTO_END_CLOCK_S = 120.0
ENDGAME_S = 30.0
FLOWER_WINDOW_S = 60.0  # flowers score only in the last minute (manual 10.5, inferred use)

# placeholder: Competition Manual Table 10-2; game point values belong in alea/game via a
# physics-reviewed PR
INCREMENTS = {20: "tip", 3: "leave", 5: "park|nectar_bonus", 2: "flower|cell", 1: "garden"}

EVENT_KEYS = (
    "schema_version",
    "video_sha256",
    "match_label",
    "event_id",
    "alliance",
    "field",
    "old",
    "new",
    "delta",
    "t_old_pts_s",
    "t_new_pts_s",
    "clock_s_remaining",
    "phase",
    "kind_guess",
    "confidence",
    "profile_id",
    "source",
)
SERIES_COLUMNS = (
    "frame",
    "t_pts_s",
    "phase",
    "red_score",
    "red_score_conf",
    "blue_score",
    "blue_score_conf",
    "red_tips",
    "red_tips_conf",
    "blue_tips",
    "blue_tips_conf",
    "red_lock",
    "red_lock_conf",
    "blue_lock",
    "blue_lock_conf",
)


class EventsError(ValueError):
    """An events file is malformed."""


@dataclass(frozen=True)
class OverlayEvent:
    schema_version: int
    video_sha256: str
    match_label: str | None
    event_id: str
    alliance: str
    field: str
    old: int
    new: int
    delta: int
    t_old_pts_s: float
    t_new_pts_s: float
    clock_s_remaining: float
    phase: str
    kind_guess: str
    confidence: float
    profile_id: str
    source: str = "overlay"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --- clock model and phases -------------------------------------------------------------------


@dataclass(frozen=True)
class ClockModel:
    """Maps video time to displayed clock and match phase for one segment."""

    play_start_pts_s: float
    play_end_pts_s: float
    transition_start_pts_s: float | None = None
    transition_end_pts_s: float | None = None

    @classmethod
    def from_segment(cls, seg: dict[str, Any]) -> ClockModel:
        clock = seg.get("evidence", {}).get("clock", {})
        return cls(
            float(seg["play_start_pts_s"]),
            float(seg["play_end_pts_s"]),
            clock.get("transition_start_pts_s"),
            clock.get("transition_end_pts_s"),
        )

    def clock_s_remaining(self, t_pts_s: float) -> float:
        if t_pts_s >= self.play_end_pts_s:
            return 0.0
        ts, te = self.transition_start_pts_s, self.transition_end_pts_s
        if ts is not None and te is not None:
            if t_pts_s < ts:
                return min(CLOCK_START_S, CLOCK_START_S - (t_pts_s - self.play_start_pts_s))
            if t_pts_s < te:
                return AUTO_END_CLOCK_S
        return min(CLOCK_START_S, self.play_end_pts_s - t_pts_s)

    def phase(self, t_pts_s: float) -> str:
        if t_pts_s >= self.play_end_pts_s:
            return "post"
        ts, te = self.transition_start_pts_s, self.transition_end_pts_s
        if ts is not None and te is not None:
            if t_pts_s < ts:
                return "auto"
            if t_pts_s < te:
                return "transition"
        rem = self.clock_s_remaining(t_pts_s)
        if rem <= ENDGAME_S:
            return "endgame"
        if rem > AUTO_END_CLOCK_S:
            return "auto"
        return "teleop"


# --- decomposition ----------------------------------------------------------------------------


def _decompose(delta: int, allowed: list[int]) -> list[int] | None:
    """Fewest increments from ``allowed`` summing to ``delta`` (small DP), or None."""
    if delta <= 0:
        return None
    best: dict[int, list[int]] = {0: []}
    for total in range(1, delta + 1):
        cands = [best[total - a] + [a] for a in allowed if total - a in best]
        if cands:
            best[total] = min(cands, key=len)
    return best.get(delta)


def guess_kind(field: str, old: int, new: int, phase: str, clock_remaining_s: float) -> str:
    """Best-guess cause of a change, from the increment table and the phase."""
    delta = new - old
    if delta == 0:
        return "unknown"
    if field == "lock":  # nectar locked only falls (inferred); a rise is a correction
        return "adjustment" if delta > 0 else "unknown"
    if delta < 0:
        return "adjustment"
    if field == "tips":
        return "tip" if delta == 1 else "unknown"
    # score
    parts = _decompose(delta, list(INCREMENTS))
    if parts is None or len(parts) != 1:
        return "unknown"
    name = INCREMENTS[parts[0]].split("|")[0]
    if name == "tip":
        return "tip"
    if name == "leave":
        return "leave" if phase in ("auto", "transition") else "unknown"
    if name == "park":
        return "park" if phase in ("auto", "transition", "endgame", "post") else "unknown"
    if name == "flower":
        return "flower" if clock_remaining_s <= FLOWER_WINDOW_S else "unknown"
    if name == "garden":
        return "garden" if phase in ("endgame", "post") else "unknown"
    return "unknown"


# --- sampling and debouncing ------------------------------------------------------------------


@dataclass
class _Reading:
    value: int | None
    conf: float


def _valid(field: str, text: str, conf: float, min_margin: float) -> _Reading:
    if not text or not text.isdigit() or conf < min_margin:
        return _Reading(None, conf)
    value = int(text)
    lo, hi = FIELD_RANGE[field]
    return _Reading(value if lo <= value <= hi else None, conf)


def read_field(
    image_bgr: np.ndarray,
    profile: OverlayProfile,
    glyphs: GlyphSet,
    alliance: str,
    field: str,
    phase: str,
    anchor: Any = None,
    min_margin: float = MIN_MARGIN,
) -> _Reading:
    text, conf = read_roi_number(
        image_bgr, profile, glyphs, f"{alliance}_{field}", phase, anchor, allowed="0123456789"
    )
    return _valid(field, text, conf, min_margin)


class _Tracker:
    """Accepts a value change only after ``stable`` consecutive identical valid readings."""

    def __init__(self, stable: int) -> None:
        self.stable = stable
        self.cur: int | None = None
        self.last_cur_idx = -1
        self._cand: int | None = None
        self._cand_start = -1
        self._cand_conf: list[float] = []

    def push(self, idx: int, r: _Reading) -> dict[str, Any] | None:
        if r.value is None:
            return None
        if self._cand == r.value:
            self._cand_conf.append(r.conf)
        elif r.value != self.cur:
            self._cand, self._cand_start, self._cand_conf = r.value, idx, [r.conf]
        if r.value == self.cur:
            self.last_cur_idx = idx
            self._cand = None
            return None
        if len(self._cand_conf) < self.stable:
            return None
        change = None
        if self.cur is not None:
            change = {
                "old": self.cur,
                "new": r.value,
                "old_idx": self.last_cur_idx,
                "new_idx": self._cand_start,
                "conf": float(np.mean(self._cand_conf)),
            }
        self.cur, self.last_cur_idx, self._cand = r.value, idx, None
        return change


def _sample_frames(reader: VideoReader, t0: float, t1: float, sample_hz: float) -> list[int]:
    ts = reader.timestamps_s()
    frames: list[int] = []
    t = t0
    while t <= t1:
        i = reader.frame_at_time(t)
        if not frames or i != frames[-1]:
            frames.append(i)
        t += 1.0 / sample_hz
    return [i for i in frames if 0 <= i < len(ts)]


def _refine_change(
    reader: VideoReader,
    profile: OverlayProfile,
    glyphs: GlyphSet,
    model: ClockModel,
    alliance: str,
    field: str,
    old_frame: int,
    new_frame: int,
    new_value: int,
    min_margin: float,
) -> tuple[float, float]:
    """Bisect to (last frame with the old value, first frame with the new value)."""
    ts = reader.timestamps_s()
    lo, hi = old_frame, new_frame
    while hi - lo > 1:
        mid = (lo + hi) // 2
        img = reader.read(mid).image_bgr
        fix = find_overlay(img, profile)
        r = read_field(img, profile, glyphs, alliance, field, model.phase(ts[mid]), fix, min_margin)
        if r.value == new_value:
            hi = mid
        else:
            lo = mid
    return ts[lo], ts[hi]


def extract_events(
    reader: VideoReader,
    profile: OverlayProfile,
    glyphs: GlyphSet,
    segment: dict[str, Any],
    sample_hz: float = 5.0,
    stable_samples: int = 3,
    min_margin: float = MIN_MARGIN,
    video_sha256: str | None = None,
) -> tuple[list[OverlayEvent], list[dict[str, Any]]]:
    """Events and the raw sample series for one segment dict (``runs_to_segments`` shape)."""
    model = ClockModel.from_segment(segment)
    sha = video_sha256 if video_sha256 is not None else reader.sha256()
    label = segment.get("match_label")
    t0 = max(float(segment["start_pts_s"]), model.play_start_pts_s - 2.0)
    t1 = float(segment["end_pts_s"])
    ts = reader.timestamps_s()
    frames = _sample_frames(reader, t0, t1, sample_hz)
    trackers = {(a, f): _Tracker(stable_samples) for a in ALLIANCES for f in FIELDS}
    raw: list[tuple[str, str, dict[str, Any], int]] = []
    series: list[dict[str, Any]] = []
    for idx, fi in enumerate(frames):
        t = ts[fi]
        phase = model.phase(t)
        img = reader.read(fi).image_bgr
        fix = find_overlay(img, profile)
        row: dict[str, Any] = {"frame": fi, "t_pts_s": round(t, 4), "phase": phase}
        overlay_ok = profile.anchor is None or fix is not None
        for a in ALLIANCES:
            for f in FIELDS:
                r = (
                    read_field(img, profile, glyphs, a, f, phase, fix, min_margin)
                    if overlay_ok
                    else _Reading(None, 0.0)
                )
                row[f"{a}_{f}"] = r.value
                row[f"{a}_{f}_conf"] = round(r.conf, 4)
                change = trackers[(a, f)].push(idx, r)
                if change:
                    raw.append((a, f, change, idx))
        series.append(row)
    events: list[OverlayEvent] = []
    for a, f, ch, _ in raw:
        of, nf = frames[ch["old_idx"]], frames[ch["new_idx"]]
        t_old, t_new = _refine_change(
            reader, profile, glyphs, model, a, f, of, nf, ch["new"], min_margin
        )
        phase = model.phase(t_new)
        rem = model.clock_s_remaining(t_new)
        events.append(
            OverlayEvent(
                SCHEMA_VERSION, sha, label, "", a, f, ch["old"], ch["new"], ch["new"] - ch["old"],
                round(t_old, 4), round(t_new, 4), round(rem, 3), phase,
                guess_kind(f, ch["old"], ch["new"], phase, rem),
                min(1.0, ch["conf"] / CONF_FULL_MARGIN), profile.profile_id,
            )
        )  # fmt: skip
    events.sort(key=lambda e: (e.t_new_pts_s, e.alliance, e.field))
    events = _finish(events, segment)
    return events, series


def _finish(events: list[OverlayEvent], segment: dict[str, Any]) -> list[OverlayEvent]:
    """Corroborate tips with the tips counter, scale confidence, assign event ids."""
    tag = segment.get("match_label") or segment.get("segment_id") or "seg"
    out: list[OverlayEvent] = []
    for n, e in enumerate(events):
        conf = min(1.0, max(0.0, e.confidence))
        if e.field == "score" and e.kind_guess == "tip":
            near = any(
                o.field == "tips" and o.alliance == e.alliance and o.delta == 1
                and abs(o.t_new_pts_s - e.t_new_pts_s) <= 3.0
                for o in events
            )  # fmt: skip
            conf = conf if near else conf * 0.6
        if e.kind_guess == "unknown":
            conf *= 0.7
        out.append(
            OverlayEvent(
                **{**e.to_dict(), "event_id": f"{tag}-e{n:03d}", "confidence": round(conf, 4)}
            )
        )
    return out


def final_scores(
    reader: VideoReader,
    profile: OverlayProfile,
    glyphs: GlyphSet,
    segment: dict[str, Any],
    offset_s: float = 2.0,
    n_votes: int = 5,
) -> dict[str, int | None]:
    """Red and blue scores read ``offset_s`` after the end of play (median of ``n_votes``)."""
    model = ClockModel.from_segment(segment)
    t_mid = model.play_end_pts_s + offset_s
    ts = reader.timestamps_s()
    centre = reader.frame_at_time(t_mid)
    out: dict[str, int | None] = {}
    for a in ALLIANCES:
        votes: list[int] = []
        for i in range(centre - n_votes // 2, centre + n_votes // 2 + 1):
            if not 0 <= i < len(ts):
                continue
            img = reader.read(i).image_bgr
            fix = find_overlay(img, profile)
            if profile.anchor is not None and fix is None:
                continue
            r = read_field(img, profile, glyphs, a, "score", "post", fix)
            if r.value is not None:
                votes.append(r.value)
        out[a] = int(np.median(votes)) if votes else None
    return out


# --- files ------------------------------------------------------------------------------------


def write_events_jsonl(path: str | Path, events: Iterable[OverlayEvent]) -> None:
    lines = [json.dumps(e.to_dict(), sort_keys=False) for e in events]
    Path(path).write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def read_events_jsonl(path: str | Path) -> list[OverlayEvent]:
    events: list[OverlayEvent] = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EventsError(f"line {n}: not JSON ({exc})") from exc
        if not isinstance(d, dict) or set(d) != set(EVENT_KEYS):
            raise EventsError(f"line {n}: keys differ from the overlay-event schema")
        if d["schema_version"] != SCHEMA_VERSION:
            raise EventsError(f"line {n}: unsupported schema_version {d['schema_version']}")
        if d["alliance"] not in ALLIANCES or d["field"] not in FIELDS:
            raise EventsError(f"line {n}: bad alliance/field")
        if d["phase"] not in PHASES or d["kind_guess"] not in KINDS:
            raise EventsError(f"line {n}: bad phase/kind_guess")
        if not math.isfinite(float(d["t_new_pts_s"])):
            raise EventsError(f"line {n}: bad time")
        events.append(OverlayEvent(**d))
    return events


def write_series_csv(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=SERIES_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row.get(k) is None else row[k]) for k in SERIES_COLUMNS})
