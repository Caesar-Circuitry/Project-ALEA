"""`python -m alea.video` command line: review, info, validate, export-csv (roadmap phase 2)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from alea.video.clicklog import ClickLogError, ShotObservation, export_csv, read_jsonl


def _cmd_review(args: argparse.Namespace) -> int:
    from alea.video.review import ReviewError, run_review

    video = Path(args.video)
    if not video.is_file():
        print(f"error: {video} does not exist", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else video.with_suffix(".shots.jsonl")
    fields = {
        "operator": args.operator,
        "event_code": args.event,
        "match_label": args.match,
        "alliance": args.alliance,
        "team_number": args.team,
        "click_z_in": args.click_z_in,
    }
    try:
        n = run_review(
            video,
            out,
            fields,
            Path(args.calibration) if args.calibration else None,
            args.camera_setup,
            args.start_frame,
        )
    except ReviewError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{n} records in {out}")
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    from alea.video.frames import VideoError, VideoReader

    try:
        with VideoReader(Path(args.video)) as reader:
            info = reader.info
            print(f"{info.width_px}x{info.height_px} px, {info.frame_count} frames")
            print(f"nominal fps {info.fps_nominal:.3f}")
            stats = reader.timestamp_stats()
            print(f"median fps {stats.fps_median:.3f}, duplicates {stats.n_duplicate}")
            print("variable frame rate: " + ("yes" if stats.variable_frame_rate else "no"))
    except VideoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def _read(path: Path) -> list[ShotObservation] | None:
    try:
        return read_jsonl(path)
    except (OSError, ClickLogError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _cmd_validate(args: argparse.Namespace) -> int:
    records = _read(Path(args.shots))
    if records is None:
        return 2
    print(f"{len(records)} valid records")
    return 0


def _cmd_export_csv(args: argparse.Namespace) -> int:
    records = _read(Path(args.shots))
    if records is None:
        return 2
    launches, tracks = export_csv(records, Path(args.out_dir))
    print(f"wrote {launches} and {tracks}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m alea.video", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    rv = sub.add_parser("review", help="click through a match video and log shots")
    rv.add_argument("video")
    rv.add_argument(
        "--calibration", help="the video's one calibration.json (referenced, not embedded)"
    )
    rv.add_argument("--camera-setup", help="camera placement id (one per event or video)")
    rv.add_argument("--out", help="shots.jsonl to append to (default: next to the video)")
    rv.add_argument("--operator", default="")
    rv.add_argument("--event", help="event code, e.g. USALTX")
    rv.add_argument("--match", help="match label, e.g. Q12")
    rv.add_argument("--alliance", choices=("red", "blue"))
    rv.add_argument("--team", type=int)
    rv.add_argument(
        "--click-z-in",
        type=float,
        default=16.0,
        help="robot top-plate height in inches: placeholder default, measure the StarterBot "
        "top-plate height",
    )
    rv.add_argument("--start-frame", type=int, default=0)
    rv.set_defaults(func=_cmd_review)

    inf = sub.add_parser("info", help="print video size, frame count and timestamp stats")
    inf.add_argument("video")
    inf.set_defaults(func=_cmd_info)

    val = sub.add_parser("validate", help="check a shots.jsonl against the schema")
    val.add_argument("shots")
    val.set_defaults(func=_cmd_validate)

    exp = sub.add_parser("export-csv", help="write launches.csv and track_points.csv")
    exp.add_argument("shots")
    exp.add_argument("--out-dir", default=".")
    exp.set_defaults(func=_cmd_export_csv)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
