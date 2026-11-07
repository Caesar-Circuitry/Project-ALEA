"""Heuristic launch detector (decision 0007).

The robot contract has no shot-fired key, so launches are inferred from the flywheel: when a
ball leaves, the flywheel loses speed in a few loops and then recovers. We look for a sharp
drop of a `HardwareMap/<motor>/velocity` signal (ticks per second, logged by PsiKit's hardware
wrappers; the exact key name is an assumption, see the decision record).

Algorithm, per candidate velocity key (absolute values):
  1. For each sample, the drop is (highest value in the previous `window_s`) - (this value).
  2. The first sample whose drop is at least `min_dip_ticks_per_sec` is a launch candidate and
     its time is the launch time. Candidates closer than `refractory_s` to the previous launch
     are ignored (one ball produces one dip, not several).
  3. `after` is the lowest value in the next `settle_s`. If it fell below
     `min_remaining_fraction` of `before`, the flywheel was switched off or stalled, not
     dipped by a ball, and the candidate is dropped.
With several matching keys, a key whose name contains launch/fly/shoot wins; otherwise the key
with the highest peak velocity.
"""

from __future__ import annotations

import fnmatch
from bisect import bisect_left
from dataclasses import dataclass, field

from alea.data.logdata import LogData


@dataclass(frozen=True)
class LaunchConfig:
    key_pattern: str = "HardwareMap/*/velocity"  # fnmatch, case-insensitive
    min_dip_ticks_per_sec: float = 80.0
    window_s: float = 0.1
    refractory_s: float = 0.5
    settle_s: float = 0.15
    min_remaining_fraction: float = 0.4
    preferred_name_parts: tuple[str, ...] = ("launch", "fly", "shoot")


@dataclass(frozen=True)
class DetectedLaunch:
    t_s: float
    ticks_per_sec_before: float
    ticks_per_sec_after: float

    @property
    def dip_ticks_per_sec(self) -> float:
        return self.ticks_per_sec_before - self.ticks_per_sec_after


@dataclass
class LaunchResult:
    launches: list[DetectedLaunch] = field(default_factory=list)
    key: str | None = None
    note: str = ""


def _normalise(key: str) -> str | None:
    i = key.find("HardwareMap/")
    return key[i:] if i >= 0 else None


def detect_in_signal(
    samples: list[tuple[float, float]], config: LaunchConfig | None = None
) -> list[DetectedLaunch]:
    """Detect launches in (t_s, ticks_per_sec) samples sorted by time."""
    cfg = config or LaunchConfig()
    times = [t for t, _ in samples]
    values = [abs(v) for _, v in samples]
    out: list[DetectedLaunch] = []
    last_t = float("-inf")
    for i, (t_s, v) in enumerate(zip(times, values, strict=True)):
        if t_s - last_t < cfg.refractory_s:
            continue
        lo = bisect_left(times, t_s - cfg.window_s)
        before = max(values[lo : i + 1])
        if before - v < cfg.min_dip_ticks_per_sec:
            continue
        hi = bisect_left(times, t_s + cfg.settle_s)
        after = min(values[i : max(hi, i + 1)])
        if after < cfg.min_remaining_fraction * before:
            continue
        out.append(DetectedLaunch(t_s, before, after))
        last_t = t_s
    return out


def detect_launches(data: LogData, config: LaunchConfig | None = None) -> LaunchResult:
    """Find launches in a decoded log; zero launches plus a note if no velocity key exists."""
    cfg = config or LaunchConfig()
    pattern = cfg.key_pattern.lower()
    candidates: dict[str, list[tuple[float, float]]] = {}
    for key, entries in data.entries.items():
        norm = _normalise(key)
        if norm is None or not fnmatch.fnmatchcase(norm.lower(), pattern):
            continue
        nums = [
            (t, float(v))
            for t, v in entries
            if isinstance(v, int | float) and not isinstance(v, bool)
        ]
        if nums:
            candidates[key] = sorted(nums)
    if not candidates:
        return LaunchResult(note=f"no flywheel velocity key matching {cfg.key_pattern!r}")

    def rank(key: str) -> tuple[bool, float]:
        preferred = any(p in key.lower() for p in cfg.preferred_name_parts)
        return preferred, max(abs(v) for _, v in candidates[key])

    best = max(candidates, key=rank)
    found = detect_in_signal(candidates[best], cfg)
    note = f"velocity key {best!r}: {len(found)} launches"
    if len(candidates) > 1:
        note += f" (chosen of {len(candidates)} matching keys)"
    return LaunchResult(found, best, note)
