"""Format-neutral result of reading a robot log (RLOG or WPILOG)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Value = bool | int | float | str | bytes | list[Any]


@dataclass
class LogData:
    """Every key of a log with its timestamped values.

    `entries` maps the key exactly as logged to a list of (t_s, value) in file order; t_s is
    seconds from the start of the log's clock.
    """

    format: str
    format_version: str
    entries: dict[str, list[tuple[float, Value]]] = field(default_factory=dict)
    types: dict[str, str] = field(default_factory=dict)
    truncated: bool = False

    def add(self, key: str, type_name: str, t_s: float, value: Value) -> None:
        self.types.setdefault(key, type_name)
        self.entries.setdefault(key, []).append((t_s, value))

    @property
    def duration_s(self) -> float:
        times = [s[-1][0] for s in self.entries.values() if s]
        return max(times, default=0.0)
