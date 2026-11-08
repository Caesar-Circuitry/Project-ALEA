"""Import hive-shot-lab shot measurements and write the ALEA measurement CSV.

hive-shot-lab (Apache-2.0, github.com/boltonftc/hive-shot-lab, v1.0.0) analyses phone
slow-motion video of the launcher and exports one CSV row per shot. The column set below was
verified from reading its code on 2026-11-08 and may change, so `read_hivelab_csv` takes a
column mapping. Nothing of hive-shot-lab is vendored here; only its CSV is read.

Measurements live in their own CSV file (never in the `launch` table). Row contract: README.md.
"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from alea.game.biobuzz import TICKS_TO_IN_S

# placeholder: last factor of alea.game.TICKS_TO_IN_S; a physics-reviewed PR should export it
# from alea.game
SIM_ASSUMED_EFFICIENCY = 0.45

# Wheel-surface speed of the StarterBot launcher (1:1 drive, 28 ticks/rev, 1.89 in wheel
# radius) without the efficiency factor. TICKS_TO_IN_S already contains 28, 1.89 and the
# efficiency, so dividing it by the efficiency recovers 1/28 * 2*pi*1.89 without retyping them.
_WHEEL_IN_PER_TICK = TICKS_TO_IN_S / SIM_ASSUMED_EFFICIENCY

SOURCE = "hivelab"

# our field -> hive-shot-lab column
DEFAULT_MAPPING: dict[str, str] = {
    "video_file": "video",
    "shot_index": "shot",
    "burst_index": "burst",
    "burst_size": "burst_size",
    "t_video_s": "time_s",
    "v_exit_in_s": "v0_in_s",
    "angle_deg": "angle_deg",
    "apex_in": "apex_in",
    "drag_per_s": "drag_per_s",
    "fit_rms_in": "fit_rms_in",
    "result": "result",
}
REQUIRED_FIELDS = ("shot_index", "t_video_s", "v_exit_in_s", "angle_deg")

MEASUREMENT_COLUMNS = [
    "measurement_id",
    "source",
    "video_file",
    "shot_index",
    "burst_index",
    "burst_size",
    "t_video_s",
    "t_log_s",
    "launch_id",
    "v_exit_in_s",
    "angle_deg",
    "apex_in",
    "drag_per_s",
    "fit_rms_in",
    "result",
    "flywheel_ticks_per_s_before",
    "flywheel_ticks_per_s_after",
    "dip_ticks_per_s",
    "wheel_surface_speed_in_s",
    "efficiency",
    "notes",
]


class HiveLabFormatError(ValueError):
    """The hive-shot-lab CSV lacks a required column or has an unreadable value."""


@dataclass
class HiveLabShot:
    video_file: str
    shot_index: int
    burst_index: int | None
    burst_size: int | None
    t_video_s: float
    v_exit_in_s: float
    angle_deg: float
    apex_in: float | None
    drag_per_s: float | None
    fit_rms_in: float | None
    result: str
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LogLaunch:
    """A launch seen by the robot log (a DB `Launch` row or a fresh detection)."""

    t_s: float
    ticks_per_s_before: float
    ticks_per_s_after: float
    dip_ticks_per_s: float
    launch_id: int | None = None


@dataclass
class ShotMeasurement:
    """One row of the measurement CSV. Log fields are None when the shot is unjoined."""

    measurement_id: str
    video_file: str
    shot_index: int
    burst_index: int | None
    burst_size: int | None
    t_video_s: float
    v_exit_in_s: float
    angle_deg: float
    apex_in: float | None = None
    drag_per_s: float | None = None
    fit_rms_in: float | None = None
    result: str = ""
    source: str = SOURCE
    t_log_s: float | None = None
    launch_id: int | None = None
    flywheel_ticks_per_s_before: float | None = None
    flywheel_ticks_per_s_after: float | None = None
    dip_ticks_per_s: float | None = None
    wheel_surface_speed_in_s: float | None = None
    efficiency: float | None = None
    notes: str = ""


def wheel_surface_speed_in_s(ticks_per_s: float) -> float:
    """Flywheel surface speed for an encoder rate: ticks/s / 28 * 2*pi*1.89 (in/s)."""
    return ticks_per_s * _WHEEL_IN_PER_TICK


def efficiency(v_exit_in_s: float, ticks_per_s: float) -> float:
    """Ball exit speed over wheel surface speed (the sim assumes `SIM_ASSUMED_EFFICIENCY`)."""
    return v_exit_in_s / wheel_surface_speed_in_s(ticks_per_s)


def measurement_id(video_file: str, shot_index: int) -> str:
    return hashlib.sha1(f"{video_file}|{shot_index}".encode(), usedforsecurity=False).hexdigest()[
        :16
    ]


def _float(raw: str, name: str, row_no: int) -> float:
    try:
        return float(raw)
    except ValueError:
        raise HiveLabFormatError(
            f"row {row_no}: column {name!r} is not a number: {raw!r}"
        ) from None


def _opt_float(raw: str | None, name: str, row_no: int) -> float | None:
    if raw is None or raw.strip() == "":
        return None
    return _float(raw, name, row_no)


def _opt_int(raw: str | None, name: str, row_no: int) -> int | None:
    value = _opt_float(raw, name, row_no)
    return None if value is None else round(value)


def read_hivelab_csv(
    path: str | Path, mapping: Mapping[str, str] | None = None
) -> list[HiveLabShot]:
    """Read a hive-shot-lab export. `mapping` overrides entries of `DEFAULT_MAPPING`.

    Raises `HiveLabFormatError` if a required column (shot, time_s, v0_in_s, angle_deg by
    default) is missing. Unmapped columns are kept as strings in `extra`.
    """
    cols = {**DEFAULT_MAPPING, **(mapping or {})}
    unknown = set(cols) - set(DEFAULT_MAPPING)
    if unknown:
        raise HiveLabFormatError(f"unknown mapping fields: {sorted(unknown)}")
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        missing = [f"{cols[f]} ({f})" for f in REQUIRED_FIELDS if cols[f] not in header]
        if missing:
            raise HiveLabFormatError(
                f"missing required column(s) {', '.join(missing)}; found: {', '.join(header)}"
            )
        mapped = set(cols.values())
        shots: list[HiveLabShot] = []
        for row_no, row in enumerate(reader, start=2):

            def get(name: str, row: dict[str, str] = row) -> str | None:
                return row.get(cols[name])

            shots.append(
                HiveLabShot(
                    video_file=(get("video_file") or "").strip(),
                    shot_index=int(_float(get("shot_index") or "", cols["shot_index"], row_no)),
                    burst_index=_opt_int(get("burst_index"), cols["burst_index"], row_no),
                    burst_size=_opt_int(get("burst_size"), cols["burst_size"], row_no),
                    t_video_s=_float(get("t_video_s") or "", cols["t_video_s"], row_no),
                    v_exit_in_s=_float(get("v_exit_in_s") or "", cols["v_exit_in_s"], row_no),
                    angle_deg=_float(get("angle_deg") or "", cols["angle_deg"], row_no),
                    apex_in=_opt_float(get("apex_in"), cols["apex_in"], row_no),
                    drag_per_s=_opt_float(get("drag_per_s"), cols["drag_per_s"], row_no),
                    fit_rms_in=_opt_float(get("fit_rms_in"), cols["fit_rms_in"], row_no),
                    result=(get("result") or "").strip(),
                    extra={k: v for k, v in row.items() if k not in mapped and k is not None},
                )
            )
    return shots


def apply_launch(m: ShotMeasurement, launch: LogLaunch) -> ShotMeasurement:
    """Copy of `m` joined to `launch`: log fields, wheel surface speed and efficiency."""
    before = launch.ticks_per_s_before
    return ShotMeasurement(
        **{
            **m.__dict__,
            "t_log_s": launch.t_s,
            "launch_id": launch.launch_id,
            "flywheel_ticks_per_s_before": before,
            "flywheel_ticks_per_s_after": launch.ticks_per_s_after,
            "dip_ticks_per_s": launch.dip_ticks_per_s,
            "wheel_surface_speed_in_s": wheel_surface_speed_in_s(before),
            "efficiency": efficiency(m.v_exit_in_s, before) if before > 0 else None,
        }
    )


def to_measurements(
    shots: Sequence[HiveLabShot], joins: Sequence[LogLaunch | None] | None = None
) -> list[ShotMeasurement]:
    """One measurement per shot; `joins[i]` is the launch matched to `shots[i]` (or None)."""
    if joins is not None and len(joins) != len(shots):
        raise ValueError("joins must be aligned with shots")
    out: list[ShotMeasurement] = []
    for i, s in enumerate(shots):
        m = ShotMeasurement(
            measurement_id=measurement_id(s.video_file, s.shot_index),
            video_file=s.video_file,
            shot_index=s.shot_index,
            burst_index=s.burst_index,
            burst_size=s.burst_size,
            t_video_s=s.t_video_s,
            v_exit_in_s=s.v_exit_in_s,
            angle_deg=s.angle_deg,
            apex_in=s.apex_in,
            drag_per_s=s.drag_per_s,
            fit_rms_in=s.fit_rms_in,
            result=s.result,
        )
        launch = None if joins is None else joins[i]
        out.append(apply_launch(m, launch) if launch is not None else m)
    return out


def _fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def write_measurements_csv(path: str | Path, rows: Sequence[ShotMeasurement]) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(MEASUREMENT_COLUMNS)
        for r in rows:
            writer.writerow([_fmt(getattr(r, c)) for c in MEASUREMENT_COLUMNS])


_INT_COLUMNS = {"shot_index", "burst_index", "burst_size", "launch_id"}
_STR_COLUMNS = {"measurement_id", "source", "video_file", "result", "notes"}


def read_measurements_csv(path: str | Path) -> list[ShotMeasurement]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != MEASUREMENT_COLUMNS:
            raise HiveLabFormatError(f"unexpected measurement header: {reader.fieldnames}")
        out: list[ShotMeasurement] = []
        for row_no, row in enumerate(reader, start=2):
            kw: dict[str, object] = {}
            for c in MEASUREMENT_COLUMNS:
                raw = row[c]
                if c in _STR_COLUMNS:
                    kw[c] = raw
                elif raw == "":
                    kw[c] = None
                elif c in _INT_COLUMNS:
                    kw[c] = int(raw)
                else:
                    kw[c] = _float(raw, c, row_no)
            out.append(ShotMeasurement(**kw))  # type: ignore[arg-type]
    return out
