"""
ALEA shot kernel: pure shot physics for BIOBUZZ, nothing else.

One GPU thread = one shot. Each shot starts at the launcher exit and is stepped
until it is CAUGHT by a raised hive cell, hits the floor, hits / clears the
perimeter wall, or runs out of time.

Kept (same math as the Java sim, BioBuzzField.stepBall + Hive):
  - gravity, air drag
  - the hive support frame (1-inch cubes from the field CAD)
  - both hives, latched at rest: cell floors, side walls, roof plates, pivot-side
    end walls, centre beam, and the "caught in the raised cell" test
Left out (cannot change whether a single shot scores):
  - robot code, drivetrain, intake, other balls, hive swinging, flowers, scoring tables
  - floor bounces and wall bounces: a ball that touches the floor or a wall
    (11.6 in tall) can never climb back to a cell mouth 53+ in up, so it is a miss

Runs on an NVIDIA GPU when one is present (e.g. Brev), otherwise on the CPU.
Units: inches, seconds, radians. Field frame = Pedro / sim frame.
"""
import base64, math, os, time
import numpy as np
import warp as wp

HERE = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------- constants
# BioBuzzConfig
FIELD = 141.3
WALL_H = 11.64
G = 386.09
AIR_DRAG = 0.05
WALL_E = 0.45            # restitution off the hive and its frame
R_BALL = 1.4             # pollen
DT = 0.002
MAX_STEPS = 1000         # Java tools: up to 1000 steps (2 s) after launch

PIVOT_H = 43.95
CELL_W = 21.06
CELL_H = 15.79
CELL_CENTER_UP = 5.18
A0, A1 = 9.38, 21.46     # cellBoxAlongMin / Max
HUB_HALF_W, HUB_BOT, HUB_TOP = 0.9, -2.71, 0.87
INNER_WALL = 9.44
IN_HALF_W = 10.0
SIDE_TOP = 6.4
FLOOR_TOP = -1.47
RIDGE = 12.7
ROOF_T = 0.3
REST = math.radians(30)

# hives: pivot x, y; tip direction u = +y; raised side (red: audience -1, blue: rear +1)
HIVE_X = (58.0, 83.5)
HIVE_Y = 70.75
HIVE_UP = (-1, 1)
RED_X, BLUE_X = HIVE_X
RED_UP, BLUE_UP = float(HIVE_UP[0]), float(HIVE_UP[1])

# StarterBot launcher (SimLauncherConfig)
LAUNCH_PITCH = math.radians(72.2)
EXIT_X, EXIT_Z = -6.1, 8.5          # robot frame, out the back
TICKS_TO_INPS = 1.0 / 28 * 2 * math.pi * 1.89 * 0.45   # flywheel ticks/s -> ball in/s


def hive_boxes():
    """The hive's solid parts as boxes in the hive frame: ca, ha, cc, hc, cu, hh, roll."""
    out = []
    ca, ha = (A0 + A1) / 2, (A1 - A0) / 2
    wall_mid = (IN_HALF_W + CELL_W / 2) / 2
    wall_half = (CELL_W / 2 - IN_HALF_W) / 2
    floor_bot = CELL_CENTER_UP - CELL_H / 2
    rise, run = RIDGE - SIDE_TOP, IN_HALF_W + 0.1
    roof_ang, roof_half = math.atan2(rise, run), math.hypot(rise, run) / 2
    roof_up = (RIDGE + SIDE_TOP) / 2 - ROOF_T / 2
    for s in (-1, 1):
        out.append((s * ca, ha, 0, CELL_W / 2, (floor_bot + FLOOR_TOP) / 2, (FLOOR_TOP - floor_bot) / 2, 0))
        for k in (-1, 1):
            out.append((s * ca, ha, k * wall_mid, wall_half, (FLOOR_TOP + SIDE_TOP) / 2, (SIDE_TOP - FLOOR_TOP) / 2, 0))
        for k in (-1, 1):
            out.append((s * ca, ha, k * run / 2, roof_half, roof_up, ROOF_T / 2, -k * roof_ang))
        wa, wh = (A0 + INNER_WALL) / 2, (INNER_WALL - A0) / 2
        out.append((s * wa, wh, 0, CELL_W / 2, (floor_bot + SIDE_TOP) / 2, (SIDE_TOP - floor_bot) / 2, 0))
        out.append((s * wa, wh, 0, run / 2, (SIDE_TOP + RIDGE) / 2, (RIDGE - SIDE_TOP) / 2, 0))
    out.append((0, A0, 0, HUB_HALF_W, (HUB_TOP + HUB_BOT) / 2, (HUB_TOP - HUB_BOT) / 2, 0))
    return np.array(out, dtype=np.float32)


# hive frame cubes (HiveFrame.java)
FX0, FY0, FZ0, FNX, FNY, FNZ = 46, 51, 0, 50, 40, 45


def frame_cubes():
    raw = np.frombuffer(base64.b64decode(open(os.path.join(HERE, "hive_frame.b64")).read()), dtype=np.uint8)
    return np.unpackbits(raw)[: FNX * FNY * FNZ].astype(np.uint8)


