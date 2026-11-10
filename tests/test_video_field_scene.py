"""Shared synthetic scene for the field-extraction tests (no real footage)."""

import numpy as np

from alea.game import biobuzz as g
from alea.video.geometry import Camera

W, H = 640, 360
F = 560.0
CENTRE = np.array([g.FIELD_SIZE_IN / 2, g.FIELD_SIZE_IN / 2, 0.0])


def look_at(position, target, f=F) -> Camera:
    pos = np.asarray(position, float)
    z = np.asarray(target, float) - pos
    z /= np.linalg.norm(z)
    x = np.cross(z, [0, 0, 1.0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return Camera(f, np.stack([x, y, z]), pos, W / 2, H / 2)


CAMERA = look_at([70, -170, 150], CENTRE)
SHAPE = (H, W)
