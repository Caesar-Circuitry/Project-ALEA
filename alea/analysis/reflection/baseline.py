"""Sim baseline: expected make probability against launch distance, and expected points."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from alea.analysis.reflection.timeline import MatchTimeline
from alea.sim.results import SCORE_KEY, load_summary

# placeholder: Competition Manual Table 10-2; game point values belong in alea/game via a
# physics-reviewed PR
BALL_POINTS = 2  # a made ball: pollen or nectar in the up cell at the end of the match
TIP_POINTS = 20

_PLACEHOLDER_DIST_IN = tuple(range(24, 84, 4))


def _placeholder_p(dist_in: float) -> float:
    # smooth logistic: ~0.79 at 24 in, ~0.44 at 60 in, ~0.20 at 80 in. Not simulated.
    return 0.15 + 0.65 / (1.0 + math.exp((dist_in - 58.0) / 9.0))


@dataclass(frozen=True)
class Baseline:
    dist_in: tuple[float, ...]
    p_make: tuple[float, ...]
    source: str  # "measured" only when the study resolved distance; else "inferred"
    note: str

    def make_probability(self, dist_in: float) -> float:
        """Interpolated make probability; flat beyond the ends."""
        return float(np.interp(dist_in, self.dist_in, self.p_make))

    @property
    def mean_p_make(self) -> float:
        return float(np.mean(self.p_make))

    @classmethod
    def placeholder(cls) -> Baseline:
        return cls(
            _PLACEHOLDER_DIST_IN,
            tuple(_placeholder_p(d) for d in _PLACEHOLDER_DIST_IN),
            "inferred",
            "placeholder logistic curve, not from a simulation",
        )

    @classmethod
    def from_summary(cls, path: str | Path) -> Baseline:
        """From a finished study. `path` is the study directory or its summary.csv.

        The study samples random spots, so its summary has one score rate per condition and no
        distance. The level is the nominal condition (lowest id, the normal robot) and the
        distance shape stays the placeholder shape rescaled to that mean: "inferred". If the rows
        carry a `dist_in` column, the make rate per distance is used directly: "measured".
        """
        p = Path(path)
        rows = load_summary(p.parent if p.is_file() else p)
        if rows and "dist_in" in rows[0]:
            by_d: dict[float, list[float]] = {}
            for r in rows:
                by_d.setdefault(float(r["dist_in"]), []).append(r[SCORE_KEY] / 100.0)
            ds = sorted(by_d)
            return cls(
                tuple(ds),
                tuple(float(np.mean(by_d[d])) for d in ds),
                "measured",
                f"shot study, {len(rows)} rows, per distance",
            )
        nominal = min(rows, key=lambda r: r["id"])
        level = nominal[SCORE_KEY] / 100.0
        shape = np.array([_placeholder_p(d) for d in _PLACEHOLDER_DIST_IN])
        scaled = np.clip(shape * level / shape.mean(), 0.0, 1.0)
        return cls(
            _PLACEHOLDER_DIST_IN,
            tuple(float(x) for x in scaled),
            "inferred",
            f"level from study condition {nominal['id']} ({100 * level:.1f}% of fired shots "
            "scored); distance shape is the placeholder shape",
        )


@dataclass(frozen=True)
class ExpectedPoints:
    expected_made_balls: float
    ball_points: float
    tips_observed: int | None
    tip_points: float | None
    expected_total_pts: float
    observed_score_pts: float | None
    points_vs_expected_pts: float | None
    launches_without_distance: int
    source: str


def expected_points(timeline: MatchTimeline, baseline: Baseline) -> ExpectedPoints:
    """Sum of make probabilities x 2 points, plus observed tips x 20, against the overlay score."""
    probs, missing = [], 0
    for launch in timeline.launches:
        if launch.distance_in is None:
            missing += 1
            probs.append(baseline.mean_p_make)
        else:
            probs.append(baseline.make_probability(launch.distance_in))
    made = float(sum(probs))
    tips = len(timeline.tip_events) if timeline.overlay_present else None
    tip_pts = None if tips is None else float(tips * TIP_POINTS)
    total = made * BALL_POINTS + (tip_pts or 0.0)
    observed = timeline.final_score_pts
    inferred = baseline.source == "inferred" or missing > 0
    return ExpectedPoints(
        expected_made_balls=made,
        ball_points=made * BALL_POINTS,
        tips_observed=tips,
        tip_points=tip_pts,
        expected_total_pts=total,
        observed_score_pts=observed,
        points_vs_expected_pts=None if observed is None else observed - total,
        launches_without_distance=missing,
        source="inferred" if inferred else "measured",
    )
