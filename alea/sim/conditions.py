"""
The study's conditions: every combination of the values below (3 x 3 x 2 x 2 x 2 = 72).
The defaults here match conf/study/brev72.yaml; pass a different dict of lists to change the
study. The FIRST value in each list is the "normal" robot.

  aim_deg    : aim error, 1 standard deviation, degrees (auto-aim settles within 1 deg)
  speed_pct  : flywheel speed error at the shot, 1 standard deviation, % (PIDF, battery)
  robot_ips  : robot still moving when it shoots, inches/second, random direction
  ball_in    : pollen diameter, inches (first value = game manual, alea.game.biobuzz)
  bounce     : how bouncy the ball is off the hive (restitution; first value = sim default)

The key `robot_ips` keeps its name because the frozen study.py reads `cond["robot_ips"]`.
tests/test_conditions.py checks these defaults against conf/study/brev72.yaml.
"""

import itertools

from alea.game.biobuzz import HIVE_RESTITUTION, POLLEN_RADIUS_IN

AIM_DEG = [1.0, 0.5, 2.0]
SPEED_PCT = [2.0, 1.0, 3.0]
ROBOT_SPEED_IN_S = [0.0, 10.0]
BALL_DIAMETER_IN = [2 * POLLEN_RADIUS_IN, 2.9]
BOUNCE = [HIVE_RESTITUTION, 0.60]

DEFAULTS = dict(
    aim_deg=AIM_DEG,
    speed_pct=SPEED_PCT,
    robot_ips=ROBOT_SPEED_IN_S,
    ball_in=BALL_DIAMETER_IN,
    bounce=BOUNCE,
)


def all_conditions(grid=None):
    unknown = sorted(set(grid or {}) - set(DEFAULTS))
    if unknown:
        raise ValueError(f"unknown condition key(s) {unknown}; valid keys: {sorted(DEFAULTS)}")
    g = {**DEFAULTS, **(grid or {})}
    out = []
    for a, s, r, b, e in itertools.product(
        g["aim_deg"], g["speed_pct"], g["robot_ips"], g["ball_in"], g["bounce"]
    ):
        out.append(dict(aim_deg=a, speed_pct=s, robot_ips=r, ball_in=b, bounce=e))
    for i, c in enumerate(out):
        c["id"] = i
    return out
