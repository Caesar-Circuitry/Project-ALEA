"""Structure check of the recorded dsim hive traces (replay comes with the port)."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
TRACES = ROOT / "hifi_traces"
PIN = (ROOT.parent / "alea" / "hifi" / "DSIM_VERSION").read_text(encoding="utf-8").strip()
FILES = sorted(TRACES.glob("*.json"))
REQUIRED = ("dsim_commit", "source_file", "scenario", "generator", "inputs")


def test_expected_fixtures_exist() -> None:
    names = {p.name for p in FILES}
    assert {
        "capture.json",
        "load.json",
        "sides.json",
        "timer_dt60_threshold.json",
        "timer_dt60_surplus.json",
        "timer_coarse.json",
        "spill.json",
        "constants.json",
        "deflect.json",
    } <= names


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_fixture_schema(path: Path) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    for key in REQUIRED:
        assert key in doc, f"{path.name} lacks {key}"
    assert doc["dsim_commit"] == PIN
    assert doc["source_file"].endswith("hive.ts")
    assert set(doc["generator"]) >= {"script", "command"}
    assert len(doc) > len(REQUIRED), "no recorded outputs"
    assert path.stat().st_size < 1_000_000
