"""Video-review page and demo loaders (roadmap phase 6)."""

import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from alea.web import video_demo

PAGE = Path(__file__).resolve().parents[1] / "alea" / "web" / "pages" / "3_video_review.py"


@pytest.fixture(autouse=True)
def _headless(monkeypatch):
    monkeypatch.setenv("STREAMLIT_SERVER_HEADLESS", "true")
    monkeypatch.setenv("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")


def test_page_runs_synthetic():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PAGE), default_timeout=30).run()
    assert not at.exception
    assert len(at.dataframe) >= 2


def test_page_real_mode_missing_file(tmp_path):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PAGE), default_timeout=30).run()
    at.sidebar.radio[0].set_value("real").run()
    at.sidebar.text_input[0].set_value(str(tmp_path / "missing.jsonl")).run()
    assert not at.exception
    assert any("not found" in w.value for w in at.warning)


def test_generators_shape():
    shots = video_demo.make_shots(seed=3)
    assert shots == video_demo.make_shots(seed=3)
    for s in shots:
        assert 8 <= len(s["ball_track"]) <= 12
        assert s["schema_version"] == 1


def test_roundtrip_through_loaders(tmp_path):
    shots = video_demo.make_shots()
    lms = video_demo.make_landmarks()
    cal = video_demo.make_calibration()
    video_demo.write_jsonl(tmp_path / "shots.jsonl", shots)
    video_demo.write_jsonl(tmp_path / "landmarks.jsonl", lms)
    (tmp_path / "calibration.json").write_text(json.dumps(cal), encoding="utf-8")
    assert video_demo.load_jsonl(tmp_path / "shots.jsonl") == shots
    assert video_demo.load_jsonl(tmp_path / "landmarks.jsonl") == lms
    assert video_demo.load_json(tmp_path / "calibration.json") == cal


def test_wrong_schema_version_raises(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    (tmp_path / "a.jsonl").write_text(json.dumps({"schema_version": 2}) + "\n", encoding="utf-8")
    (tmp_path / "bad.json").write_text("{nope", encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        video_demo.load_json(tmp_path / "a.json")
    with pytest.raises(ValueError, match="schema_version"):
        video_demo.load_jsonl(tmp_path / "a.jsonl")
    with pytest.raises(ValueError, match="invalid JSON"):
        video_demo.load_json(tmp_path / "bad.json")
