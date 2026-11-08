from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from alea.web import logs_demo, study_demo

PAGES = Path(__file__).resolve().parents[1] / "alea" / "web" / "pages"


@pytest.fixture(autouse=True)
def _headless(monkeypatch):
    monkeypatch.setenv("STREAMLIT_SERVER_HEADLESS", "true")
    monkeypatch.setenv("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")


def test_study_demo_rows():
    rows = study_demo.build_summary(1)
    assert len(rows) == 72
    assert {"id", "aim_deg", "fired", "scored", "pct_scored_of_fired"} <= set(rows[0])
    assert rows == study_demo.build_summary(1)


def test_logs_demo_finds_launches():
    log = logs_demo.load_demo(0)
    assert log.launches
    assert len(log.t_s) == len(log.flywheel_ticks_per_sec) > 0
    assert len(logs_demo.launch_rows(log)) == len(log.launches)


def test_shot_study_synthetic():
    at = AppTest.from_file(str(PAGES / "1_shot_study.py"), default_timeout=15).run()
    assert not at.exception
    assert at.title[0].value == "Shot study"
    assert len(at.dataframe) >= 1


def test_shot_study_real_missing_dir(tmp_path):
    at = AppTest.from_file(str(PAGES / "1_shot_study.py"), default_timeout=15)
    at.session_state["data_source"] = "real"
    at.run()
    at.text_input[0].set_value(str(tmp_path / "nope")).run()
    assert not at.exception
    assert at.info


def test_match_logs_synthetic():
    at = AppTest.from_file(str(PAGES / "2_match_logs.py"), default_timeout=15).run()
    assert not at.exception
    assert at.title[0].value == "Match logs"
    assert len(at.dataframe) == 1


def test_match_logs_real_empty_db(tmp_path):
    at = AppTest.from_file(str(PAGES / "2_match_logs.py"), default_timeout=15)
    at.session_state["data_source"] = "real"
    at.run()
    at.text_input[0].set_value(f"sqlite:///{(tmp_path / 'empty.db').as_posix()}").run()
    assert not at.exception
    assert at.info
