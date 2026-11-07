"""Shared helpers for replaying the dsim hive traces (tests/hifi_traces) through alea.hifi.

Not a test module. `Dev` compares fixture JSON with the port's output: integers, booleans and
strings must match exactly; floats are compared by absolute and relative deviation, recorded so
each test can assert a tolerance and the measured maximum can be reported.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from alea.hifi.hive import HiveState, Vec2, Vec3

TRACES = Path(__file__).parent / "hifi_traces"


def load(name: str) -> dict[str, Any]:
    return json.loads((TRACES / name).read_text(encoding="utf-8"))


class Dev:
    """Accumulates the worst float deviation seen; asserts on any exact-type mismatch."""

    def __init__(self) -> None:
        self.abs_dev = 0.0
        self.rel_dev = 0.0
        self.n_floats = 0

    def cmp(self, actual: Any, expected: Any, where: str = "") -> None:
        if isinstance(expected, dict):
            assert isinstance(actual, dict), f"{where}: expected dict"
            assert set(actual) == set(expected), (
                f"{where}: keys {sorted(actual)} != {sorted(expected)}"
            )
            for k, v in expected.items():
                self.cmp(actual[k], v, f"{where}.{k}")
        elif isinstance(expected, list):
            assert isinstance(actual, (list, tuple)), f"{where}: expected list"
            assert len(actual) == len(expected), f"{where}: length {len(actual)} != {len(expected)}"
            for i, v in enumerate(expected):
                self.cmp(actual[i], v, f"{where}[{i}]")
        elif expected is None or isinstance(expected, (bool, str)):
            assert actual == expected and type(actual) is type(expected), (
                f"{where}: {actual!r} != {expected!r}"
            )
        elif isinstance(expected, int) and isinstance(actual, int) and not isinstance(actual, bool):
            assert actual == expected, f"{where}: {actual!r} != {expected!r}"
        else:
            assert isinstance(actual, (int, float)) and not isinstance(actual, bool), (
                f"{where}: {actual!r}"
            )
            d = abs(float(actual) - float(expected))
            self.n_floats += 1
            self.abs_dev = max(self.abs_dev, d)
            if expected != 0:
                self.rel_dev = max(self.rel_dev, d / abs(float(expected)))


def hive_from_json(h: dict[str, Any]) -> HiveState:
    return HiveState(
        up=h["up"],
        contents=tuple(h.get("contents", ())),
        tips=h["tips"],
        tipping=h["tipping"],
        released=h["released"],
        swing_rate=h.get("swingRate"),
    )


def hive_to_json(h: HiveState, *, contents: bool = True) -> dict[str, Any]:
    d: dict[str, Any] = {"up": h.up}
    if contents:
        d["contents"] = list(h.contents)
    d.update(tips=h.tips, tipping=h.tipping, released=h.released)
    if h.swing_rate is not None:  # dsim's undefined swingRate: key absent
        d["swingRate"] = h.swing_rate
    return d


def vec2(d: dict[str, Any]) -> Vec2:
    return Vec2(d["x"], d["y"])


def vec3(d: dict[str, Any]) -> Vec3:
    return Vec3(d["x"], d["y"], d["z"])


def vec_json(v: Vec2 | Vec3) -> dict[str, float]:
    return dict(vars(v))


def mulberry32(seed: int) -> Callable[[], float]:
    """The fixture's generator (spill.json inputs.rng.mulberry32.source), 32-bit integer ops."""
    mask = 0xFFFFFFFF
    a = seed & mask

    def imul(x: int, y: int) -> int:
        return (x * y) & mask

    def rng() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & mask
        t = a
        t = imul(t ^ (t >> 15), t | 1)
        t ^= (t + imul(t ^ (t >> 7), t | 61)) & mask
        return ((t ^ (t >> 14)) & mask) / 4294967296

    return rng


def cycled(values: list[float]) -> Callable[[], float]:
    k = 0

    def rng() -> float:
        nonlocal k
        v = values[k % len(values)]
        k += 1
        return v

    return rng
