"""Structure check of the recorded dsim 3D hive traces (replay is not written yet)."""

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parent
TRACES = ROOT / "hifi_traces" / "sim3d"
PIN = (ROOT.parent / "alea" / "hifi" / "DSIM_VERSION").read_text(encoding="utf-8").strip()
FILES = sorted(TRACES.glob("*.json"))
REQUIRED = ("dsim_commit", "source_file", "source_files", "scenario", "generator", "inputs")
LOAD_COLUMNS = {
    "tray_theta_rad",
    "tray_omega_rad_s",
    "hive_angle_rad",
    "hive_ang_vel_rad_s",
    "tipping_s",
    "released",
    "tips",
    "up",
    "contents_n",
    "spill_n",
    "tray_held",
    "nectar_due",
}


def _load(name: str) -> dict[str, Any]:
    return json.loads((TRACES / name).read_text(encoding="utf-8"))


def test_expected_fixtures_exist() -> None:
    names = {p.name for p in FILES}
    assert {
        "constants3d.json",
        "statics3d.json",
        "loads_no_tip_blue.json",
        "loads_tip_blue.json",
        "loads_red.json",
        "joint_tick.json",
        "g409_contacts.json",
    } <= names


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_fixture_schema(path: Path) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    for key in REQUIRED:
        assert key in doc, f"{path.name} lacks {key}"
    assert doc["dsim_commit"] == PIN
    assert "/sim3d/" in doc["source_file"]
    assert doc["source_file"] == doc["source_files"][0]
    assert set(doc["generator"]) >= {"script", "command"}
    assert len(doc) > len(REQUIRED), "no recorded outputs"
    assert path.stat().st_size < 1_000_000


LOAD_FILES = ["loads_no_tip_blue.json", "loads_tip_blue.json", "loads_red.json"]


@pytest.mark.parametrize("name", LOAD_FILES)
def test_load_traces_are_rectangular(name: str) -> None:
    doc = _load(name)
    assert doc["rows"]
    for row in doc["rows"]:
        cols = row["columns"]
        assert set(cols) == LOAD_COLUMNS
        assert {len(v) for v in cols.values()} == {row["ticks"]}


def test_tip_table_outcomes() -> None:
    """The recorded runs agree with BB_TIP_POLLEN = [8, 7, 6, 3, 1, 0] by nectar."""
    for name, expect_tip in (
        ("loads_no_tip_blue.json", False),
        ("loads_tip_blue.json", True),
    ):
        for row in _load(name)["rows"]:
            tipped = row["summary"]["final_tips"] > 0
            empty = row["pollen"] == 0 and row["nectar"] == 0
            assert tipped is expect_tip or empty, (name, row["pollen"], row["nectar"])
    rows = _load("loads_red.json")["rows"]
    red = {(r["pollen"], r["nectar"]): r["summary"]["final_tips"] for r in rows}
    assert red[(8, 0)] > 0 and red[(7, 0)] == 0


def test_g409_rows() -> None:
    rows = _load("g409_contacts.json")["rows"]
    away, under = rows
    assert away["robot_under_down_cell"] is False and under["robot_under_down_cell"] is True
    assert away["columns"]["g409_lines_total"][-1] == 0
    assert under["columns"]["g409_lines_total"][-1] > 0


def test_joint_tick_cases_have_state() -> None:
    cases = _load("joint_tick.json")["cases"]
    assert len(cases) >= 10
    for c in cases:
        assert {"label", "hive_in", "hive_out", "events"} <= set(c)
