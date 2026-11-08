"""Field mask and top-down warp on a synthetic camera (roadmap phase 2, field extraction)."""

import numpy as np
import pytest

pytest.importorskip("cv2")
import cv2

from alea.game import biobuzz as g
from alea.video.field.fieldmask import (
    floor_mask,
    floor_polygon_px,
    overlay_band_mask,
    prism_mask,
)
from alea.video.field.synth import ROBOT_BGR, render_frame
from alea.video.field.topdown import (
    TopDownGrid,
    draw_field_outline,
    field_to_topdown_px,
    topdown_to_field_in,
    warp_topdown,
)
from tests.test_video_field_scene import CAMERA, SHAPE, H, W


def test_floor_polygon_is_convex_quad_inside_image() -> None:
    poly = floor_polygon_px(CAMERA, SHAPE)
    assert poly.shape == (4, 2)
    assert poly[:, 0].min() >= 0 and poly[:, 0].max() <= W
    assert poly[:, 1].min() >= 0 and poly[:, 1].max() <= H
    hull = cv2.convexHull(poly.astype(np.float32))
    assert len(hull) == 4
    assert cv2.isContourConvex(poly.astype(np.float32).reshape(-1, 1, 2))
    bigger = floor_polygon_px(CAMERA, SHAPE, margin_in=10)
    assert cv2.contourArea(bigger.astype(np.float32)) > cv2.contourArea(poly.astype(np.float32))


def test_prism_mask_contains_floor_mask_and_exclusions() -> None:
    floor = floor_mask(CAMERA, SHAPE)
    prism = prism_mask(CAMERA, SHAPE)
    assert prism.dtype == np.uint8 and floor.dtype == np.uint8
    assert np.all(prism[floor > 0] > 0)
    assert (prism > 0).sum() > (floor > 0).sum()
    ex = prism_mask(CAMERA, SHAPE, exclude_rects_px=[(300, 150, 340, 200)])
    assert ex[170, 320] == 0 and prism[170, 320] > 0


def test_overlay_band() -> None:
    band = overlay_band_mask(SHAPE, 40)
    assert band[39].max() == 0 and band[40].min() == 255


def test_grid_round_trip() -> None:
    grid = TopDownGrid()
    for x, y in [(0.0, 0.0), (70.0, 12.5), (141.3, 141.3)]:
        u, v = field_to_topdown_px(x, y, grid)
        assert topdown_to_field_in(u, v, grid) == pytest.approx((x, y))


def test_warp_places_robot_and_ball_within_3_in() -> None:
    grid = TopDownGrid()
    robot, ball = (50.0, 80.0), (100.0, 60.0)
    frame = render_frame(CAMERA, SHAPE, robot, [ball])
    td = warp_topdown(frame, CAMERA, grid)
    assert td.shape[:2] == (grid.size_px, grid.size_px)

    robot_px = np.all(np.abs(td.astype(int) - ROBOT_BGR) < 12, axis=2)
    vs, us = np.nonzero(robot_px)
    assert len(us) > 100
    x_c, _ = topdown_to_field_in(us.mean(), vs.mean(), grid)
    assert abs(x_c - robot[0]) < 3
    # the body smears away from the camera; its near edge is the contact line y - 9
    near_y = topdown_to_field_in(0, float(vs.max()), grid)[1]
    assert abs(near_y - (robot[1] - 9)) < 3

    hsv = cv2.cvtColor(td, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, (18, 110, 150), (34, 255, 255))
    vs, us = np.nonzero(yellow)
    bx, by = topdown_to_field_in(us.mean(), vs.mean(), grid)
    assert np.hypot(bx - ball[0], by - ball[1]) < 3


def test_outline_aligns_with_floor_edge() -> None:
    grid = TopDownGrid()
    td = warp_topdown(render_frame(CAMERA, SHAPE), CAMERA, grid)
    out = draw_field_outline(td, grid, color=(0, 0, 255))
    red = np.all(out == (0, 0, 255), axis=2)
    assert red.sum() > 4 * 140 * grid.px_per_in * 0.9
    # inside the outline the floor is grey tiles, just outside it is dark wall/zero
    u0, v0 = field_to_topdown_px(70, 70, grid)
    assert td[int(v0), int(u0)].min() > 100
    u1, v1 = field_to_topdown_px(-3, 70, grid)
    assert td[int(v1), int(u1)].max() < 80
    assert g.FIELD_SIZE_IN > 0
