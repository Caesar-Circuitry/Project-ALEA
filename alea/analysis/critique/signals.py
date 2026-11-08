"""`MatchSignals`: the arrays the critique features need, independent of the log format."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from alea.data import rlog
from alea.data.contract import canonical_key
from alea.data.importer import read_log
from alea.data.launches import LaunchConfig, detect_launches
from alea.data.logdata import LogData

_F = np.float64


def _empty() -> np.ndarray:
    return np.zeros(0, dtype=_F)


def _empty_bool() -> np.ndarray:
    return np.zeros(0, dtype=bool)


@dataclass
class MatchSignals:
    """Time series from one match. All times are seconds from the log clock (match start = 0)."""

    duration_s: float
    # Alea/Aim/* held onto one timeline `t_s`
    t_s: np.ndarray = field(default_factory=_empty)
    distance_in: np.ndarray = field(default_factory=_empty)
    off_axis_deg: np.ndarray = field(default_factory=_empty)
    heading_error_deg: np.ndarray = field(default_factory=_empty)
    lut_ticks_per_sec: np.ndarray = field(default_factory=_empty)
    aimed: np.ndarray = field(default_factory=_empty_bool)
    in_range: np.ndarray = field(default_factory=_empty_bool)
    # flywheel velocity (absolute, ticks per second) on its own timeline
    flywheel_t_s: np.ndarray = field(default_factory=_empty)
    flywheel_ticks_per_sec: np.ndarray = field(default_factory=_empty)
    # one drive motor velocity (ticks per second) on its own timeline
    drive_t_s: np.ndarray = field(default_factory=_empty)
    drive_ticks_per_sec: np.ndarray = field(default_factory=_empty)
    # detected launches
    launch_t_s: np.ndarray = field(default_factory=_empty)
    launch_before_ticks_per_sec: np.ndarray = field(default_factory=_empty)

    @classmethod
    def from_logdata(cls, data: LogData, config: LaunchConfig | None = None) -> MatchSignals:
        view: dict[str, list] = {}
        for key, samples in data.entries.items():
            canon = canonical_key(key)
            if canon is not None:
                view.setdefault(canon, []).extend(samples)
        ref_key = next(
            (
                k
                for k in ("Alea/Aim/DistanceIn", *sorted(view))
                if k.startswith("Alea/Aim/") and k in view
            ),
            None,
        )
        sig = cls(duration_s=data.duration_s)
        if ref_key is not None:
            t = np.array(sorted({s[0] for s in view[ref_key]}), dtype=_F)
            sig.t_s = t
            sig.distance_in = _hold_float(t, view.get("Alea/Aim/DistanceIn"))
            sig.off_axis_deg = _hold_float(t, view.get("Alea/Aim/OffAxisDeg"))
            sig.heading_error_deg = _hold_float(t, view.get("Alea/Aim/HeadingErrorDeg"))
            sig.lut_ticks_per_sec = _hold_float(t, view.get("Alea/Aim/LutTicksPerSec"))
            sig.aimed = _hold_bool(t, view.get("Alea/Aim/Aimed"))
            sig.in_range = _hold_bool(t, view.get("Alea/Aim/InRange"))

        result = detect_launches(data, config)
        fly_key = result.key
        if fly_key is not None:
            ft, fv = _numeric(data.entries[fly_key])
            sig.flywheel_t_s, sig.flywheel_ticks_per_sec = ft, np.abs(fv)
            sig.launch_t_s = np.array([x.t_s for x in result.launches], dtype=_F)
            sig.launch_before_ticks_per_sec = np.array(
                [x.ticks_per_sec_before for x in result.launches], dtype=_F
            )
        drive_keys = [
            k
            for k in data.entries
            if k != fly_key and "HardwareMap/" in k and k.endswith("/velocity")
        ]
        if drive_keys:
            drive_keys.sort(key=lambda k: (not any(p in k.lower() for p in ("front", "drive")), k))
            sig.drive_t_s, sig.drive_ticks_per_sec = _numeric(data.entries[drive_keys[0]])
        return sig

    @classmethod
    def from_log(cls, path: str | Path, config: LaunchConfig | None = None) -> MatchSignals:
        return cls.from_logdata(read_log(path), config)

    @classmethod
    def from_synthetic(cls, seed: int = 0) -> MatchSignals:
        from alea.data.synthetic import synth_match

        return cls.from_logdata(rlog.decode(synth_match(seed).data))


def _numeric(samples: list) -> tuple[np.ndarray, np.ndarray]:
    rows = sorted(
        (t, float(v)) for t, v in samples if isinstance(v, int | float) and not isinstance(v, bool)
    )
    if not rows:
        return _empty(), _empty()
    arr = np.array(rows, dtype=_F)
    return arr[:, 0], arr[:, 1]


def _hold_index(t: np.ndarray, rows: list) -> np.ndarray:
    st = np.array([s[0] for s in rows], dtype=_F)
    return np.clip(np.searchsorted(st, t, side="right") - 1, 0, len(rows) - 1)


def _hold_float(t: np.ndarray, samples: list | None) -> np.ndarray:
    """Resample (t_s, value) onto `t` holding the last value; a missing key gives NaN."""
    if not samples:
        return np.full(len(t), np.nan)
    rows = sorted(samples, key=lambda s: s[0])
    return np.array([float(rows[i][1]) for i in _hold_index(t, rows)], dtype=_F)


def _hold_bool(t: np.ndarray, samples: list | None) -> np.ndarray:
    if not samples:
        return np.zeros(len(t), dtype=bool)
    rows = sorted(samples, key=lambda s: s[0])
    return np.array([bool(rows[i][1]) for i in _hold_index(t, rows)], dtype=bool)
