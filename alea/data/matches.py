"""Import match results from a CSV file (see alea/data/README.md for the format)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from alea.data.models import Event, Match

REQUIRED_COLUMNS = ("event_code", "label", "red_score", "blue_score")
OPTIONAL_COLUMNS = ("event_name",)


class MatchCsvError(ValueError):
    """The CSV is malformed; the message names the line number."""


@dataclass
class MatchImportResult:
    events_created: int = 0
    matches_created: int = 0
    matches_updated: int = 0
    matches_unchanged: int = 0


@dataclass
class _Row:
    event_code: str
    event_name: str | None
    label: str
    red_score: int | None
    blue_score: int | None


def _score(raw: str, column: str, line: int) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        raise MatchCsvError(f"line {line}: {column} must be an integer, got {raw!r}") from None
    if value < 0:
        raise MatchCsvError(f"line {line}: {column} must not be negative, got {value}")
    return value


def _parse(path: Path) -> list[_Row]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = [h.strip() for h in (reader.fieldnames or [])]
        if not header:
            raise MatchCsvError("line 1: file is empty; a header row is required")
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            raise MatchCsvError(f"line 1: missing required column(s): {', '.join(missing)}")
        reader.fieldnames = header
        rows: list[_Row] = []
        seen: dict[tuple[str, str], int] = {}
        for record in reader:
            line = reader.line_num
            if None in record:
                raise MatchCsvError(f"line {line}: more values than header columns")
            if not any((v or "").strip() for v in record.values()):
                continue  # blank line
            code = (record["event_code"] or "").strip()
            label = (record["label"] or "").strip()
            if not code:
                raise MatchCsvError(f"line {line}: event_code is empty")
            if not label:
                raise MatchCsvError(f"line {line}: label is empty")
            if (code, label) in seen:
                raise MatchCsvError(
                    f"line {line}: duplicate match {code}:{label} (first on line "
                    f"{seen[(code, label)]})"
                )
            seen[(code, label)] = line
            name = (record.get("event_name") or "").strip() or None
            rows.append(
                _Row(
                    code,
                    name,
                    label,
                    _score(record["red_score"] or "", "red_score", line),
                    _score(record["blue_score"] or "", "blue_score", line),
                )
            )
    return rows


def get_or_create_event(session: Session, code: str, name: str | None = None) -> Event:
    event = session.scalar(select(Event).where(Event.code == code))
    if event is None:
        event = Event(code=code, name=name)
        session.add(event)
        session.flush()
    elif name and event.name != name:
        event.name = name
    return event


def get_or_create_match(session: Session, event: Event, label: str) -> Match:
    match = session.scalar(select(Match).where(Match.event_id == event.id, Match.label == label))
    if match is None:
        match = Match(event=event, label=label)
        session.add(match)
        session.flush()
    return match


def import_matches_csv(session: Session, path: str | Path) -> MatchImportResult:
    """Upsert the matches in `path`; running it twice changes nothing the second time.

    The whole file is validated before anything is written. The caller commits.
    """
    rows = _parse(Path(path))
    result = MatchImportResult()
    for row in rows:
        event = session.scalar(select(Event).where(Event.code == row.event_code))
        if event is None:
            result.events_created += 1
        event = get_or_create_event(session, row.event_code, row.event_name)
        match = session.scalar(
            select(Match).where(Match.event_id == event.id, Match.label == row.label)
        )
        if match is None:
            session.add(
                Match(
                    event=event,
                    label=row.label,
                    red_score=row.red_score,
                    blue_score=row.blue_score,
                )
            )
            result.matches_created += 1
        elif (match.red_score, match.blue_score) != (row.red_score, row.blue_score):
            match.red_score, match.blue_score = row.red_score, row.blue_score
            result.matches_updated += 1
        else:
            result.matches_unchanged += 1
        session.flush()
    return result
