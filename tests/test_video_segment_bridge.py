"""Segments to the existing matches CSV importer and robot-log lookups (stage 2.2b)."""

import csv

import pytest
from sqlalchemy import select

from alea.data.db import make_engine, make_session, upgrade
from alea.data.matches import import_matches_csv
from alea.data.models import Match
from alea.video.segment.__main__ import main
from alea.video.segment.bridge import (
    MATCHES_CSV_COLUMNS,
    segment_for_label,
    segments_to_matches_csv,
    segments_with_team,
)
from alea.video.segment.segments import Score, SegmentError, write_json
from tests.test_video_segments import make_file, make_segment


@pytest.fixture
def session(tmp_path):
    url = f"sqlite:///{(tmp_path / 'bridge.db').as_posix()}"
    upgrade(url)
    engine = make_engine(url)
    with make_session(engine) as s:
        yield s
    engine.dispose()


def test_csv_imports_cleanly(session, tmp_path) -> None:
    sf = make_file(make_segment(1), make_segment(2, score=None), make_segment(3, score=Score(5, 6)))
    path = segments_to_matches_csv(sf, tmp_path / "matches.csv", event_name="Test Event")
    with path.open(newline="", encoding="utf-8") as fh:
        assert tuple(next(csv.reader(fh))) == MATCHES_CSV_COLUMNS
    result = import_matches_csv(session, path)
    session.commit()
    assert (result.events_created, result.matches_created) == (1, 3)
    rows = {m.label: (m.red_score, m.blue_score) for m in session.scalars(select(Match))}
    assert rows == {"Q1": (24, 28), "Q2": (None, None), "Q3": (5, 6)}
    again = import_matches_csv(session, path)
    assert again.matches_unchanged == 3


def test_columns_match_importer() -> None:
    from alea.data.matches import OPTIONAL_COLUMNS, REQUIRED_COLUMNS

    assert set(MATCHES_CSV_COLUMNS) == set(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)


def test_duplicate_labels_refused(tmp_path) -> None:
    sf = make_file(make_segment(1), make_segment(1, segment_id="replay"))
    with pytest.raises(SegmentError, match="duplicate match labels"):
        segments_to_matches_csv(sf, tmp_path / "m.csv")


def test_lookups() -> None:
    sf = make_file(
        make_segment(2, red_teams=(24331, 10002)), make_segment(1, blue_teams=(24331, 10004))
    )
    assert segment_for_label(sf, "Q2") is not None
    assert segment_for_label(sf, "Q99") is None
    assert [s.match_label for s in segments_with_team(sf, 24331)] == ["Q1", "Q2"]
    assert segments_with_team(sf, 1) == []


def test_cli_to_matches_csv(tmp_path, capsys) -> None:
    seg_path = tmp_path / "segments.json"
    write_json(seg_path, make_file())
    out = tmp_path / "out" / "matches.csv"
    assert main(["to-matches-csv", str(seg_path), str(out)]) == 0
    assert out.read_text(encoding="utf-8").splitlines()[1] == "TESTEVT,,Q1,24,28"
    assert "wrote" in capsys.readouterr().out
