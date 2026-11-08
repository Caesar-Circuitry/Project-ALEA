"""Run many simulated matches: `python -m alea.matchsim --matches N --seed S [--config c.yaml]`.

Red robot 0 is "ours". Writes `matches.csv` (one row per match) and `summary.json` to the output
directory (default `results/matchsim/`, git-ignored). The YAML schema is in README.md.
"""

import argparse
import csv
import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from alea.matchsim.match import BREAKDOWN_KEYS, MatchResult, simulate_match
from alea.matchsim.policies import ConstantCyclePolicy, NoOpPolicy
from alea.matchsim.robot import RobotProfile
from alea.matchsim.rules import TipBehaviour
from alea.matchsim.shots import PlaceholderShotModel, ShotSuccessModel, TableShotModel

DEFAULT_OUT_DIR = Path("results") / "matchsim"

DEFAULT_CONFIG: dict[str, Any] = {
    "shot_model": {"type": "placeholder"},
    "red": [
        {"type": "profile", "name": "ours"},
        {"type": "constant_cycle", "name": "partner", "cycle_time_s": 20.0, "make_rate": 0.5},
    ],
    "blue": [
        {"type": "constant_cycle", "name": "opp1", "cycle_time_s": 22.0, "make_rate": 0.45},
        {"type": "constant_cycle", "name": "opp2", "cycle_time_s": 25.0, "make_rate": 0.4},
    ],
}

_TUPLE_FIELDS = {
    "shoot_spot_audience_up_in",
    "shoot_spot_rear_up_in",
    "pickup_spot_in",
    "start_spot_in",
}


def _kwargs(cls: type, spec: dict[str, Any]) -> dict[str, Any]:
    names = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    unknown = set(spec) - names
    if unknown:
        raise ValueError(
            f"unknown key(s) {sorted(unknown)} for {cls.__name__}; valid: {sorted(names)}"
        )
    return {k: (tuple(v) if k in _TUPLE_FIELDS and v is not None else v) for k, v in spec.items()}


def build_robot(spec: dict[str, Any]) -> Any:
    spec = dict(spec)
    kind = spec.pop("type")
    if kind == "profile":
        return RobotProfile(**_kwargs(RobotProfile, spec))
    if kind == "constant_cycle":
        return ConstantCyclePolicy(**_kwargs(ConstantCyclePolicy, spec))
    if kind == "noop":
        return NoOpPolicy(**_kwargs(NoOpPolicy, spec))
    raise ValueError(f"unknown robot type {kind!r}; use profile, constant_cycle or noop")


def build_shot_model(spec: dict[str, Any]) -> ShotSuccessModel:
    spec = dict(spec)
    kind = spec.pop("type", "placeholder")
    if kind == "placeholder":
        return PlaceholderShotModel(**spec)
    if kind == "table":
        return TableShotModel.from_study_summary(spec.pop("summary_dir"), **spec)
    raise ValueError(f"unknown shot_model type {kind!r}; use placeholder or table")


@dataclass
class MatchSetup:
    red: list[Any]
    blue: list[Any]
    shot_model: ShotSuccessModel
    tip_behaviour: TipBehaviour
    raw: dict[str, Any]


def load_config(path: str | Path | None) -> MatchSetup:
    raw = DEFAULT_CONFIG
    if path is not None:
        with Path(path).open(encoding="utf-8") as fh:
            raw = {**DEFAULT_CONFIG, **(yaml.safe_load(fh) or {})}
    return MatchSetup(
        red=[build_robot(s) for s in raw["red"]],
        blue=[build_robot(s) for s in raw["blue"]],
        shot_model=build_shot_model(raw["shot_model"]),
        tip_behaviour=TipBehaviour(raw.get("tip_behaviour", "spill_to_field")),
        raw=raw,
    )


def match_seeds(seed: int, n: int) -> list[int]:
    """One independent integer seed per match, derived from the run seed."""
    return [int(c.generate_state(1)[0]) for c in np.random.SeedSequence(seed).spawn(n)]


def _row(i: int, r: MatchResult) -> dict[str, Any]:
    row: dict[str, Any] = {
        "match": i,
        "seed": r.seed,
        "red_score": r.red_score,
        "blue_score": r.blue_score,
        "red_tips": r.tips["red"],
        "blue_tips": r.tips["blue"],
        "red_tips_auto": r.tips_auto["red"],
        "red_rp": r.ranking_points["red"],
        "pollen_left": r.pollen_left,
    }
    for k in BREAKDOWN_KEYS:
        row[f"red_{k}"] = r.breakdown["red"][k]
    return row


def _mean_sd(values: list[float]) -> dict[str, float]:
    a = np.asarray(values, dtype=float)
    return {"mean": float(a.mean()), "sd": float(a.std(ddof=1)) if len(a) > 1 else 0.0}


def run_matches(setup: MatchSetup, n_matches: int, seed: int, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, s in enumerate(match_seeds(seed, n_matches)):
        res = simulate_match(setup.red, setup.blue, setup.shot_model, s, setup.tip_behaviour)
        rows.append(_row(i, res))
    with (out_dir / "matches.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    col = lambda k: [r[k] for r in rows]  # noqa: E731
    summary: dict[str, Any] = {
        "n_matches": n_matches,
        "seed": seed,
        "our_score": _mean_sd(col("red_score")),
        "opponent_score": _mean_sd(col("blue_score")),
        "our_tips": _mean_sd(col("red_tips")),
        "our_ranking_points": _mean_sd(col("red_rp")),
        "win_rate": float(np.mean([r["red_score"] > r["blue_score"] for r in rows])),
        "our_breakdown": {k: _mean_sd(col(f"red_{k}")) for k in BREAKDOWN_KEYS},
        "config": setup.raw,
    }
    with (out_dir / "summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m alea.matchsim", description=__doc__)
    ap.add_argument("--matches", type=int, default=100)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--config", type=Path, default=None, help="YAML robot/policy/shot-model config")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args(argv)
    if args.matches < 1:
        ap.error("--matches must be >= 1")
    summary = run_matches(load_config(args.config), args.matches, args.seed, args.out)
    s = summary
    print(f"{s['n_matches']} matches, seed {s['seed']}")
    print(f"our score  {s['our_score']['mean']:.1f} +- {s['our_score']['sd']:.1f}")
    print(f"opp score  {s['opponent_score']['mean']:.1f} +- {s['opponent_score']['sd']:.1f}")
    print(f"our tips   {s['our_tips']['mean']:.2f} +- {s['our_tips']['sd']:.2f}")
    print(f"win rate   {s['win_rate']:.2f}")
    for k, v in s["our_breakdown"].items():
        print(f"  {k:14s} {v['mean']:6.2f} +- {v['sd']:.2f}")
    print(f"wrote {args.out / 'matches.csv'} and {args.out / 'summary.json'}")
    return 0