# ----------------------------------------------------------------- kernel
@wp.func
def solid(cubes: wp.array(dtype=wp.uint8), x: int, y: int, z: int) -> bool:
    i = x - FX0
    j = y - FY0
    k = z - FZ0
    if i < 0 or j < 0 or k < 0 or i >= FNX or j >= FNY or k >= FNZ:
        return False
    return cubes[(k * FNY + j) * FNX + i] != wp.uint8(0)


@wp.func
def roof_underside(across: float) -> float:
    t = wp.min(1.0, wp.abs(across) / IN_HALF_W)
    return RIDGE - ROOF_T - t * (RIDGE - SIDE_TOP)


@wp.func
def fly(px: float, py: float, pz: float, vx: float, vy: float, vz: float, r: float, e: float,
        boxes: wp.array2d(dtype=float), cubes: wp.array(dtype=wp.uint8)) -> int:
    """Step one ball from the launcher exit until it is decided. 1 = red hive, 2 = blue hive, 0 = miss.
    r = ball radius, e = restitution off the hive and its frame."""
    drag = 1.0 - AIR_DRAG * DT
    out = int(0)
    for step in range(MAX_STEPS):
        vz = vz - G * DT
        vx = vx * drag
        vy = vy * drag
        vz = vz * drag
        prevx = px
        prevy = py
        px = px + vx * DT
        py = py + vy * DT
        pz = pz + vz * DT

        # floor or perimeter wall: can never come back up to a cell -> miss
        if pz < r:
            break
        if pz - r < WALL_H:
            if px < r or py < r or px > FIELD - r or py > FIELD - r:
                break
        if px < 0.0 or py < 0.0 or px > FIELD or py > FIELD:
            break  # over the wall and out

        # hive frame cubes: push out of the deepest, up to 3 passes (HiveFrame.pushOut)
        if px + r >= float(FX0) and px - r <= float(FX0 + FNX) and py + r >= float(FY0) and py - r <= float(FY0 + FNY) and pz - r <= float(FZ0 + FNZ):
            deep = float(0.0)
            dnx = float(0.0)
            dny = float(0.0)
            dnz = float(0.0)
            for p in range(3):
                best = float(0.0)
                bnx = float(0.0)
                bny = float(0.0)
                bnz = float(0.0)
                for cx in range(int(wp.floor(px - r)), int(wp.floor(px + r)) + 1):
                    for cy in range(int(wp.floor(py - r)), int(wp.floor(py + r)) + 1):
                        for cz in range(int(wp.floor(pz - r)), int(wp.floor(pz + r)) + 1):
                            if solid(cubes, cx, cy, cz):
                                qx = wp.clamp(px, float(cx), float(cx + 1))
                                qy = wp.clamp(py, float(cy), float(cy + 1))
                                qz = wp.clamp(pz, float(cz), float(cz + 1))
                                dx = px - qx
                                dy = py - qy
                                dz = pz - qz
                                d = wp.sqrt(dx * dx + dy * dy + dz * dz)
                                if d < r and d > 1.0e-6:
                                    if r - d > best:
                                        best = r - d
                                        bnx = dx / d
                                        bny = dy / d
                                        bnz = dz / d
                if best > 0.0:
                    px = px + bnx * best
                    py = py + bny * best
                    pz = pz + bnz * best
                    if best > deep:
                        deep = best
                        dnx = bnx
                        dny = bny
                        dnz = bnz
            if deep > 0.0:
                vn = vx * dnx + vy * dny + vz * dnz
                if vn < 0.0:
                    vx = vx - (1.0 + e) * vn * dnx
                    vy = vy - (1.0 + e) * vn * dny
                    vz = vz - (1.0 + e) * vn * dnz

        # hives (both latched at rest)
        for hv in range(2):
            hx = float(RED_X)
            up = float(RED_UP)
            if hv == 1:
                hx = float(BLUE_X)
                up = float(BLUE_UP)
            ang = up * REST
            ca = wp.cos(ang)
            sa = wp.sin(ang)
            # u = +y (along), p = -x (across)
            # caught in the raised cell?
            a = py - HIVE_Y
            acr = -(px - hx)
            hh = pz - PIVOT_H
            la = a * ca + hh * sa
            lu = -a * sa + hh * ca
            o = up * la
            if o >= INNER_WALL and o <= A1 - r and wp.abs(acr) <= IN_HALF_W - r and lu >= FLOOR_TOP and lu <= roof_underside(acr) - r:
                out = hv + 1
            if out > 0:
                break
            # bounce off the solid parts
            for bi in range(boxes.shape[0]):
                a = py - HIVE_Y
                acr = -(px - hx)
                hh = pz - PIVOT_H
                la = a * ca + hh * sa
                lu = -a * sa + hh * ca
                cr = wp.cos(boxes[bi, 6])
                sr = wp.sin(boxes[bi, 6])
                oa = la - boxes[bi, 0]
                dc = acr - boxes[bi, 2]
                dh = lu - boxes[bi, 4]
                oc = dc * cr + dh * sr
                oh = -dc * sr + dh * cr
                pa = boxes[bi, 1] + r - wp.abs(oa)
                pc = boxes[bi, 3] + r - wp.abs(oc)
                ph = boxes[bi, 5] + r - wp.abs(oh)
                if pa > 0.0 and pc > 0.0 and ph > 0.0:
                    qa = wp.max(wp.abs(oa) - boxes[bi, 1], 0.0)
                    qc = wp.max(wp.abs(oc) - boxes[bi, 3], 0.0)
                    qh = wp.max(wp.abs(oh) - boxes[bi, 5], 0.0)
                    if qa * qa + qc * qc + qh * qh < r * r:
                        na = float(0.0)
                        nc = float(0.0)
                        nh = float(0.0)
                        pen = float(0.0)
                        if pa <= pc and pa <= ph:
                            na = wp.sign(oa)
                            if oa == 0.0:
                                na = 1.0
                            pen = pa
                        elif pc <= ph:
                            nc = wp.sign(oc)
                            if oc == 0.0:
                                nc = 1.0
                            pen = pc
                        else:
                            nh = wp.sign(oh)
                            if oh == 0.0:
                                nh = 1.0
                            pen = ph
                        lc = nc * cr - nh * sr
                        lh = nc * sr + nh * cr
                        wa = na * ca - lh * sa
                        wh = na * sa + lh * ca
                        nx = -lc
                        ny = wa
                        nz = wh
                        px = px + nx * pen
                        py = py + ny * pen
                        pz = pz + nz * pen
                        vn = vx * nx + vy * ny + vz * nz
                        if vn < 0.0:
                            vx = vx - (1.0 + e) * vn * nx
                            vy = vy - (1.0 + e) * vn * ny
                            vz = vz - (1.0 + e) * vn * nz
        if out > 0:
            break

    return out


