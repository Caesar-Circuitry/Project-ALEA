"""
ALEA robustness study kernel: random TeleOp-style shots, done the way the robot code does them.

For each shot (one GPU thread):
  1. Pick a random robot position on the field (rejecting spots where the robot would sit on
     the hive frame's base rails).
  2. Do what aimAssist + launchLUT do: aim at the RED_AUDIENCE cell mouth, distance = centre
     to mouth minus 6.1 in, LUT speed for that distance, and only fire when the LUT covers the
     distance and the robot is within 80 deg of straight out of the cell.
  3. Add this condition's errors: aim error, flywheel speed error, robot still moving.
  4. Fly the ball with shotsim.fly (the physics checked against the Java sim).
  5. Count tries / fired / scored in a 2-inch grid cell on the GPU (no per-shot data is kept,
     so a big run needs almost no memory or disk).
"""
import math
import numpy as np
import warp as wp
from alea.sim.shotsim import (fly, frame_cubes, hive_boxes, LAUNCH_PITCH, EXIT_X, EXIT_Z, TICKS_TO_INPS,
                     FIELD, FX0, FY0, FNX, FNY)

# ---- robot code (constants.java / aimAssist.java), RED_AUDIENCE target ----
TARGET_X, TARGET_Y, FACES_Y = 58.0, 54.47, -1.0
EXIT_BEHIND = 6.1
MAX_OFF_AXIS = math.radians(80.0)
LUT_DISTANCE_IN = [24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76, 80]
LUT_TICKS_PER_SEC = [1180, 1110, 1100, 1100, 1120, 1140, 1160, 1180, 1200, 1230, 1260, 1290, 1310, 1340, 1360]

# ---- where the robot can be ----
ROBOT_HALF = 8.9                 # StarterBot is 17.8 in square (treated as axis-aligned here)
X_MIN, X_MAX = ROBOT_HALF, FIELD - ROBOT_HALF
Y_MIN, Y_MAX = ROBOT_HALF, 70.75  # our half of the field (audience side)
CELL = 2.0                        # heat-map cell size, inches
GX, GY = int(math.ceil(FIELD / CELL)), int(math.ceil(Y_MAX / CELL))
ROBOT_HEIGHT = 12.69
DBG_COLS = 12   # x y target_heading distance lut_tps can_fire heading tps robot_vx robot_vy result rejects


def frame_footprint():
    """Top view of frame cubes lower than the robot is tall (the base rails), [FNY, FNX] uint8."""
    c = frame_cubes().reshape(-1, FNY, FNX)
    return c[: int(math.ceil(ROBOT_HEIGHT))].any(0).astype(np.uint8)


@wp.func
def blocked(foot: wp.array2d(dtype=wp.uint8), x: float, y: float) -> bool:
    """Would a robot centred here overlap the hive frame's base rails?"""
    x0 = int(wp.floor(x - ROBOT_HALF)) - FX0
    x1 = int(wp.floor(x + ROBOT_HALF)) - FX0
    y0 = int(wp.floor(y - ROBOT_HALF)) - FY0
    y1 = int(wp.floor(y + ROBOT_HALF)) - FY0
    hit = bool(False)
    for j in range(wp.max(y0, 0), wp.min(y1, FNY - 1) + 1):
        for i in range(wp.max(x0, 0), wp.min(x1, FNX - 1) + 1):
            if foot[j, i] != wp.uint8(0):
                hit = True
    return hit


@wp.func
def lut_speed(d: float, ld: wp.array(dtype=float), lt: wp.array(dtype=float)) -> float:
    """launchLUT.ticksPerSec: linear between rows, clamped at the ends."""
    n = ld.shape[0]
    if d <= ld[0]:
        return lt[0]
    if d >= ld[n - 1]:
        return lt[n - 1]
    i = int(1)
    while ld[i] < d:
        i = i + 1
    t = (d - ld[i - 1]) / (ld[i] - ld[i - 1])
    return lt[i - 1] + t * (lt[i] - lt[i - 1])


