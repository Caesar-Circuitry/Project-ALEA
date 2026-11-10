"""Synthetic match-reflection report and loader/validator (roadmap phase 6).

The report shape is the phase-5 contract written by ``alea/analysis/reflection``.
Reports are text/JSON only; no video frames are ever stored in them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA_VERSION = 1
SOURCES = ("measured", "inferred")
SEVERITIES = ("high", "medium", "low")
FILLED_BY = ("inferred", "none")
_TOP_KEYS = ("schema_version", "match", "summary", "metrics", "timeline", "findings", "gaps")
_MATCH_KEYS = ("event_code", "match_label", "alliance", "team_number")
_METRIC_KEYS = ("value", "unit", "expected", "source", "note")
_TIMELINE_KEYS = ("t_s", "kind", "detail", "source")
_FINDING_KEYS = ("title", "severity", "evidence", "suggestion", "source")
_GAP_KEYS = ("what", "why_missing", "filled_by")


def synthetic_report(seed: int = 24331) -> dict[str, Any]:
    """Return a seeded, plausible report: ~12 launches, one long idle gap, two tips."""
    rng = np.random.default_rng(seed)
    timeline: list[dict[str, Any]] = [
        {"t_s": 0.0, "kind": "phase", "detail": "Autonomous starts", "source": "measured"},
        {"t_s": 30.0, "kind": "phase", "detail": "Driver-controlled starts", "source": "measured"},
    ]
    t_s = 4.0
    for i in range(12):
        t_s += float(rng.uniform(3.0, 9.0)) + (28.0 if i == 7 else 0.0)
        if i == 7:
            timeline.append(
                {
                    "t_s": round(t_s - 28.0, 1),
                    "kind": "idle_gap",
                    "detail": "No launches for 28 s",
                    "source": "inferred",
                }
            )
        timeline.append(
            {
                "t_s": round(t_s, 1),
                "kind": "launch",
                "detail": f"Launch {i + 1}",
                "source": "measured" if i % 3 else "inferred",
            }
        )
    timeline.append({"t_s": 71.2, "kind": "tip", "detail": "Hive tipped", "source": "measured"})
    timeline.append({"t_s": 118.4, "kind": "tip", "detail": "Hive tipped", "source": "inferred"})
    timeline.append({"t_s": 150.0, "kind": "phase", "detail": "Match ends", "source": "measured"})
    timeline.sort(key=lambda e: e["t_s"])
    return {
        "schema_version": SCHEMA_VERSION,
        "match": {
            "event_code": "USALATQ",
            "match_label": "Q7",
            "alliance": "red",
            "team_number": 24331,
        },
        "summary": "Synthetic demo: 12 launches, one 28 s idle gap mid-match, two tips.",
        "metrics": {
            "launches": {
                "value": 12,
                "unit": "count",
                "expected": 15,
                "source": "measured",
                "note": "",
            },
            "mean_cycle_time": {
                "value": 8.4,
                "unit": "s",
                "expected": 6.0,
                "source": "inferred",
                "note": "from launch timestamps",
            },
            "longest_idle_gap": {
                "value": 28.0,
                "unit": "s",
                "expected": 8.0,
                "source": "measured",
                "note": "",
            },
            "tips": {
                "value": 2,
                "unit": "count",
                "expected": 0,
                "source": "measured",
                "note": "",
            },
        },
        "timeline": timeline,
        "findings": [
            {
                "title": "Long idle gap",
                "severity": "high",
                "evidence": "No launches between two consecutive shots for 28 s.",
                "suggestion": "Pre-position for the next pickup during the gap.",
                "source": "measured",
            },
            {
                "title": "Two tips",
                "severity": "medium",
                "evidence": "Tips at ~71 s and ~118 s.",
                "suggestion": "Review approach angle before contact.",
                "source": "inferred",
            },
            {
                "title": "Cycle time above target",
                "severity": "low",
                "evidence": "Mean cycle 8.4 s vs 6.0 s expected.",
                "suggestion": "Check flywheel recovery between shots.",
                "source": "inferred",
            },
        ],
        "gaps": [
            {
                "what": "Launch results (hit or miss)",
                "why_missing": "No clear view of the target in video.",
                "filled_by": "inferred",
            },
            {
                "what": "Partner robot actions",
                "why_missing": "Not logged.",
                "filled_by": "none",
            },
        ],
    }


def _check_keys(obj: Any, keys: tuple[str, ...], where: str, problems: list[str]) -> bool:
    if not isinstance(obj, dict):
        problems.append(f"{where}: expected an object")
        return False
    for k in keys:
        if k not in obj:
            problems.append(f"{where}: missing key '{k}'")
    return True


def validate_report(d: Any) -> list[str]:
    """Return a list of problems; an empty list means the report is valid."""
    problems: list[str] = []
    if not _check_keys(d, _TOP_KEYS, "report", problems):
        return problems
    if d.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"report: schema_version must be {SCHEMA_VERSION}")
    _check_keys(d.get("match"), _MATCH_KEYS, "match", problems)

    def check_source(item: dict[str, Any], where: str) -> None:
        if "source" in item and item["source"] not in SOURCES:
            problems.append(f"{where}: bad source {item['source']!r}")

    metrics = d.get("metrics", {})
    if isinstance(metrics, dict):
        for name, m in metrics.items():
            if _check_keys(m, _METRIC_KEYS, f"metrics.{name}", problems):
                check_source(m, f"metrics.{name}")
    else:
        problems.append("metrics: expected an object")
    for key, keys in (("timeline", _TIMELINE_KEYS), ("findings", _FINDING_KEYS)):
        rows = d.get(key, [])
        if not isinstance(rows, list):
            problems.append(f"{key}: expected a list")
            continue
        for i, row in enumerate(rows):
            if _check_keys(row, keys, f"{key}[{i}]", problems):
                check_source(row, f"{key}[{i}]")
                if key == "findings" and row.get("severity") not in SEVERITIES:
                    problems.append(f"{key}[{i}]: bad severity {row.get('severity')!r}")
    gaps = d.get("gaps", [])
    if isinstance(gaps, list):
        for i, g in enumerate(gaps):
            if _check_keys(g, _GAP_KEYS, f"gaps[{i}]", problems) and g.get("filled_by") not in (
                FILLED_BY
            ):
                problems.append(f"gaps[{i}]: bad filled_by {g.get('filled_by')!r}")
    else:
        problems.append("gaps: expected a list")
    return problems


def load_report(path: str | Path) -> dict[str, Any]:
    """Read a report JSON file; raise ``ValueError`` if schema_version is not 1."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version in {path}; expected {SCHEMA_VERSION}")
    return data
