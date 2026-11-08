"""Tests for the match-reflection page and its demo data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from alea.web.reflection_demo import load_report, synthetic_report, validate_report

PAGE = Path(__file__).resolve().parents[1] / "alea" / "web" / "pages" / "4_match_reflection.py"


def test_page_renders_synthetic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STREAMLIT_SERVER_HEADLESS", "true")
    monkeypatch.setenv("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    at = AppTest.from_file(str(PAGE), default_timeout=30).run()
    assert not at.exception
    assert any("prototype (phase 5)" in w.value for w in at.warning)


def test_synthetic_is_valid_and_deterministic() -> None:
    assert validate_report(synthetic_report()) == []
    assert synthetic_report() == synthetic_report()


def test_json_round_trip(tmp_path: Path) -> None:
    p = tmp_path / "r.json"
    p.write_text(json.dumps(synthetic_report()), encoding="utf-8")
    assert load_report(p) == synthetic_report()


def test_bad_schema_version_raises(tmp_path: Path) -> None:
    p = tmp_path / "r.json"
    p.write_text(json.dumps({**synthetic_report(), "schema_version": 2}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_report(p)


def test_validate_flags_bad_source_and_missing_key() -> None:
    d = synthetic_report()
    d["timeline"][0]["source"] = "guessed"
    del d["summary"]
    problems = validate_report(d)
    assert any("bad source" in p for p in problems)
    assert any("summary" in p for p in problems)
