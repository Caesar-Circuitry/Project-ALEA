"""Overlay score events: reader, writer and a seeded synthetic generator.

The real events come from `alea.video.overlay` (JSONL, one object per line, schema version 1).
This module reads them without depending on that package, so tests run on their own.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

SCHEMA_VERSION = 1
FIELDS = ("score", "tips", "lock")
PHASES = ("auto", "transition", "teleop", "endgame", "post")
ALLIANCES = ("red", "blue")

# placeholder: Competition Manual Table 10-2; game point values belong in alea/game via a
# physics-reviewed PR
MATCH_TOTAL_S = 150.0
AUTO_END_S = 30.0
TRANSITION_END_S = 38.0
ENDGAME_START_S = 120.0
SCORE_LAG_S = 1.0  # placeholder: seconds from a ball leaving the launcher to the score changing


@dataclass(frozen=True)
class OverlayEvent:
    schema_version: int
    video_sha256: str
    match_label: str
    event_id: int
    alliance: str
    field: str
    old: float
    new: float
    delta: float
    t_old_pts_s: float
    t_new_pts_s: float
    clock_s_remaining: float | None
    phase: str
    kind_guess: str
    confidence: float
    profile_id: str
    source: str = "overlay"


def parse_event(obj: dict) -> OverlayEvent:
    if obj.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported overlay schema_version {obj.get('schema_version')!r}")
    if obj.get("alliance") not in ALLIANCES:
        raise ValueError(f"bad alliance {obj.get('alliance')!r}")
    if obj.get("field") not in FIELDS:
        raise ValueError(f"bad field {obj.get('field')!r}")
    clock = obj.get("clock_s_remaining")
    return OverlayEvent(
        schema_version=SCHEMA_VERSION,
        video_sha256=str(obj.get("video_sha256", "")),
        match_label=str(obj.get("match_label", "")),
        event_id=int(obj["event_id"]),
        alliance=obj["alliance"],
        field=obj["field"],
        old=float(obj["old"]),
        new=float(obj["new"]),
        delta=float(obj["delta"]),
        t_old_pts_s=float(obj["t_old_pts_s"]),
        t_new_pts_s=float(obj["t_new_pts_s"]),
        clock_s_remaining=None if clock is None else float(clock),
        phase=str(obj.get("phase", "teleop")),
        kind_guess=str(obj.get("kind_guess", "unknown")),
        confidence=float(obj.get("confidence", 1.0)),
        profile_id=str(obj.get("profile_id", "")),
        source=str(obj.get("source", "overlay")),
    )


def read_overlay_events(path: str | Path) -> list[OverlayEvent]:
    """Read a JSONL file; blank lines are skipped, a bad line raises ValueError with its number."""
    events = []
    with Path(path).open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                events.append(parse_event(json.loads(line)))
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"line {n}: {exc}") from exc
    return events


def write_overlay_events(events: list[OverlayEvent], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8", newline="\n") as fh:
        for e in events:
            fh.write(json.dumps(asdict(e)) + "\n")


def phase_for_match_t(t_s: float) -> str:
    if t_s < AUTO_END_S:
        return "auto"
    if t_s < TRANSITION_END_S:
        return "transition"
    if t_s < ENDGAME_START_S:
        return "teleop"
    if t_s < MATCH_TOTAL_S:
        return "endgame"
    return "post"


def synth_overlay_events(
    launch_times_s: list[float],
    seed: int = 0,
    *,
    alliance: str = "red",
    offset_s: float = 0.0,
    make_prob: float = 0.5,
    tip_times_match_s: tuple[float, ...] = (),
    video_offset_s: float = 5.0,
    match_label: str = "SYN",
) -> list[OverlayEvent]:
    """Fake overlay events for a log with known launches.

    Log time `t` is match time `t + offset_s`. Each launch scores 2 points with probability
    `make_prob`, `SCORE_LAG_S` plus up to 0.3 s later. Each time in `tip_times_match_s` adds a
    20 point tip step and a tips-counter step. The other alliance gets a few unrelated score steps.
    """
    rng = np.random.default_rng(seed)
    raw: list[tuple[float, str, str, float, str]] = []  # (match_t, alliance, field, delta, kind)
    for t in launch_times_s:
        if rng.random() < make_prob:
            lag = SCORE_LAG_S + float(rng.uniform(0, 0.3))
            raw.append((t + offset_s + lag, alliance, "score", 2.0, "unknown"))
    for t in tip_times_match_s:
        raw.append((t, alliance, "score", 20.0, "tip"))
        raw.append((t, alliance, "tips", 1.0, "tip"))
    other = "blue" if alliance == "red" else "red"
    for t in rng.uniform(5.0, 140.0, 4):
        raw.append((float(t), other, "score", 2.0, "unknown"))
    raw.sort(key=lambda r: r[0])

    totals: dict[tuple[str, str], float] = {}
    events = []
    for i, (t, who, fld, delta, kind) in enumerate(raw):
        old = totals.get((who, fld), 0.0)
        totals[(who, fld)] = old + delta
        pts = t + video_offset_s
        events.append(
            OverlayEvent(
                schema_version=SCHEMA_VERSION,
                video_sha256="0" * 64,
                match_label=match_label,
                event_id=i,
                alliance=who,
                field=fld,
                old=old,
                new=old + delta,
                delta=delta,
                t_old_pts_s=pts - 0.5,
                t_new_pts_s=pts,
                clock_s_remaining=round(MATCH_TOTAL_S - t, 2),
                phase=phase_for_match_t(t),
                kind_guess=kind,
                confidence=0.95,
                profile_id="synthetic",
            )
        )
    return events
