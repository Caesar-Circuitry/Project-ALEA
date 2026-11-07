"""alea.sim.results: both load paths and the factor averages, on hand-built condition files."""

import csv

import numpy as np
import pytest

from alea.sim import results
from alea.sim.conditions import all_conditions


def _write_study(out, grid, write_csv):
    """Two-by-N tiny study; condition i scores (10 + 10 * i) % of 100 fired shots."""
    conds = all_conditions(grid)
    rows = []
    for c in conds:
        fired = np.full((2, 2), 25, dtype=np.int64)
        tries = fired + 5
        hits = np.zeros((2, 2), dtype=np.int64)
        hits[0, 0] = 10 + 10 * c["id"]
        np.savez_compressed(
            out / f"cond_{c['id']:03d}.npz",
            tries=tries,
            fired=fired,
            hits=hits,
            shots=20,
            seed=1,
            **c,
        )
        with np.load(out / f"cond_{c['id']:03d}.npz") as z:
            rows.append(results.summary_row(c, z))
    if write_csv:
        with (out / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    return rows


GRID = dict(aim_deg=[1.0, 2.0], speed_pct=[2.0], robot_ips=[0.0], ball_in=[2.5], bounce=[0.5])


def test_rebuild_matches_csv(tmp_path):
    csv_dir, npz_dir = tmp_path / "a", tmp_path / "b"
    csv_dir.mkdir()
    npz_dir.mkdir()
    _write_study(csv_dir, GRID, write_csv=True)
    _write_study(npz_dir, GRID, write_csv=False)
    from_csv, rebuilt = results.load_summary(csv_dir), results.load_summary(npz_dir)
    assert from_csv == rebuilt
    r = from_csv[1]
    assert isinstance(r["id"], int) and isinstance(r["fired"], int)
    assert isinstance(r["aim_deg"], float)
    assert (r["shots"], r["fired"], r["scored"]) == (120, 100, 20)
    assert r["pct_scored_of_fired"] == 20.0


def test_missing_study_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        results.load_summary(tmp_path)


def test_factor_effects_and_worst_best(tmp_path):
    grid = dict(GRID, ball_in=[2.5, 2.9])  # ids 0..3: aim x ball
    _write_study(tmp_path, grid, write_csv=False)
    rows = results.load_summary(tmp_path)
    scores = [r["pct_scored_of_fired"] for r in rows]
    assert scores == [10.0, 20.0, 30.0, 40.0]
    eff = results.factor_effects(rows)
    assert eff["aim error (deg)"] == [(1.0, 15.0), (2.0, 35.0)]
    assert eff["ball size (in)"] == [(2.5, 20.0), (2.9, 30.0)]
    assert eff["ball bounce"] == [(0.5, 25.0)]
    worst, best = results.worst_best(rows, n=2)
    assert [r["id"] for r in worst] == [0, 1]
    assert [r["id"] for r in best] == [3, 2]
