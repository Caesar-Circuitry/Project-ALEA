"""`python -m alea.data` command line: import logs, import match results, summarise, synth."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from alea.data.db import default_url, make_engine, make_session, upgrade
from alea.data.importer import file_sha256, import_log
from alea.data.matches import (
    MatchCsvError,
    get_or_create_event,
    get_or_create_match,
    import_matches_csv,
)
from alea.data.models import Event, Launch, LogFile, Match, Robot, Shot, Team

LOG_SUFFIXES = (".rlog", ".wpilog")


def collect_logs(target: Path, recursive: bool = False) -> list[Path]:
    """The file itself, or the .rlog/.wpilog files in a directory (sorted)."""
    if target.is_dir():
        found = target.rglob("*") if recursive else target.iterdir()
        return sorted(p for p in found if p.is_file() and p.suffix.lower() in LOG_SUFFIXES)
    return [target]


def _robot(session: Session, name: str | None, team_number: int | None) -> Robot | None:
    team = None
    if team_number is not None:
        team = session.scalar(select(Team).where(Team.number == team_number))
        if team is None:
            team = Team(number=team_number)
            session.add(team)
            session.flush()
    if name is None and team is None:
        return None
    name = name or f"team-{team_number}"
    robot = session.scalar(select(Robot).where(Robot.name == name))
    if robot is None:
        robot = Robot(name=name, team=team)
        session.add(robot)
        session.flush()
    elif team is not None and robot.team_id is None:
        robot.team = team
    return robot


def _cmd_import(args: argparse.Namespace) -> int:
    target = Path(args.path)
    if not target.exists():
        print(f"error: {target} does not exist", file=sys.stderr)
        return 2
    match_spec = None
    if args.match:
        event_code, sep, label = args.match.partition(":")
        if not sep or not event_code.strip() or not label.strip():
            print("error: --match must look like EVENT:LABEL", file=sys.stderr)
            return 2
        match_spec = (event_code.strip(), label.strip())
    files = collect_logs(target, args.recursive)
    if not files:
        print(f"no .rlog or .wpilog files found in {target}")
        return 0

    upgrade(args.db)
    engine = make_engine(args.db)
    counts = {"imported": 0, "skipped": 0, "failed": 0}
    try:
        with make_session(engine) as session:
            robot = _robot(session, args.robot, args.team)
            match = None
            if match_spec:
                event = get_or_create_event(session, match_spec[0])
                match = get_or_create_match(session, event, match_spec[1])
            session.commit()
            for path in files:
                try:
                    digest = file_sha256(path)
                    if session.scalar(select(LogFile.id).where(LogFile.sha256 == digest)):
                        counts["skipped"] += 1
                        print(f"{path}: skipped duplicate")
                        continue
                    row = import_log(session, path, robot=robot, match=match)
                    session.commit()
                    counts["imported"] += 1
                    print(
                        f"{path}: imported ({len(row.shots)} loops, {len(row.launches)} launches)"
                    )
                except Exception as exc:  # a bad file must not abort the batch
                    session.rollback()
                    counts["failed"] += 1
                    print(f"{path}: failed: {exc}")
    finally:
        engine.dispose()
    print(
        f"{counts['imported']} imported, {counts['skipped']} skipped duplicate, "
        f"{counts['failed']} failed"
    )
    return 1 if counts["failed"] else 0


def _cmd_matches(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"error: {csv_path} is not a file", file=sys.stderr)
        return 2
    upgrade(args.db)
    engine = make_engine(args.db)
    try:
        with make_session(engine) as session:
            try:
                res = import_matches_csv(session, csv_path)
            except MatchCsvError as exc:
                session.rollback()
                print(f"error: {csv_path}: {exc}", file=sys.stderr)
                return 1
            session.commit()
    finally:
        engine.dispose()
    print(
        f"events created {res.events_created}, matches created {res.matches_created}, "
        f"updated {res.matches_updated}, unchanged {res.matches_unchanged}"
    )
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    upgrade(args.db)
    engine = make_engine(args.db)
    try:
        with make_session(engine) as session:

            def count(model: type, *where: object) -> int:
                return session.scalar(select(func.count()).select_from(model).where(*where)) or 0  # type: ignore[arg-type]

            rows = [
                ("teams", count(Team)),
                ("robots", count(Robot)),
                ("events", count(Event)),
                ("matches", count(Match)),
                ("log_files", count(LogFile)),
                ("log_files_truncated", count(LogFile, LogFile.truncated.is_(True))),
                ("log_files_with_match", count(LogFile, LogFile.match_id.is_not(None))),
                ("shots", count(Shot)),
                ("launches", count(Launch)),
            ]
    finally:
        engine.dispose()
    for name, value in rows:
        print(f"{name}: {value}")
    return 0


def _cmd_synth(args: argparse.Namespace) -> int:
    from alea.data.synthetic import write_matches

    for path, truth in write_matches(args.outdir, args.matches, args.seed):
        print(f"{path}: {len(truth.launch_times_s)} launches")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m alea.data", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_db(p: argparse.ArgumentParser) -> None:
        p.add_argument("--db", default=default_url(), help="database URL (default: ALEA_DB_URL)")

    p = sub.add_parser("import", help="import a log file or a directory of logs")
    p.add_argument("path")
    add_db(p)
    p.add_argument("--robot", help="robot name (get-or-create)")
    p.add_argument("--team", type=int, help="team number (get-or-create)")
    p.add_argument("--match", help="attach every imported log to EVENT:LABEL (get-or-create)")
    p.add_argument("--recursive", action="store_true", help="scan directories recursively")
    p.set_defaults(func=_cmd_import)

    p = sub.add_parser("matches", help="import match results from a CSV")
    p.add_argument("csv")
    add_db(p)
    p.set_defaults(func=_cmd_matches)

    p = sub.add_parser("summary", help="print row counts")
    add_db(p)
    p.set_defaults(func=_cmd_summary)

    p = sub.add_parser("synth", help="write synthetic .rlog files")
    p.add_argument("outdir")
    p.add_argument("--matches", type=int, default=1)
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=_cmd_synth)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


def run() -> None:
    sys.exit(main())
