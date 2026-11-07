"""Import a robot log (.rlog or .wpilog) into the database, reading only contract keys."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from alea.data import rlog, wpilog
from alea.data.contract import AIM_COLUMNS, META_COLUMNS, canonical_key
from alea.data.logdata import LogData
from alea.data.models import LogFile, Match, Robot, Shot

_READERS = {".rlog": rlog.read, ".wpilog": wpilog.read}
_META_FLOAT = {c for c in META_COLUMNS.values() if c != "contract_version"}


def read_log(path: str | Path) -> LogData:
    """Read a log by extension."""
    suffix = Path(path).suffix.lower()
    if suffix not in _READERS:
        raise ValueError(f"unsupported log type {suffix!r}; expected .rlog or .wpilog")
    return _READERS[suffix](path)


def _contract_view(data: LogData) -> dict[str, list]:
    view: dict[str, list] = {}
    for key, samples in data.entries.items():
        canon = canonical_key(key)
        if canon is not None:
            view.setdefault(canon, []).extend(samples)
    return view


def import_log(
    session: Session,
    path: str | Path,
    *,
    robot: Robot | None = None,
    match: Match | None = None,
) -> LogFile:
    """Import one log; returns the existing row if the same bytes were imported before.

    Shot rows are built from the Alea/Aim/* samples that share a timestamp. Contract keys the
    log lacks stay NULL and are listed in `LogFile.missing_keys`. The caller commits.
    """
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    existing = session.scalar(select(LogFile).where(LogFile.sha256 == digest))
    if existing is not None:
        return existing

    data = read_log(path)
    view = _contract_view(data)

    meta: dict[str, str] = {}
    columns: dict[str, object] = {}
    for key, column in META_COLUMNS.items():
        if key not in view:
            continue
        raw = str(view[key][-1][1])
        meta[key] = raw
        columns[column] = int(raw) if column == "contract_version" else float(raw)

    log_file = LogFile(
        filename=path.name,
        sha256=digest,
        format=data.format,
        format_version=data.format_version,
        duration_s=data.duration_s,
        truncated=data.truncated,
        missing_keys=sorted(k for k in (*AIM_COLUMNS, *META_COLUMNS) if k not in view),
        metadata_json=meta,
        robot=robot,
        match=match,
        **columns,
    )

    frames: dict[float, dict[str, object]] = defaultdict(dict)
    for key in AIM_COLUMNS:
        for t_s, value in view.get(key, []):
            frames[t_s][AIM_COLUMNS[key]] = value
    for t_s in sorted(frames):
        log_file.shots.append(Shot(t_s=t_s, **frames[t_s]))

    session.add(log_file)
    session.flush()
    return log_file
