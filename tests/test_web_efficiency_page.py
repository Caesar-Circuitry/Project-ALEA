"""Tests for the launcher-efficiency page and its demo data."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from alea.web.efficiency_demo import (
    per_burst_index,
    per_session,
    read_measurements_csv,
    synthetic_rows,
    write_measurements_csv,
)

PAGE = Path(__file__).resolve().parents[1] / "alea" / "web" / "pages" / "5_launcher_efficiency.py"


def test_page_renders_synthetic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STREAMLIT_SERVER_HEADLESS", "true")
    monkeypatch.setenv("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    at = AppTest.from_file(str(PAGE), default_timeout=30).run()
    assert not at.exception


def test_synthetic_shape() -> None:
    rows = synthetic_rows()
    assert len(rows) == 40
    assert len({r["video_file"] for r in rows}) == 3
    eff = np.array([r["efficiency"] for r in rows])
    assert 0.35 < eff.mean() < 0.45
    assert len(per_session(rows)) == 3
    assert per_burst_index(rows)[0]["burst_index"] == 0


def test_csv_round_trip(tmp_path: Path) -> None:
    rows = synthetic_rows()
    p = tmp_path / "m.csv"
    write_measurements_csv(p, rows)
    back = read_measurements_csv(p)
    assert len(back) == len(rows)
    assert back[3]["shot_index"] == rows[3]["shot_index"]
    assert back[3]["efficiency"] == pytest.approx(rows[3]["efficiency"])
    assert back[3]["video_file"] == rows[3]["video_file"]


def test_bad_header_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.csv"
    p.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_measurements_csv(p)
