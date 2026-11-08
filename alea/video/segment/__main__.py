"""``python -m alea.video.segment`` : inspect, validate and bridge match-segment files."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from alea.video.segment.bridge import segments_to_matches_csv
from alea.video.segment.schedule import (
    ScheduleError,
    load_ftcscout_matches,
    match_segments_to_schedule,
)
from alea.video.segment.segments import SegmentError, read_json, sorted_by_start


def _hms(t_s: float) -> str:
    total = round(t_s)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


def _teams(s) -> str:
    return "+".join(map(str, s.red_teams)) + " v " + "+".join(map(str, s.blue_teams))


def _cmd_list(args: argparse.Namespace) -> int:
    sf = read_json(args.segments)
    print(f"{sf.event.event_code} {sf.video.file} ({len(sf.segments)} segments)")
    print(f"{'label':8} {'play_start':>10} {'play_end':>10} {'teams':32} {'score':>7} conf  flags")
    for s in sorted_by_start(sf.segments):
        score = "-" if s.score is None else f"{s.score.red_final}-{s.score.blue_final}"
        flags = "review" if s.needs_review else ""
        print(
            f"{s.match_label:8} {_hms(s.play_start_pts_s):>10} {_hms(s.play_end_pts_s):>10} "
            f"{_teams(s):32} {score:>7} {s.confidence:.2f}  {flags}"
        )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    sf = read_json(args.segments)
    print(f"ok: {len(sf.segments)} segments, schema_version {sf.schema_version}")
    return 0


def _cmd_to_matches_csv(args: argparse.Namespace) -> int:
    out = segments_to_matches_csv(read_json(args.segments), args.out)
    print(f"wrote {out}")
    return 0


def _cmd_check_schedule(args: argparse.Namespace) -> int:
    sf = read_json(args.segments)
    joins = match_segments_to_schedule(sf.segments, load_ftcscout_matches(args.schedule))
    bad = 0
    for j in joins:
        status = "ok" if j.matched else "DISAGREE"
        bad += not j.matched
        print(f"{j.label:8} {status}" + "".join(f"\n    - {d}" for d in j.disagreements))
    print(f"{len(joins) - bad} agree, {bad} disagree")
    return 1 if bad else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m alea.video.segment", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for name, fn, help_ in (
        ("list", _cmd_list, "print the segment table"),
        ("validate", _cmd_validate, "check schema and invariants"),
    ):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("segments", type=Path)
        sp.set_defaults(func=fn)
    sp = sub.add_parser("to-matches-csv", help="write the CSV for alea.data import-matches")
    sp.add_argument("segments", type=Path)
    sp.add_argument("out", type=Path)
    sp.set_defaults(func=_cmd_to_matches_csv)
    sp = sub.add_parser("check-schedule", help="join segments to a local FTCScout JSON")
    sp.add_argument("segments", type=Path)
    sp.add_argument("schedule", type=Path)
    sp.set_defaults(func=_cmd_check_schedule)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (SegmentError, ScheduleError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