@wp.kernel
def study(seed: int, offset: int, aim_sigma: float, speed_sigma: float, robot_speed: float,
          radius: float, e: float,
          ld: wp.array(dtype=float), lt: wp.array(dtype=float), foot: wp.array2d(dtype=wp.uint8),
          boxes: wp.array2d(dtype=float), cubes: wp.array(dtype=wp.uint8),
          tries: wp.array2d(dtype=int), fired: wp.array2d(dtype=int), hits: wp.array2d(dtype=int),
          debug: int, dbg: wp.array2d(dtype=float)):
    tid = wp.tid()
    rng = wp.rand_init(seed, offset + tid)

    # 1. a random place the robot can actually be
    x = wp.randf(rng, X_MIN, X_MAX)
    y = wp.randf(rng, Y_MIN, Y_MAX)
    rejects = int(0)
    while blocked(foot, x, y):
        x = wp.randf(rng, X_MIN, X_MAX)
        y = wp.randf(rng, Y_MIN, Y_MAX)
        rejects = rejects + 1
    gx = wp.min(int(x / CELL), GX - 1)
    gy = wp.min(int(y / CELL), GY - 1)
    wp.atomic_add(tries, gx, gy, 1)

    # 2. aimAssist.update
    dx = TARGET_X - x
    dy = TARGET_Y - y
    target_heading = wp.atan2(dy, dx) + wp.pi
    dist = wp.sqrt(dx * dx + dy * dy) - EXIT_BEHIND
    tps0 = lut_speed(dist, ld, lt)
    off = wp.atan2(wp.abs(dx), -dy * FACES_Y)
    can = dist >= ld[0] and dist <= ld[ld.shape[0] - 1] and off <= MAX_OFF_AXIS

    heading = target_heading
    tps = tps0
    rvx = float(0.0)
    rvy = float(0.0)
    result = int(-1)
    if can:
        wp.atomic_add(fired, gx, gy, 1)
        # 3. this condition's errors
        heading = target_heading + aim_sigma * wp.randn(rng)
        tps = tps0 * (1.0 + speed_sigma * wp.randn(rng))
        ang = wp.randf(rng, 0.0, 2.0 * wp.pi)
        rvx = robot_speed * wp.cos(ang)
        rvy = robot_speed * wp.sin(ang)
        # 4. the shot (same launch as BioBuzzField.launch, launcher out the back)
        v = tps * TICKS_TO_INPS
        yaw = heading + wp.pi
        px = x + EXIT_X * wp.cos(heading)
        py = y + EXIT_X * wp.sin(heading)
        bvx = v * wp.cos(LAUNCH_PITCH) * wp.cos(yaw) + rvx
        bvy = v * wp.cos(LAUNCH_PITCH) * wp.sin(yaw) + rvy
        bvz = v * wp.sin(LAUNCH_PITCH)
        result = fly(px, py, float(EXIT_Z), bvx, bvy, bvz, radius, e, boxes, cubes)
        if result == 1:
            wp.atomic_add(hits, gx, gy, 1)

    if debug != 0:
        dbg[tid, 0] = x
        dbg[tid, 1] = y
        dbg[tid, 2] = target_heading
        dbg[tid, 3] = dist
        dbg[tid, 4] = tps0
        dbg[tid, 5] = wp.where(can, 1.0, 0.0)
        dbg[tid, 6] = heading
        dbg[tid, 7] = tps
        dbg[tid, 8] = rvx
        dbg[tid, 9] = rvy
        dbg[tid, 10] = float(result)
        dbg[tid, 11] = float(rejects)


class Study:
    def __init__(self, device=None):
        wp.init()
        self.device = device or ("cuda" if wp.is_cuda_available() else "cpu")
        d = self.device
        self.boxes = wp.array(hive_boxes(), dtype=float, device=d)
        self.cubes = wp.array(frame_cubes(), dtype=wp.uint8, device=d)
        self.foot = wp.array(frame_footprint(), dtype=wp.uint8, device=d)
        self.ld = wp.array(np.array(LUT_DISTANCE_IN, np.float32), dtype=float, device=d)
        self.lt = wp.array(np.array(LUT_TICKS_PER_SEC, np.float32), dtype=float, device=d)
        self.nodbg = wp.zeros((1, DBG_COLS), dtype=float, device=d)

    def run(self, cond, shots, seed, batch=1_000_000, debug=False):
        """One condition. Returns tries, fired, hits as [GX, GY] int arrays (and per-shot debug rows)."""
        d = self.device
        tries = wp.zeros((GX, GY), dtype=int, device=d)
        fired = wp.zeros((GX, GY), dtype=int, device=d)
        hits = wp.zeros((GX, GY), dtype=int, device=d)
        dbg_all = []
        done = 0
        while done < shots:
            n = min(batch, shots - done)
            dbg = wp.zeros((n, DBG_COLS), dtype=float, device=d) if debug else self.nodbg
            wp.launch(study, dim=n, device=d, inputs=[
                int(seed), int(done), math.radians(cond["aim_deg"]), cond["speed_pct"] / 100.0,
                float(cond["robot_ips"]), cond["ball_in"] / 2.0, float(cond["bounce"]),
                self.ld, self.lt, self.foot, self.boxes, self.cubes, tries, fired, hits,
                int(debug), dbg])
            if debug:
                dbg_all.append(dbg.numpy())
            done += n
        out = tries.numpy(), fired.numpy(), hits.numpy()
        return out + ((np.concatenate(dbg_all),) if debug else ())
