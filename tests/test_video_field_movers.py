"""Background, static check and movers on a synthetic sequence (field extraction)."""

import os
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("cv2")
import cv2

from alea.video.field.background import (
    camera_static_check,
    median_background,
    windowed_median_background,
)
from alea.video.field.fieldmask import floor_mask, prism_mask
from alea.video.field.movers import (
    ClassifierConfig,
    MoverRecord,
    ball_position_in,
    blobs,
    classify_blob,
    floor_position_in,
    foreground_mask,
    occupancy_fraction,
    read_movers_csv,
    write_movers_csv,
    yellow_ball_candidates,
)
from alea.video.field.synth import render_frame, render_sequence
from alea.video.field.topdown import TopDownGrid, warp_topdown
from tests.test_video_field_scene import CAMERA, SHAPE

PATH = [(30.0, 85.0), (115.0, 85.0)]
BALLS = [(30.0, 30.0), (110.0, 30.0), (70.0, 45.0)]
PERSON = (-12.0, 40.0)  # just outside the left edge
N = 24


@pytest.fixture(scope="module")
def sequence():
    return render_sequence(CAMERA, PATH, BALLS, N, SHAPE, person_xy_in=PERSON)


def test_median_background_removes_moving_robot() -> None:
    frames, _ = render_sequence(CAMERA, PATH, BALLS, N, SHAPE)
    bg = median_background(iter(frames), max_samples=12)
    empty = render_frame(CAMERA, SHAPE, None, BALLS)
    assert np.abs(bg.astype(int) - empty.astype(int)).sum(axis=2).max() < 10
    # the reservoir bound holds and the result is deterministic
    again = median_background(iter(frames), max_samples=12)
    assert np.array_equal(bg, again)


def test_windowed_background_follows_a_parked_robot() -> None:
    parked, _ = render_sequence(CAMERA, [(70.0, 85.0), (70.0, 85.0)], BALLS, 8, SHAPE)
    empty = render_sequence(CAMERA, None, BALLS, 8, SHAPE)[0]
    wins = list(windowed_median_background(empty + parked, window=8, step=8))
    assert [(w.start, w.stop) for w in wins] == [(0, 8), (8, 16)]
    assert np.array_equal(wins[1].image, parked[0])  # absorbed, as documented
    with pytest.raises(ValueError):
        list(windowed_median_background(empty, window=0, step=1))


def test_static_check() -> None:
    frames, _ = render_sequence(CAMERA, None, BALLS, 3, SHAPE, noise_sigma=2.0)
    rows = (120, 200)
    same = camera_static_check(frames[1:], frames[0], rows)
    assert same.static and same.max_dx_px < 0.5
    m = np.array([[1.0, 0.0, 5.0], [0.0, 1.0, 0.0]])
    shifted = np.asarray(
        cv2.warpAffine(frames[0], m, (SHAPE[1], SHAPE[0]), borderMode=cv2.BORDER_REPLICATE),
        dtype=np.uint8,
    )
    moved = camera_static_check([shifted], frames[0], rows)
    assert not moved.static and 3.5 < moved.max_dx_px < 6.5


def test_foreground_blobs_positions_and_classes(sequence) -> None:
    frames, truth = sequence
    empty = render_frame(CAMERA, SHAPE, None, BALLS)  # pre-match, no robot or person
    region = prism_mask(CAMERA, SHAPE, margin_in=24.0)
    floor = floor_mask(CAMERA, SHAPE)
    config = ClassifierConfig()
    errs, ball_errs, persons = [], [], 0
    for k in range(3, N - 3, 3):
        fg = foreground_mask(frames[k], empty, region_mask=region, min_area_px=100)
        found = blobs(fg)
        kinds = [classify_blob(b, CAMERA, SHAPE, config) for b in found]
        assert kinds.count("robot") == 1 and kinds.count("person") == 1, kinds
        persons += 1
        robot = found[kinds.index("robot")]
        x, y = floor_position_in(robot, CAMERA)
        tx, ty = truth[k].robot_contact_in
        errs.append(np.hypot(x - tx, y - ty))
        cands = yellow_ball_candidates(frames[k], floor)
        assert len(cands) == len(BALLS)
        for bx, by in BALLS:
            d = min(np.hypot(*(np.array(ball_position_in(c, CAMERA)) - (bx, by))) for c in cands)
            ball_errs.append(d)
    print(f"robot contact error max {max(errs):.2f} in, ball error max {max(ball_errs):.2f} in")
    assert max(errs) < 4.0
    assert max(ball_errs) < 2.0
    assert persons > 0


def test_occupancy_higher_along_robot_path(sequence) -> None:
    frames, _ = sequence
    grid = TopDownGrid(px_per_in=2.0)
    empty = render_frame(CAMERA, SHAPE, None, BALLS)
    region = prism_mask(CAMERA, SHAPE, margin_in=24.0)
    tds = [
        warp_topdown(
            foreground_mask(f, empty, region_mask=region, min_area_px=100),
            CAMERA,
            grid,
            nearest=True,
        )
        for f in frames
    ]
    occ = occupancy_fraction(tds, grid)
    from alea.video.field.topdown import field_to_topdown_px as f2t

    on = f2t(70.0, 80.0, grid)  # on the path
    off = f2t(70.0, 20.0, grid)
    assert occ[int(on[1]), int(on[0])] > occ[int(off[1]), int(off[0])]
    assert occ.max() <= 1.0


def test_csv_round_trip(tmp_path: Path) -> None:
    recs = [
        MoverRecord(3, 0.6, "robot", 12.5, 40.25, (10, 20, 30, 40), 900, 0.5, "a note"),
        MoverRecord(4, 0.8, "person", float("nan"), float("nan"), (0, 0, 5, 5), 25, 0.1),
    ]
    p = tmp_path / "m.csv"
    write_movers_csv(recs, p)
    back = read_movers_csv(p)
    assert back[0] == recs[0]
    assert back[1].kind == "person" and np.isnan(back[1].x_in)


@pytest.mark.skipif(not os.environ.get("ALEA_LOCAL_CLIP"), reason="ALEA_LOCAL_CLIP not set")
def test_local_clip_smoke() -> None:
    from alea.video.field.__main__ import _iter_frames

    path = Path(os.environ["ALEA_LOCAL_CLIP"])
    frame = next(_iter_frames(path))[2]
    assert frame.ndim == 3
