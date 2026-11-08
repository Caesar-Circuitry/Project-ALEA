from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from alea.web import __main__ as web_main

APP = Path(__file__).resolve().parents[1] / "alea" / "web" / "app.py"


@pytest.fixture(autouse=True)
def _headless(monkeypatch):
    monkeypatch.setenv("STREAMLIT_SERVER_HEADLESS", "true")
    monkeypatch.setenv("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")


def test_home_renders_synthetic_by_default():
    at = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not at.exception
    assert at.title[0].value == "ALEA"
    assert at.session_state["data_source"] == "synthetic"


def test_selector_switches_to_real():
    at = AppTest.from_file(str(APP), default_timeout=15).run()
    at.sidebar.radio[0].set_value("real").run()
    assert not at.exception
    assert at.session_state["data_source"] == "real"


def test_main_prints_command(capsys):
    assert web_main.main([]) == 0
    out = capsys.readouterr().out
    assert "streamlit run" in out
    assert str(web_main.APP_PATH) in out
    assert web_main.APP_PATH.exists()


def test_check_ok(capsys):
    assert web_main.main(["--check"]) == 0
