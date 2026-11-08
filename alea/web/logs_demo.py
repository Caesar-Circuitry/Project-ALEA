"""Synthetic match for the log viewer: decode, detect launches, hand back plain data."""

from __future__ import annotations

from dataclasses import dataclass

from alea.data import rlog
from alea.data.launches import DetectedLaunch, detect_launches
from alea.data.synthetic import synth_match


@dataclass(frozen=True)
class DemoLog:
    seed: int
    key: str | None
    t_s: list[float]
    flywheel_ticks_per_sec: list[float]
    launches: list[DetectedLaunch]
    true_launch_times_s: list[float]
    note: str


def load_demo(seed: int = 0) -> DemoLog:
    match = synth_match(seed)
    data = rlog.decode(match.data)
    result = detect_launches(data)
    series = data.entries.get(result.key, []) if result.key else []
    return DemoLog(
        seed=seed,
        key=result.key,
        t_s=[t for t, _ in series],
        flywheel_ticks_per_sec=[float(v) for _, v in series],  # type: ignore[arg-type]
        launches=result.launches,
        true_launch_times_s=match.launch_times_s,
        note=result.note,
    )


def launch_rows(log: DemoLog) -> list[dict]:
    return [
        {
            "t_s": round(x.t_s, 2),
            "before_ticks_per_sec": round(x.ticks_per_sec_before, 1),
            "after_ticks_per_sec": round(x.ticks_per_sec_after, 1),
            "dip_ticks_per_sec": round(x.dip_ticks_per_sec, 1),
        }
        for x in log.launches
    ]
