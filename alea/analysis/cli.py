"""`python -m alea.analysis` command line (Phases 3-5)."""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Sequence
from pathlib import Path

from alea.analysis.hivelab import (
    HiveLabFormatError,
    LogLaunch,
    read_hivelab_csv,
    to_measurements,
    write_measurements_csv,
)
from alea.analysis.sync import SyncResult, join_launches, match_offset, offset_from_cue


def launches_from_log(path: Path) -> list[LogLaunch]:
    """Decode an .rlog/.wpilog and run the launch detector (no database)."""
    from alea.data.importer import read_log
    from alea.data.launches import detect_launches

    result = detect_launches(read_log(path))
    return [
        LogLaunch(d.t_s, d.ticks_per_sec_before, d.ticks_per_sec_after, d.dip_ticks_per_sec)
        for d in result.launches
    ]


def launches_from_csv(path: Path) -> list[LogLaunch]:
    """Read launches from a CSV with columns t_s,before,after,dip (and optional launch_id)."""
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        need = ["t_s", "before", "after", "dip"]
        missing = [c for c in need if c not in (reader.fieldnames or [])]
        if missing:
            raise HiveLabFormatError(f"launches CSV lacks column(s) {', '.join(missing)}")
        return [
            LogLaunch(
                float(r["t_s"]),
                float(r["before"]),
                float(r["after"]),
                float(r["dip"]),
                int(r["launch_id"]) if r.get("launch_id") else None,
            )
            for r in reader
        ]


def _parse_mapping(items: Sequence[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        key, sep, col = item.partition("=")
        if not sep or not col:
            raise HiveLabFormatError(f"--map expects field=column, got {item!r}")
        out[key] = col
    return out


def _cmd_hivelab_import(args: argparse.Namespace) -> int:
    try:
        shots = read_hivelab_csv(args.csv, _parse_mapping(args.map))
        if args.log is not None:
            launches = launches_from_log(Path(args.log))
        else:
            launches = launches_from_csv(Path(args.launches_csv))
    except (HiveLabFormatError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if (args.cue_video_s is None) != (args.cue_log_s is None):
        print("error: give both --cue-video-s and --cue-log-s", file=sys.stderr)
        return 2
    if args.cue_video_s is not None:
        offset_s = offset_from_cue(args.cue_video_s, args.cue_log_s)
        sync = SyncResult(offset_s, 0, float("nan"), [], "cue")
        print(f"sync: cue offset {offset_s:.3f} s")
    else:
        sync = match_offset(
            [s.t_video_s for s in shots],
            [ln.t_s for ln in launches],
            window_s=args.window_s,
            search=(args.search_lo_s, args.search_hi_s),
        )
        if sync.n_pairs < 2:
            print(
                f"error: burst-gap sync found only {sync.n_pairs} pair(s); give a cue",
                file=sys.stderr,
            )
            return 3
        print(
            f"sync: {sync.method} offset {sync.offset_s:.3f} s, {sync.n_pairs} pairs, "
            f"residual rms {sync.residual_rms_s * 1000:.1f} ms"
        )
        if sync.ambiguous:
            print("warning: sync is ambiguous (a second offset scores within one pair)")
    rows = join_launches(to_measurements(shots), launches, sync.offset_s, args.max_dt_s)
    n_joined = sum(r.t_log_s is not None for r in rows)
    write_measurements_csv(args.out, rows)
    print(f"join: {n_joined} of {len(rows)} shots matched a launch -> {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m alea.analysis")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("hivelab-import", help="join a hive-shot-lab CSV to a robot log")
    p.add_argument("csv", help="hive-shot-lab export")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--log", help=".rlog or .wpilog of the same session")
    src.add_argument("--launches-csv", help="CSV with columns t_s,before,after,dip")
    p.add_argument("--cue-video-s", type=float, help="clap/LED time in the video")
    p.add_argument("--cue-log-s", type=float, help="the same event in the log")
    p.add_argument("--out", required=True, help="measurement CSV to write")
    p.add_argument("--map", action="append", default=[], metavar="FIELD=COLUMN")
    p.add_argument("--window-s", type=float, default=0.05)
    p.add_argument("--max-dt-s", type=float, default=0.25)
    p.add_argument("--search-lo-s", type=float, default=float("-inf"))
    p.add_argument("--search-hi-s", type=float, default=float("inf"))
    p.set_defaults(func=_cmd_hivelab_import)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


def run() -> None:
    sys.exit(main())
