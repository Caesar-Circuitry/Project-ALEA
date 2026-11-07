"""Synthetic robot logs for tests and notebooks (no robot needed).

`synth_match(seed)` builds a ~150 s match at 50 Hz as RLOG frames shaped like PsiKit output:
`RealOutputs/Alea/Aim/*`, `/RealMetadata/Alea/Meta/*` (values from `alea.game`), plus
`HardwareMap/launcher/velocity` (flywheel, dips when a ball leaves) and a drive-motor velocity.
The launch times are returned so tests can check the detector. Same seed, same bytes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from alea.data import rlog
from alea.data.contract import AIM_KEYS, META_KEYS
from alea.game import biobuzz as game

LOOP_HZ = 50
LOOP_DT_S = 1.0 / LOOP_HZ
MATCH_DURATION_S = 150.0
FLYWHEEL_KEY = "HardwareMap/launcher/velocity"
DRIVE_KEY = "HardwareMap/frontLeft/velocity"


@dataclass(frozen=True)
class SyntheticMatch:
    data: bytes
    launch_times_s: list[float]
    seed: int
    duration_s: float


def meta_values() -> dict[str, str]:
    values = [
        "1",
        str(game.HIVE_X_IN[0]),
        str(game.HIVE_X_IN[1]),
        str(game.HIVE_AUDIENCE_MOUTH_Y_IN),
        str(game.HIVE_REAR_MOUTH_Y_IN),
        str(math.degrees(game.LAUNCH_PITCH_RAD)),
        str(-game.LAUNCH_EXIT_X_IN),
        str(float(max(game.LUT_TICKS_PER_SEC))),
    ]
    return dict(zip(META_KEYS, values, strict=True))


def synth_match(seed: int = 0, duration_s: float = MATCH_DURATION_S) -> SyntheticMatch:
    rng = np.random.default_rng(seed)
    n = int(duration_s * LOOP_HZ)
    t = np.arange(n) * LOOP_DT_S

    # Segments between launches: the robot drives to a new spot, turns, settles, then fires.
    launch_idx: list[int] = []
    seg_start: list[int] = []
    seg_begin = 0
    while True:
        fire = seg_begin + int(rng.uniform(1.5, 2.5) * LOOP_HZ)
        if fire >= n - LOOP_HZ:
            break
        seg_start.append(seg_begin)
        launch_idx.append(fire)
        seg_begin = fire + int(rng.uniform(0.5, 1.0) * LOOP_HZ)
    if not seg_start:
        raise ValueError("duration_s too short for a launch")

    dist = np.empty(n)
    off_axis = np.empty(n)
    heading_err = np.empty(n)
    target = np.empty(n, dtype=object)
    names = ["RED_AUDIENCE", "RED_REAR", "BLUE_AUDIENCE", "BLUE_REAR"]
    prev_d, prev_o = 50.0, 5.0
    bounds = [*seg_start, n]
    # segments are [seg_start[i], seg_start[i+1]); fill them, tail keeps last values
    for i, s in enumerate(seg_start):
        e = bounds[i + 1]
        new_d = float(rng.uniform(30, 76))
        new_o = float(rng.uniform(-30, 30))
        k = np.arange(e - s)
        ramp = np.clip(k / max(launch_idx[i] - s, 1), 0, 1)
        dist[s:e] = prev_d + (new_d - prev_d) * ramp
        off_axis[s:e] = prev_o + (new_o - prev_o) * ramp
        e0 = float(rng.uniform(-40, 40)) * (1 if rng.random() > 0.2 else 0.1)
        heading_err[s:e] = e0 * np.exp(-k * LOOP_DT_S / 0.4)
        target[s:e] = names[int(rng.integers(0, 4))]
        prev_d, prev_o = new_d, new_o
    dist += rng.normal(0, 0.15, n)
    off_axis += rng.normal(0, 0.1, n)
    heading_err += rng.normal(0, 0.1, n)
    target_heading = 45.0 + 0.0 * t
    turn = np.clip(0.05 * heading_err, -1.0, 1.0)
    lut = np.interp(dist, game.LUT_DISTANCE_IN, game.LUT_TICKS_PER_SEC)
    aimed = np.abs(heading_err) < 2.0
    in_range = (dist >= game.LUT_DISTANCE_IN[0]) & (dist <= game.LUT_DISTANCE_IN[-1])
    in_range &= np.abs(off_axis) <= game.AIM_MAX_OFF_AXIS_DEG

    # flywheel: first-order approach to the LUT setpoint; a dip at each launch, then recovery
    fly = np.empty(n)
    v = 0.0
    dips = {i: float(rng.uniform(150, 250)) for i in launch_idx}
    for i in range(n):
        v += (lut[i] - v) * (1 - math.exp(-LOOP_DT_S / 0.25))
        if i in dips:
            v -= dips[i]
        fly[i] = v
    fly += rng.normal(0, 3.0, n)
    drive = 800 * np.sin(t / 3.0) * np.sin(t / 7.0) + rng.normal(0, 20, n)

    meta = meta_values()
    frames: list[tuple[float, dict]] = [(0.0, {f"/RealMetadata/{k}": v_ for k, v_ in meta.items()})]
    for i in range(n):
        row = [target[i], True, dist[i], off_axis[i], target_heading[i], heading_err[i], turn[i],
               lut[i], bool(aimed[i]), bool(in_range[i])]  # fmt: skip
        values: dict = {f"RealOutputs/{k}": x for k, x in zip(AIM_KEYS, row, strict=True)}
        values[FLYWHEEL_KEY] = float(fly[i])
        values[DRIVE_KEY] = float(drive[i])
        frames.append((float(t[i]), values))
    return SyntheticMatch(
        data=rlog.encode(frames),
        launch_times_s=[float(t[i]) for i in launch_idx],
        seed=seed,
        duration_s=duration_s,
    )


def write_matches(
    outdir: str | Path, count: int, seed: int = 0
) -> list[tuple[Path, SyntheticMatch]]:
    """Write `count` logs (seeds seed..seed+count-1) into `outdir`; returns path and truth."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for k in range(count):
        m = synth_match(seed + k)
        path = out / f"synth_{seed + k:04d}.rlog"
        path.write_bytes(m.data)
        written.append((path, m))
    return written
