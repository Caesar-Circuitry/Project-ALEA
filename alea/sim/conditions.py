"""
The study's conditions: every combination of the values below (3 x 3 x 2 x 2 x 2 = 72).
The defaults here match conf/study/brev72.yaml; pass a different dict of lists to change the
study. The FIRST value in each list is the "normal" robot.

  aim_deg    : aim error, 1 standard deviation, degrees (auto-aim settles within 1 deg)
  speed_pct  : flywheel speed error at the shot, 1 standard deviation, % (PIDF, battery)
  robot_ips  : robot still moving when it shoots, inches/second, random direction
  ball_in    : pollen diameter, inches (2.8 = game manual)
  bounce     : how bouncy the ball is off the hive (restitution; 0.45 = sim default)
"""

import itertools

AIM_DEG = [1.0, 0.5, 2.0]
SPEED_PCT = [2.0, 1.0, 3.0]
ROBOT_IPS = [0.0, 10.0]
BALL_IN = [2.8, 2.9]
BOUNCE = [0.45, 0.60]

DEFAULTS = dict(
    aim_deg=AIM_DEG, speed_pct=SPEED_PCT, robot_ips=ROBOT_IPS, ball_in=BALL_IN, bounce=BOUNCE
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
