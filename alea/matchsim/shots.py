"""Pluggable shot-success models for the match simulator.

A model answers one question: given where the robot stands and what flywheel speed it commands,
how likely is the ball to score in the raised cell? The match simulator never fires a ball; it
asks a `ShotSuccessModel`. Swap the placeholder for the table built from a finished shot study
(`TableShotModel`) or, later, a fit to hive-shot-lab video data.
"""

import math
from pathlib import Path
from typing import Protocol

import numpy as np

from alea.game.biobuzz import (
    AIM_MAX_OFF_AXIS_DEG,
    INNER_HALF_WIDTH_IN,
    LUT_DISTANCE_IN,
    LUT_TICKS_PER_SEC,
)
from alea.sim.results import load_summary

# The sim's assumed flywheel efficiency: the last factor of alea.game.biobuzz.TICKS_TO_IN_S
# (1/28 * 2*pi * 1.89 * 0.45). A real launcher whose efficiency differs shifts every ball speed
# by the ratio and misses. Placeholder until the hive-shot-lab calibration measures it.
SIM_ASSUMED_EFFICIENCY = 0.45


class ShotSuccessModel(Protocol):
    def p_make(
        self,
        distance_in: float,
        off_axis_deg: float,
        ticks_per_s: float,
        rng: np.random.Generator | None = None,
    ) -> float:
        """Probability in [0, 1] that one shot scores."""
        ...


def sample_make(
    model: ShotSuccessModel,
    distance_in: float,
    off_axis_deg: float,
    ticks_per_s: float,
    rng: np.random.Generator,
) -> bool:
    """Draw one Bernoulli outcome from the model's make probability."""
    return bool(rng.random() < model.p_make(distance_in, off_axis_deg, ticks_per_s, rng))


class LutSpeedModel:
    """Flywheel ticks/s for a distance, by linear interpolation of the launch LUT.

    The table is `alea.game.biobuzz.LUT_DISTANCE_IN` / `LUT_TICKS_PER_SEC` (unverified on the
    robot). Outside 24..80 in the end values hold (np.interp clamps). `bias_frac` scales the
    commanded speed (a mis-calibrated LUT).
    """

    def __init__(self, bias_frac: float = 0.0):
        self.bias_frac = bias_frac
        self._d = np.asarray(LUT_DISTANCE_IN, dtype=float)
        self._t = np.asarray(LUT_TICKS_PER_SEC, dtype=float)

    def ticks_per_s(self, distance_in: float) -> float:
        return float(np.interp(distance_in, self._d, self._t)) * (1.0 + self.bias_frac)


_LUT = LutSpeedModel()


def _geometry_factor(distance_in: float, off_axis_deg: float) -> float:
    """Placeholder shape in [0, 1]: falls off beyond the LUT range and with off-axis angle."""
    far = 1.0 / (1.0 + math.exp((distance_in - 70.0) / 6.0))
    near = 1.0 / (1.0 + math.exp((22.0 - distance_in) / 3.0))
    off = max(0.0, 1.0 - (abs(off_axis_deg) / AIM_MAX_OFF_AXIS_DEG) ** 2)
    return far * near * off


def _gauss_window(mean: float, noise_sd: float, window_sd: float) -> float:
    """E[exp(-x^2 / (2 w^2))] for x ~ N(mean, noise_sd^2): a smooth acceptance window."""
    v = window_sd**2 + noise_sd**2
    return (window_sd / math.sqrt(v)) * math.exp(-(mean**2) / (2 * v))


