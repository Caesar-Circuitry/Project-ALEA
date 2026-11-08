"""Command line: background, movers and static-check for a static-camera video.

    python -m alea.video.field background VIDEO --calibration cal.json --out bg.png
    python -m alea.video.field movers VIDEO --calibration cal.json --background bg.png \
        --out movers.csv [--topdown-dir DIR]
    python -m alea.video.field static-check VIDEO --out report.json

Output images are for the operator only; keep them out of git.
"""

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from alea.video.calibration import read_calibration
from alea.video.field.background import camera_static_check, median_background
from alea.video.field.fieldmask import floor_mask, prism_mask
from alea.video.field.movers import (
    ClassifierConfig,
    MoverRecord,
    ball_position_in,
    blobs,
    blobs_to_records,
    foreground_mask,
    write_movers_csv,
    yellow_ball_candidates,
)
from alea.video.field.topdown import TopDownGrid, warp_topdown
from alea.video.geometry import Camera


def _iter_frames(path: Path, every: int = 1) -> Iterator[tuple[int, float, NDArray[np.uint8]]]:
    """Yield (frame_index, t_s, BGR frame) for every `every`-th frame.

    Private stand-in: switch to `alea.video.frames.VideoReader` when the click-log branch merges.
    """
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise SystemExit(f"cannot open video {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    try:
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                return
            if i % every == 0:
                yield i, i / fps, np.asarray(frame, dtype=np.uint8)
            i += 1
    finally:
        cap.release()


def _camera(path: Path) -> Camera:
    cal = read_calibration(path)
    if cal.camera is None:
        raise SystemExit("calibration has no pinhole camera (floor-only homography)")
    return cal.camera


def _cmd_background(a: argparse.Namespace) -> None:
    import cv2

    cam = _camera(a.calibration)
    first = next(_iter_frames(a.video))[2]
    mask = prism_mask(cam, first.shape, margin_in=a.margin_in)
    bg = median_background(
        (f for _, _, f in _iter_frames(a.video, a.every)), max_samples=a.max_samples
    )
    cv2.imwrite(str(a.out), bg)
    print(f"wrote {a.out} (field mask covers {int((mask > 0).sum())} px)")


def _cmd_movers(a: argparse.Namespace) -> None:
    import cv2

    cam = _camera(a.calibration)
    bg_read = cv2.imread(str(a.background))
    if bg_read is None:
        raise SystemExit(f"cannot read background {a.background}")
    bg = np.asarray(bg_read, dtype=np.uint8)
    shape = bg.shape
    region = prism_mask(cam, shape, margin_in=a.margin_in)
    if a.overlay_top_px:
        region[: a.overlay_top_px] = 0
    floor = floor_mask(cam, shape)
    config = ClassifierConfig()
    grid = TopDownGrid()
    records: list[MoverRecord] = []
    for i, t_s, frame in _iter_frames(a.video, a.every):
        fg = foreground_mask(frame, bg, region_mask=region)
        records += blobs_to_records(i, t_s, blobs(fg), cam, shape, config)
        for c in yellow_ball_candidates(frame, floor):
            x_in, y_in = ball_position_in(c, cam)
            bbox = (int(c.u_px - c.radius_px), int(c.v_px - c.radius_px), 0, 0)
            records.append(MoverRecord(i, t_s, "ball", x_in, y_in, bbox, c.area_px, 0.5, "yellow"))
        if a.topdown_dir is not None:
            a.topdown_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(a.topdown_dir / f"td_{i:06d}.png"), warp_topdown(frame, cam, grid))
    write_movers_csv(records, a.out)
    print(f"wrote {len(records)} records to {a.out}")


def _cmd_static(a: argparse.Namespace) -> None:
    frames = _iter_frames(a.video, a.every)
    _, _, ref = next(frames)
    default_rows = (ref.shape[0] // 3, ref.shape[0] // 2)
    rows = (a.strip_rows[0], a.strip_rows[1]) if a.strip_rows else default_rows
    rep = camera_static_check((f for _, _, f in frames), ref, rows, a.threshold_px)
    report = {
        "max_dx_px": rep.max_dx_px,
        "max_dy_px": rep.max_dy_px,
        "threshold_px": rep.threshold_px,
        "n_frames": rep.n_frames,
        "strip_rows": list(rows),
        "static": rep.static,
    }
    a.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m alea.video.field")
    sub = p.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("video", type=Path)
    common.add_argument("--every", type=int, default=1, help="use every N-th frame")
    b = sub.add_parser("background", parents=[common])
    b.add_argument("--calibration", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--max-samples", type=int, default=64)
    b.add_argument("--margin-in", type=float, default=12.0)
    b.set_defaults(fn=_cmd_background)
    m = sub.add_parser("movers", parents=[common])
    m.add_argument("--calibration", type=Path, required=True)
    m.add_argument("--background", type=Path, required=True)
    m.add_argument("--out", type=Path, required=True)
    m.add_argument("--topdown-dir", type=Path, default=None)
    m.add_argument("--margin-in", type=float, default=12.0)
    m.add_argument("--overlay-top-px", type=int, default=0)
    m.set_defaults(fn=_cmd_movers)
    s = sub.add_parser("static-check", parents=[common])
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--strip-rows", type=int, nargs=2, default=None)
    s.add_argument("--threshold-px", type=float, default=2.0)
    s.set_defaults(fn=_cmd_static)
    a = p.parse_args(argv)
    a.fn(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
