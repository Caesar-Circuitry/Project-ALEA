"""CLI, synthetic logs, launch detection and match CSV import (roadmap phase 0)."""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from alea.data import rlog
from alea.data.cli import main
from alea.data.db import make_engine, make_session, upgrade
from alea.data.importer import import_log
from alea.data.launches import LaunchConfig, detect_in_signal
from alea.data.matches import MatchCsvError, import_matches_csv
from alea.data.models import Event, Launch, LogFile, Match, Robot, Shot, Team
from alea.data.synthetic import FLYWHEEL_KEY, synth_match, write_matches

SAMPLE_CSV = Path(__file__).resolve().parent / "data" / "sample_matches.csv"
GOLDEN = Path(__file__).resolve().parent / "golden" / "sample_contract.rlog"


@pytest.fixture
def url(tmp_path) -> str:
    return f"sqlite:///{(tmp_path / 'cli.db').as_posix()}"


@pytest.fixture
def session(url):
    upgrade(url)
    engine = make_engine(url)
    with make_session(engine) as s:
        yield s
    engine.dispose()


def _count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


# --- synthetic logs -------------------------------------------------------------------------


def test_synth_is_deterministic_and_realistic() -> None:
    a, b = synth_match(7), synth_match(7)
    assert a.data == b.data
    assert a.data != synth_match(8).data
    log = rlog.decode(a.data)
    assert 149 < log.duration_s < 151
    assert len(log.entries["RealOutputs/Alea/Aim/DistanceIn"]) == 7500
    assert len(a.launch_times_s) >= 10


# --- launch detection -----------------------------------------------------------------------


def test_detect_signal_basics() -> None:
    cfg = LaunchConfig()
    steady = [(i * 0.02, 1200.0) for i in range(100)]
    assert detect_in_signal(steady, cfg) == []
    dipped = [(t, v - 150 if 0.99 < t < 1.03 else v) for t, v in steady]
    found = detect_in_signal(dipped, cfg)
    assert [round(f.t_s, 2) for f in found] == [1.0]
    assert found[0].dip_ticks_per_sec == pytest.approx(150)


def test_detect_ignores_spin_down_and_small_dip() -> None:
    off = [(i * 0.02, 1200.0 if i < 50 else 0.0) for i in range(100)]
    assert detect_in_signal(off, LaunchConfig()) == []
    small = [(i * 0.02, 1200.0 - (30 if i == 50 else 0)) for i in range(100)]
    assert detect_in_signal(small, LaunchConfig()) == []


def test_detect_refractory() -> None:
    sig = [(i * 0.02, 1200.0 - (150 if i in (50, 52) else 0)) for i in range(100)]
    assert len(detect_in_signal(sig, LaunchConfig())) == 1
    assert len(detect_in_signal(sig, LaunchConfig(refractory_s=0.0))) == 2


def test_import_detects_known_launches(session, tmp_path) -> None:
    m = synth_match(3)
    path = tmp_path / "m.rlog"
    path.write_bytes(m.data)
    log = import_log(session, path)
    session.commit()
    got = sorted(item.t_s for item in log.launches)
    assert len(got) == len(m.launch_times_s)
    assert got == pytest.approx(m.launch_times_s, abs=0.021)
    first = min(log.launches, key=lambda item: item.t_s)
    assert first.aimed is True
    assert first.distance_in is not None
    assert first.dip_ticks_per_sec > 100
    assert FLYWHEEL_KEY in (log.launch_note or "")


def test_no_velocity_key_gives_zero_launches_and_note(session) -> None:
    log = import_log(session, GOLDEN)
    assert log.launches == []
    assert "no flywheel velocity key" in (log.launch_note or "")


# --- match CSV ------------------------------------------------------------------------------


def test_matches_csv_import_and_idempotent(session) -> None:
    first = import_matches_csv(session, SAMPLE_CSV)
    session.commit()
    assert (first.events_created, first.matches_created) == (1, 3)
    assert _count(session, Match) == 3
    event = session.scalar(select(Event))
    assert event is not None and event.name == "Test Cup"
    q3 = session.scalar(select(Match).where(Match.label == "Q3"))
    assert q3 is not None and q3.red_score is None
    again = import_matches_csv(session, SAMPLE_CSV)
    assert (again.matches_created, again.matches_updated, again.matches_unchanged) == (0, 0, 3)


