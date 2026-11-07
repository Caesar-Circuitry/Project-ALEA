"""hive_constants matches the dsim-recorded constants.json; ported files carry the header."""

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from alea.hifi import DSIM_VERSION, hive_constants
from tests.hifi_replay import load

HIFI = Path(__file__).parent.parent / "alea" / "hifi"
HEADER = "Ported from dsim by genius0412"


def _plain(v: Any) -> Any:
    """Normalise a port constant to the JSON shape: tuples to lists, dataclasses to dicts."""
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return {k: _plain(x) for k, x in dataclasses.asdict(v).items()}
    if isinstance(v, (tuple, list)):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    return v


def _assert_same(got: Any, want: Any, name: str) -> None:
    """Exact equality; ints and floats of equal value count as equal (JSON writes 4 for 4.0)."""
    assert _plain(got) == want, name
    assert type(got) is not bool or isinstance(want, bool), name


@pytest.mark.parametrize("block", ["config_ts", "hive_ts"])
def test_module_constants_match_constants_json(block: str) -> None:
    doc = load("constants.json")
    for name, want in doc[block].items():
        _assert_same(getattr(hive_constants, name), want, name)


def test_hive_geometry_matches_constants_json() -> None:
    want = load("constants.json")["fieldDims_gen_HIVE"]
    got = _plain(hive_constants.HIVE)
    assert got == want
    assert set(got) == set(want)


def test_tip_table_is_a_tuple() -> None:
    assert hive_constants.BB_TIP_POLLEN == (8, 7, 6, 3, 1, 0)
    assert isinstance(hive_constants.BB_TIP_POLLEN, tuple)
    assert hive_constants.BB_TIP_SWING_S == 4.0
    assert hive_constants.BB_TIP_RELEASE_S == hive_constants.BB_TIP_SWING_S / 2


def test_hive_ts_reads_are_all_present() -> None:
    for name in load("constants.json")["inputs"]["hive_ts_reads"]:
        assert hasattr(hive_constants, name), name


GLUE = ["frame.py", "hifi_study.py", "hive_session.py"]  # original ALEA code that uses the port
PORTED = sorted(p for p in HIFI.glob("*.py") if p.name != "__init__.py" and p.name not in GLUE)


def test_ported_files_exist() -> None:
    assert {p.name for p in PORTED} >= {"hive.py", "hive_constants.py", "hive_math.py"}


@pytest.mark.parametrize("path", PORTED, ids=lambda p: p.name)
def test_ported_file_header(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    first = text.removeprefix('"""').splitlines()[0]
    assert first.startswith(HEADER), f"{path.name}: first line is {first!r}"
    assert DSIM_VERSION in first, f"{path.name}: first line lacks the pinned hash"
    assert "PolyForm Noncommercial 1.0.0" in text.split('"""')[1], f"{path.name}: licence not named"


@pytest.mark.parametrize("name", GLUE)
def test_glue_file_header(name: str) -> None:
    doc = (HIFI / name).read_text(encoding="utf-8").split('"""')[1]
    first = doc.splitlines()[0]
    assert first.startswith("Uses the dsim port") and DSIM_VERSION in first
    assert "PolyForm Noncommercial 1.0.0" in doc
