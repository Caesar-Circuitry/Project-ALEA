"""The Java under robot/ must match docs/robot-interface.md and alea.game."""

import math
import re
from pathlib import Path

import pytest

from alea.game import biobuzz

ROOT = Path(__file__).resolve().parent.parent
JAVA_DIR = ROOT / "robot" / "TeamCode" / "src" / "main" / "java"
DOC = ROOT / "docs" / "robot-interface.md"
TOL = 1e-6

KEY_CALL = re.compile(r"Logger\.(recordOutput|recordMetadata)\(\s*(\"[^\"]*\"|[^\"\s][^,]*)")
DOC_KEY = re.compile(r"^\|\s*`([^`]+)`\s*\|", re.MULTILINE)
CONSTANT = re.compile(r"public static final (?:double|int|long)\s+(\w+)\s*=\s*(-?[\d.]+)\s*;")


def java_sources() -> list[Path]:
    return sorted(JAVA_DIR.rglob("*.java"))


def java_keys() -> set[str]:
    keys: set[str] = set()
    for path in java_sources():
        for call, arg in KEY_CALL.findall(path.read_text(encoding="utf-8")):
            assert arg.startswith('"'), (
                f"{path.name}: {call} key must be a string literal, got {arg}"
            )
            keys.add(arg.strip('"'))
    return keys


def doc_keys() -> set[str]:
    """First-column keys that start with Alea/ (PsiKit built-in keys are not ours)."""
    return {k for k in DOC_KEY.findall(DOC.read_text(encoding="utf-8")) if k.startswith("Alea/")}


def java_constants() -> dict[str, float]:
    text = (next(p for p in java_sources() if p.name == "Constants.java")).read_text(
        encoding="utf-8"
    )
    return {name: float(value) for name, value in CONSTANT.findall(text)}


def test_java_has_keys() -> None:
    assert java_keys(), "no Logger.recordOutput calls found under robot/"


def test_all_keys_under_alea_prefix() -> None:
    bad = sorted(k for k in java_keys() if not k.startswith("Alea/"))
    assert not bad, f"keys outside Alea/: {bad}"


def test_java_keys_are_documented() -> None:
    missing = sorted(java_keys() - doc_keys())
    assert not missing, f"in Java but not in docs/robot-interface.md: {missing}"


def test_documented_keys_exist_in_java() -> None:
    stale = sorted(doc_keys() - java_keys())
    assert not stale, f"in docs/robot-interface.md but not in Java: {stale}"


def test_java_constants_match_game_values() -> None:
    c = java_constants()
    exact = {
        "RED_HIVE_X_IN": biobuzz.HIVE_X_IN[0],
        "BLUE_HIVE_X_IN": biobuzz.HIVE_X_IN[1],
        "LAUNCH_ANGLE_DEG": math.degrees(biobuzz.LAUNCH_PITCH_RAD),
        "LAUNCHER_EXIT_BEHIND_IN": -biobuzz.LAUNCH_EXIT_X_IN,
    }
    for name, expected in exact.items():
        assert c[name] == pytest.approx(expected, abs=TOL), name
    # The two mouth y values are rounded CAD numbers (0.01 in) that sit
    # symmetrically about the hive pivot y.
    mid = (c["HIVE_AUDIENCE_MOUTH_Y_IN"] + c["HIVE_REAR_MOUTH_Y_IN"]) / 2
    assert mid == pytest.approx(biobuzz.HIVE_Y_IN, abs=0.01)


def test_start_pose_is_on_the_field() -> None:
    consts = java_constants()
    for name in ("START_X_IN", "START_Y_IN"):
        assert 0 <= consts[name] <= biobuzz.FIELD_SIZE_IN, name
    for name in ("HIVE_AUDIENCE_MOUTH_Y_IN", "HIVE_REAR_MOUTH_Y_IN"):
        assert 0 <= consts[name] <= biobuzz.FIELD_SIZE_IN, name


def test_metadata_matches_constants() -> None:
    """Every Alea/Meta key records a Constants field of the same name, so the log can't drift."""
    sample = next(p for p in java_sources() if p.name == "AleaSampleOpMode.java")
    text = sample.read_text(encoding="utf-8")
    pairs = re.findall(
        r'recordMetadata\("Alea/Meta/(\w+)",\s*String\.valueOf\(Constants\.(\w+)\)', text
    )
    assert pairs
    for key, const in pairs:
        camel = "".join(w.capitalize() for w in const.lower().split("_"))
        assert camel == key, f"{key} records {const}"
        assert const in java_constants(), const