def test_matches_csv_updates_score(session, tmp_path) -> None:
    import_matches_csv(session, SAMPLE_CSV)
    p = tmp_path / "u.csv"
    p.write_text("event_code,label,red_score,blue_score\nTESTCUP,Q3,10,20\n")
    res = import_matches_csv(session, p)
    assert res.matches_updated == 1
    q3 = session.scalar(select(Match).where(Match.label == "Q3"))
    assert q3 is not None and (q3.red_score, q3.blue_score) == (10, 20)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "line 1"),
        ("event_code,label,red_score\nA,Q1,1\n", "missing required column.*blue_score"),
        ("event_code,label,red_score,blue_score\nA,Q1,x,2\n", "line 2: red_score"),
        ("event_code,label,red_score,blue_score\nA,Q1,1,2\nA,Q2,1,-2\n", "line 3: blue_score"),
        ("event_code,label,red_score,blue_score\n,Q1,1,2\n", "line 2: event_code is empty"),
        ("event_code,label,red_score,blue_score\nA,Q1,1,2\nA,Q1,3,4\n", "line 3: duplicate"),
    ],
)
def test_matches_csv_errors(session, tmp_path, text, message) -> None:
    p = tmp_path / "bad.csv"
    p.write_text(text)
    with pytest.raises(MatchCsvError, match=message):
        import_matches_csv(session, p)
    assert _count(session, Match) == 0


# --- CLI ------------------------------------------------------------------------------------


def test_cli_end_to_end(url, tmp_path, capsys) -> None:
    logs = tmp_path / "logs"
    truth = write_matches(logs, 3, seed=11)
    assert main(["matches", str(SAMPLE_CSV), "--db", url]) == 0
    code = main(
        ["import", str(logs), "--db", url, "--robot", "Bee", "--team", "24331",
         "--match", "TESTCUP:Q1"]
    )  # fmt: skip
    out = capsys.readouterr().out
    assert code == 0
    assert "3 imported, 0 skipped duplicate, 0 failed" in out

    engine = make_engine(url)
    with make_session(engine) as s:
        assert _count(s, LogFile) == 3
        assert _count(s, Launch) == sum(len(t.launch_times_s) for _, t in truth)
        assert _count(s, Match) == 3  # Q1 reused, not duplicated
        assert _count(s, Robot) == 1 and _count(s, Team) == 1
        assert _count(s, Shot) == 3 * 7500
        linked = s.scalar(select(func.count()).select_from(LogFile).where(LogFile.match_id == 1))
        assert linked == 3
    engine.dispose()

    assert main(["summary", "--db", url]) == 0
    summary = capsys.readouterr().out
    assert "log_files: 3" in summary
    assert f"launches: {sum(len(t.launch_times_s) for _, t in truth)}" in summary

    assert main(["import", str(logs), "--db", url]) == 0
    assert "0 imported, 3 skipped duplicate, 0 failed" in capsys.readouterr().out


def test_cli_bad_file_does_not_abort_batch(url, tmp_path, capsys) -> None:
    d = tmp_path / "logs"
    write_matches(d, 1, seed=1)
    (d / "broken.rlog").write_bytes(b"\x07garbage")
    (d / "notes.txt").write_text("ignored")
    assert main(["import", str(d), "--db", url]) == 1
    out = capsys.readouterr().out
    assert "broken.rlog: failed" in out
    assert "1 imported, 0 skipped duplicate, 1 failed" in out


def test_cli_recursive_and_single_file(url, tmp_path, capsys) -> None:
    write_matches(tmp_path / "a" / "b", 1, seed=2)
    assert main(["import", str(tmp_path / "a"), "--db", url]) == 0
    assert "no .rlog or .wpilog" in capsys.readouterr().out
    assert main(["import", str(tmp_path / "a"), "--db", url, "--recursive"]) == 0
    assert "1 imported" in capsys.readouterr().out
    assert main(["import", str(GOLDEN), "--db", url]) == 0


def test_cli_errors(url, tmp_path, capsys) -> None:
    assert main(["import", str(tmp_path / "missing"), "--db", url]) == 2
    assert main(["import", str(GOLDEN), "--db", url, "--match", "nolabel"]) == 2
    bad = tmp_path / "bad.csv"
    bad.write_text("event_code,label\nA,Q1\n")
    assert main(["matches", str(bad), "--db", url]) == 1
    assert "missing required" in capsys.readouterr().err


def test_cli_synth(tmp_path, capsys) -> None:
    assert main(["synth", str(tmp_path / "s"), "--matches", "2", "--seed", "5"]) == 0
    assert len(list((tmp_path / "s").glob("*.rlog"))) == 2
