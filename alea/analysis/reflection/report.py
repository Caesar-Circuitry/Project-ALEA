"""Turn a MatchTimeline and a Baseline into the report JSON (schema_version 1)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from alea.analysis.reflection.baseline import Baseline, ExpectedPoints, expected_points
from alea.analysis.reflection.timeline import (
    IDLE_GAP_S,
    INFERRED,
    MEASURED,
    UNDER_SPEED_FRACTION,
    MatchTimeline,
)

SCHEMA_VERSION = 1

# placeholder thresholds, tuned on synthetic data only
LONG_IDLE_S = 15.0  # an idle gap this long is a high finding
UNDER_SPEED_SHARE = 0.25  # share of launches under-speed that triggers a finding
UNAIMED_SHARE = 0.25
FAR_SHOT_IN = 60.0
FAR_SHARE = 0.4
FAR_LOW_P = 0.4
TIP_MIN_EXPECTED_BALLS = 3.0

_META_KEYS = ("event_code", "match_label", "alliance", "team_number")
_SEVERITIES = ("high", "medium", "low")
_SOURCES = (MEASURED, INFERRED)


def _metric(value: float, unit: str, source: str, note: str = "", expected: float | None = None):
    return {
        "value": float(value),
        "unit": unit,
        "expected": None if expected is None else float(expected),
        "source": source,
        "note": note,
    }


def _finding(title, severity, evidence, suggestion, source):
    return dict(
        title=title, severity=severity, evidence=evidence, suggestion=suggestion, source=source
    )


def _gap(what: str, why: str, filled_by: str) -> dict:
    return {"what": what, "why_missing": why, "filled_by": filled_by}


def _metrics(tl: MatchTimeline, exp: ExpectedPoints | None) -> dict[str, dict]:
    m: dict[str, dict] = {}
    launches = tl.launches
    if tl.log_present:
        m["launch_count"] = _metric(
            len(launches), "count", MEASURED, "launches detected in the log"
        )
        m["log_to_match_offset_s"] = _metric(
            tl.offset_s, "s", tl.offset_source, "match time = log time + this offset"
        )
    if launches:
        cyc = tl.cycle_times_s
        if cyc:
            m["cycle_time_mean_s"] = _metric(
                np.mean(cyc), "s", MEASURED, f"{len(cyc)} intervals up to {IDLE_GAP_S:g} s"
            )
            m["cycle_time_p90_s"] = _metric(np.percentile(cyc, 90), "s", MEASURED)
        gaps = tl.idle_gaps
        longest = max(gaps, key=lambda g: g.length_s, default=None)
        m["longest_idle_gap_s"] = _metric(
            longest.length_s if longest else 0.0,
            "s",
            MEASURED,
            "longest time between launches" + ("" if longest else f"; none over {IDLE_GAP_S:g} s"),
        )
        if longest:
            m["longest_idle_gap_start_s"] = _metric(
                longest.start_s, "s", tl.offset_source, "match time the gap began"
            )
        fracs = [launch.speed_fraction for launch in launches if launch.speed_fraction is not None]
        if fracs:
            under = sum(f < UNDER_SPEED_FRACTION for f in fracs) / len(fracs)
            m["fraction_launches_under_setpoint"] = _metric(
                under,
                "fraction",
                MEASURED,
                f"flywheel under {100 * UNDER_SPEED_FRACTION:g}% of the LUT setpoint when it fired",
                expected=0.0,
            )
        aimed = [launch.aimed for launch in launches if launch.aimed is not None]
        if aimed:
            m["fraction_aimed"] = _metric(
                sum(aimed) / len(aimed),
                "fraction",
                MEASURED,
                "launches with Alea/Aim/Aimed true",
                expected=1.0,
            )
        dists = [launch.distance_in for launch in launches if launch.distance_in is not None]
        if dists:
            m["mean_distance_in"] = _metric(np.mean(dists), "in", MEASURED)
    if exp is not None and launches:
        m["expected_made_balls"] = _metric(
            exp.expected_made_balls, "balls", exp.source, "sum of baseline make probabilities"
        )
    if exp is not None and exp.tips_observed is not None:
        m["tips_observed"] = _metric(exp.tips_observed, "count", MEASURED, "from overlay events")
    if exp is not None and exp.points_vs_expected_pts is not None:
        m["points_vs_expected_pts"] = _metric(
            exp.points_vs_expected_pts,
            "pts",
            exp.source,
            f"overlay score {exp.observed_score_pts:g} minus expected",
            expected=exp.expected_total_pts,
        )
    return m


def _findings(tl: MatchTimeline, baseline: Baseline, exp: ExpectedPoints | None) -> list[dict]:
    out: list[dict] = []
    launches = tl.launches
    gaps = tl.idle_gaps
    if gaps:
        g = max(gaps, key=lambda x: x.length_s)
        sev = "high" if g.length_s >= LONG_IDLE_S else "low"
        out.append(
            _finding(
                "Long gap without a launch",
                sev,
                f"{g.length_s:.1f} s between launches starting at match time {g.start_s:.0f} s; "
                f"{len(gaps)} gap(s) over {IDLE_GAP_S:g} s",
                "Find out what the robot was doing in that gap (collecting, defence, a stall) and "
                "plan a faster return to a shooting spot.",
                tl.offset_source,
            )
        )
    fracs = [launch.speed_fraction for launch in launches if launch.speed_fraction is not None]
    if fracs:
        n_under = sum(f < UNDER_SPEED_FRACTION for f in fracs)
        if n_under / len(fracs) >= UNDER_SPEED_SHARE:
            out.append(
                _finding(
                    "Firing before the flywheel is up to speed",
                    "medium",
                    f"{n_under} of {len(fracs)} launches below {100 * UNDER_SPEED_FRACTION:g}% "
                    f"of the setpoint (mean {100 * float(np.mean(fracs)):.0f}%)",
                    "Wait for the flywheel to recover after each ball, or hold fire until the "
                    "speed is within 5% of the setpoint.",
                    MEASURED,
                )
            )
    aimed = [launch.aimed for launch in launches if launch.aimed is not None]
    if aimed and (len(aimed) - sum(aimed)) / len(aimed) >= UNAIMED_SHARE:
        out.append(
            _finding(
                "Firing before the turret/heading is aimed",
                "medium",
                f"{len(aimed) - sum(aimed)} of {len(aimed)} launches had Aimed false",
                "Let auto-aim settle before pressing fire.",
                MEASURED,
            )
        )
    far = [
        launch.distance_in
        for launch in launches
        if launch.distance_in is not None and launch.distance_in > FAR_SHOT_IN
    ]
    known = [launch for launch in launches if launch.distance_in is not None]
    if known and far:
        far_p = float(np.mean([baseline.make_probability(d) for d in far]))
        if len(far) / len(known) >= FAR_SHARE and far_p < FAR_LOW_P:
            out.append(
                _finding(
                    "Many shots from far away",
                    "medium",
                    f"{len(far)} of {len(known)} launches beyond {FAR_SHOT_IN:g} in, where the "
                    f"baseline make rate averages {100 * far_p:.0f}% "
                    f"(about {100 * baseline.make_probability(48):.0f}% at 48 in)",
                    "Drive closer before shooting when the lane is open.",
                    baseline.source,
                )
            )
    if (
        exp is not None
        and exp.tips_observed == 0
        and exp.expected_made_balls >= TIP_MIN_EXPECTED_BALLS
    ):
        out.append(
            _finding(
                "No tip although the alliance was scoring balls",
                "low",
                f"0 tips in the overlay events; about {exp.expected_made_balls:.1f} balls expected "
                "to be made",
                "Check whether a tip was available and whether going for it was worth the time.",
                INFERRED,
            )
        )
    return out


def _gaps(tl: MatchTimeline, baseline: Baseline, exp: ExpectedPoints | None) -> list[dict]:
    g: list[dict] = []
    if not tl.log_present:
        g.append(
            _gap("robot log", "no log was given; launches, cadence and speed not computed", "none")
        )
    elif not tl.launches:
        g.append(_gap("launches", "the detector found none in the log", "none"))
    if not tl.overlay_present:
        g.append(
            _gap(
                "overlay events",
                "none given; phases come from nominal durations and the "
                "log is assumed to start with the match",
                INFERRED if tl.log_present else "none",
            )
        )
        g.append(
            _gap("tips and score", "tips and the final score come from overlay events", "none")
        )
    elif tl.offset_source == INFERRED:
        g.append(
            _gap(
                "log to match clock offset",
                "too few launch and score pairs to confirm it",
                INFERRED,
            )
        )
    if tl.overlay_present and tl.alliance is None:
        g.append(_gap("alliance", "not given; overlay events of both alliances are mixed", "none"))
    if baseline.source == INFERRED:
        g.append(_gap("baseline make rate by distance", baseline.note, INFERRED))
    if exp is not None and exp.launches_without_distance:
        g.append(
            _gap(
                "launch distance",
                f"{exp.launches_without_distance} launch(es) had no "
                "Aim sample; mean make rate used",
                INFERRED,
            )
        )
    g.append(
        _gap(
            "field state from video",
            "balls and robot positions are not read from video yet",
            "none",
        )
    )
    return g


def _summary(tl: MatchTimeline, metrics: dict, findings: list[dict]) -> str:
    if not tl.log_present:
        return "No robot log was given, so only overlay events could be summarised."
    parts = [f"{len(tl.launches)} launches detected"]
    if "cycle_time_mean_s" in metrics:
        parts.append(f"mean cycle {metrics['cycle_time_mean_s']['value']:.1f} s")
    if "points_vs_expected_pts" in metrics:
        d = metrics["points_vs_expected_pts"]["value"]
        parts.append(f"{d:+.0f} points against the baseline expectation")
    high = sum(f["severity"] == "high" for f in findings)
    parts.append(f"{len(findings)} finding(s), {high} high")
    return "; ".join(parts) + "."


def build_report(timeline: MatchTimeline, baseline: Baseline, match_meta: dict | None) -> dict:
    meta = {k: (match_meta or {}).get(k) for k in _META_KEYS}
    exp = expected_points(timeline, baseline) if timeline.log_present else None
    if exp is None and timeline.overlay_present:
        exp = expected_points(timeline, baseline)
    metrics = _metrics(timeline, exp)
    findings = _findings(timeline, baseline, exp)
    return {
        "schema_version": SCHEMA_VERSION,
        "match": meta,
        "summary": _summary(timeline, metrics, findings),
        "metrics": metrics,
        "timeline": [
            {"t_s": round(e.t_s, 2), "kind": e.kind, "detail": e.detail, "source": e.source}
            for e in timeline.events()
        ],
        "findings": findings,
        "gaps": _gaps(timeline, baseline, exp),
    }


def validate_report(d: dict) -> list[str]:
    """Problems with a report dict; empty when it matches the schema."""
    p: list[str] = []
    if d.get("schema_version") != SCHEMA_VERSION:
        p.append("schema_version must be 1")
    match = d.get("match")
    if not isinstance(match, dict) or set(match) != set(_META_KEYS):
        p.append(f"match must have exactly {_META_KEYS}")
    elif match["alliance"] not in (None, "red", "blue"):
        p.append("match.alliance must be red, blue or null")
    if not isinstance(d.get("summary"), str):
        p.append("summary must be a string")
    metrics = d.get("metrics")
    if not isinstance(metrics, dict):
        p.append("metrics must be an object")
        metrics = {}
    for name, v in metrics.items():
        if not isinstance(v, dict) or set(v) != {"value", "unit", "expected", "source", "note"}:
            p.append(f"metric {name}: wrong keys")
            continue
        if not isinstance(v["value"], int | float) or isinstance(v["value"], bool):
            p.append(f"metric {name}: value must be a number")
        if v["expected"] is not None and not isinstance(v["expected"], int | float):
            p.append(f"metric {name}: expected must be a number or null")
        if v["source"] not in _SOURCES:
            p.append(f"metric {name}: bad source")
    for i, e in enumerate(d.get("timeline") or []):
        if not isinstance(e.get("t_s"), int | float) or e.get("source") not in _SOURCES:
            p.append(f"timeline[{i}]: bad t_s or source")
        if not isinstance(e.get("kind"), str) or not isinstance(e.get("detail"), str):
            p.append(f"timeline[{i}]: kind and detail must be strings")
    for i, f in enumerate(d.get("findings") or []):
        if f.get("severity") not in _SEVERITIES or f.get("source") not in _SOURCES:
            p.append(f"findings[{i}]: bad severity or source")
        for k in ("title", "evidence", "suggestion"):
            if not isinstance(f.get(k), str):
                p.append(f"findings[{i}]: {k} must be a string")
    for i, g in enumerate(d.get("gaps") or []):
        if g.get("filled_by") not in (INFERRED, "none"):
            p.append(f"gaps[{i}]: bad filled_by")
    for key in ("timeline", "findings", "gaps"):
        if not isinstance(d.get(key), list):
            p.append(f"{key} must be a list")
    return p


def write_report(d: dict, path: str | Path) -> None:
    problems = validate_report(d)
    if problems:
        raise ValueError("invalid report: " + "; ".join(problems))
    Path(path).write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")


def render_markdown(d: dict) -> str:
    """A readable rendering of the report."""
    m = d["match"]
    lines = [
        "# Match reflection",
        "",
        f"Match {m['match_label'] or '?'} | alliance {m['alliance'] or '?'} | "
        f"team {m['team_number'] or '?'}",
        "",
        d["summary"],
        "",
        "## Findings",
        "",
    ]
    if not d["findings"]:
        lines.append("None from the rules.")
    for f in d["findings"]:
        lines += [
            f"- **{f['title']}** ({f['severity']}, {f['source']}): {f['evidence']}. "
            f"Suggestion: {f['suggestion']}"
        ]
    lines += [
        "",
        "## Metrics",
        "",
        "| metric | value | unit | expected | source |",
        "|---|---|---|---|---|",
    ]
    for name, v in d["metrics"].items():
        exp = "" if v["expected"] is None else f"{v['expected']:.2f}"
        lines.append(f"| {name} | {v['value']:.2f} | {v['unit']} | {exp} | {v['source']} |")
    lines += ["", "## Timeline", ""]
    lines += [
        f"- {e['t_s']:.1f} s {e['kind']}: {e['detail']} ({e['source']})" for e in d["timeline"]
    ]
    lines += ["", "## Gaps", ""]
    lines += [f"- {g['what']}: {g['why_missing']} (filled by {g['filled_by']})" for g in d["gaps"]]
    return "\n".join(lines) + "\n"
