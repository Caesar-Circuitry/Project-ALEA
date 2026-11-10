"""Tests for alea.analysis.calibration_report."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from alea.analysis.calibration_report import (
    build_report,
    main,
    render_markdown,
    write_report,
)
from alea.analysis.efficiency import CSV_COLUMNS, read_measurements_csv
from tests.test_analysis_efficiency import make_rows


def test_report_json_and_markdown():
    rows = make_rows(11, n_sessions=4)
    report = build_report(rows, seed=1, n_boot=200)
    json.dumps(report, allow_nan=False)
    assert report["inputs"]["n_sessions"] == 4
    assert report["efficiency"]["vs_sim"]["sim_inside_ci95"] is False
    assert report["drag"]["sim_value_per_s"] == 0.05
    assert any("placeholder" in c for c in report["caveats"])
    assert any("tag scale" in c for c in report["caveats"])
    md = render_markdown(report)
    mean = report["efficiency"]["hierarchical"]["mean"]
    assert f"{mean:.4f}" in md
    assert "Calibration report" in md and "Caveats" in md


def test_small_sample_warning_and_empty():
    report = build_report(make_rows(12, n_sessions=1)[:5], n_boot=50)
    assert any("Only 5" in w for w in report["warnings"])
    empty = build_report([], n_boot=50)
    json.dumps(empty, allow_nan=False)
    assert render_markdown(empty)


def test_write_report_and_cli(tmp_path: Path):
    rows = make_rows(13, n_sessions=3)
    paths = write_report(rows, tmp_path / "a", seed=2, n_boot=100)
    for p in paths.values():
        assert p.exists() and p.stat().st_size > 0
    assert paths["histogram"].suffix == ".png"

    csv_path = tmp_path / "m.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, restval="")
        w.writeheader()
        for r in rows:
            w.writerow({k: v for k, v in r.items() if k in CSV_COLUMNS})
    assert len(read_measurements_csv(csv_path)) == len(rows)
    assert main([str(csv_path), "--out", str(tmp_path / "b"), "--n-boot", "100"]) == 0
    assert (tmp_path / "b" / "calibration_report.json").exists()