class PlaceholderShotModel:
    """Smooth analytic make probability; the shape is NOT fitted to data.

    p = peak_make * geometry(distance, off-axis) * speed window * aim window, where the two
    windows are Gaussian acceptance windows convolved with the launcher's noise, so more noise
    always lowers p. `efficiency` is the real launcher's efficiency; the sim assumes
    SIM_ASSUMED_EFFICIENCY (0.45), so the default efficiency gives no systematic speed error.
    """

    def __init__(
        self,
        efficiency: float = SIM_ASSUMED_EFFICIENCY,
        speed_noise_frac: float = 0.03,
        aim_noise_deg: float = 2.0,
        peak_make: float = 0.95,
        speed_window_frac: float = 0.05,
        aim_window_frac: float = 0.5,
    ):
        self.efficiency = efficiency
        self.speed_noise_frac = speed_noise_frac
        self.aim_noise_deg = aim_noise_deg
        self.peak_make = peak_make
        self.speed_window_frac = speed_window_frac
        self.aim_window_frac = aim_window_frac

    def p_make(
        self,
        distance_in: float,
        off_axis_deg: float,
        ticks_per_s: float,
        rng: np.random.Generator | None = None,
    ) -> float:
        ideal_ticks = _LUT.ticks_per_s(distance_in)
        speed_mean_err = ticks_per_s / ideal_ticks * (self.efficiency / SIM_ASSUMED_EFFICIENCY) - 1
        f_speed = _gauss_window(speed_mean_err, self.speed_noise_frac, self.speed_window_frac)
        aim_window_deg = math.degrees(
            math.atan(self.aim_window_frac * INNER_HALF_WIDTH_IN / max(distance_in, 1.0))
        )
        f_aim = _gauss_window(0.0, self.aim_noise_deg, aim_window_deg)
        p = self.peak_make * _geometry_factor(distance_in, off_axis_deg) * f_speed * f_aim
        return min(1.0, max(0.0, p))


class TableShotModel:
    """Make rate from a finished shot study, times the placeholder distance/off-axis shape.

    The study reports one aggregate hit rate per error condition (aim, flywheel speed, robot
    moving, ball size, bounce), averaged over all standing spots, so it carries no distance
    information. The rate is interpolated over (aim_deg, speed_pct) at the launcher's
    operating noise, averaged over ball size and bounce, using the rows whose robot speed is
    nearest `robot_speed_in_s`. Distance and off-axis dependence stay the placeholder shape.
    """

    def __init__(self, table: dict[tuple[float, float], float], aim_deg: float, speed_pct: float):
        if not table:
            raise ValueError("empty make-rate table")
        self.table = dict(table)
        self.aim_deg = aim_deg
        self.speed_pct = speed_pct
        self.base_rate = self._interpolate(aim_deg, speed_pct)

    def _interpolate(self, aim_deg: float, speed_pct: float) -> float:
        by_aim: dict[float, list[tuple[float, float]]] = {}
        for (a, s), p in self.table.items():
            by_aim.setdefault(a, []).append((s, p))
        aims = sorted(by_aim)
        at_aim = []
        for a in aims:
            pts = sorted(by_aim[a])
            at_aim.append(float(np.interp(speed_pct, [s for s, _ in pts], [p for _, p in pts])))
        return float(np.interp(aim_deg, aims, at_aim))

    @classmethod
    def from_study_summary(
        cls,
        path: str | Path,
        aim_deg: float = 1.0,
        speed_pct: float = 2.0,
        robot_speed_in_s: float = 0.0,
    ) -> "TableShotModel":
        """Build from a finished study; `path` is the results directory or its summary.csv."""
        p = Path(path)
        rows = load_summary(p.parent if p.is_file() else p)
        moving = min({r["robot_ips"] for r in rows}, key=lambda v: abs(v - robot_speed_in_s))
        acc: dict[tuple[float, float], list[float]] = {}
        for r in rows:
            if r["robot_ips"] == moving:
                acc.setdefault((r["aim_deg"], r["speed_pct"]), []).append(
                    r["pct_scored_of_fired"] / 100.0
                )
        table = {k: float(np.mean(v)) for k, v in acc.items()}
        return cls(table, aim_deg, speed_pct)

    def p_make(
        self,
        distance_in: float,
        off_axis_deg: float,
        ticks_per_s: float,
        rng: np.random.Generator | None = None,
    ) -> float:
        # ticks_per_s is unused: the study fixes the operating point, the LUT sets the speed.
        return min(1.0, max(0.0, self.base_rate * _geometry_factor(distance_in, off_axis_deg)))