@wp.kernel
def shoot(xs: wp.array(dtype=float), ys: wp.array(dtype=float), heading: wp.array(dtype=float),
          speed: wp.array(dtype=float), rvx: wp.array(dtype=float), rvy: wp.array(dtype=float),
          radius: float, e: float,
          boxes: wp.array2d(dtype=float), cubes: wp.array(dtype=wp.uint8), result: wp.array(dtype=int)):
    """Fully specified shots (no randomness): used to check the physics against the Java sim.
    speed = ball exit speed in/s; rvx, rvy = robot velocity in/s (added to the ball, as in Java)."""
    tid = wp.tid()
    h = heading[tid]
    yaw = h + wp.pi
    v = speed[tid]
    px = xs[tid] + EXIT_X * wp.cos(h)
    py = ys[tid] + EXIT_X * wp.sin(h)
    vx = v * wp.cos(LAUNCH_PITCH) * wp.cos(yaw) + rvx[tid]
    vy = v * wp.cos(LAUNCH_PITCH) * wp.sin(yaw) + rvy[tid]
    vz = v * wp.sin(LAUNCH_PITCH)
    result[tid] = fly(px, py, float(EXIT_Z), vx, vy, vz, radius, e, boxes, cubes)


class ShotSim:
    def __init__(self, device=None):
        wp.init()
        self.device = device or ("cuda" if wp.is_cuda_available() else "cpu")
        self.boxes = wp.array(hive_boxes(), dtype=float, device=self.device)
        self.cubes = wp.array(frame_cubes(), dtype=wp.uint8, device=self.device)

    def run(self, x, y, heading, ticks_per_sec, robot_vx=0.0, robot_vy=0.0, radius=R_BALL, restitution=WALL_E):
        """Arrays in, array of 0/1/2 out (miss / red hive / blue hive)."""
        n = len(x)
        a = lambda v: wp.array(np.broadcast_to(np.asarray(v, dtype=np.float32), (n,)).copy(), dtype=float, device=self.device)
        res = wp.zeros(n, dtype=int, device=self.device)
        wp.launch(shoot, dim=n, inputs=[a(x), a(y), a(heading), a(np.asarray(ticks_per_sec) * TICKS_TO_INPS),
                                        a(robot_vx), a(robot_vy), float(radius), float(restitution),
                                        self.boxes, self.cubes, res], device=self.device)
        return res.numpy()


def opening_center(hive=0):
    """World point the Java tools aim at: middle of the raised cell's open end (Hive.openingCenter)."""
    up = HIVE_UP[hive]
    ang = up * REST
    along, h = up * A1, (FLOOR_TOP + RIDGE) / 2 - 1
    a = along * math.cos(ang) - h * math.sin(ang)
    z = along * math.sin(ang) + h * math.cos(ang)
    return HIVE_X[hive], HIVE_Y + a, PIVOT_H + z


def aim_heading(x, y, hive=0):
    """Robot heading that points the (rear-facing) launcher at the cell opening."""
    tx, ty, _ = opening_center(hive)
    return np.arctan2(ty - np.asarray(y), tx - np.asarray(x)) - math.pi
