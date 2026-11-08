import csv
import json

import pytest
import yaml

from alea.matchsim.run import load_config, main, match_seeds


def test_cli_writes_outputs(tmp_path, capsys):
    out = tmp_path / "res"
    assert main(["--matches", "6", "--seed", "3", "--out", str(out)]) == 0
    with (out / "matches.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 6
    assert {"match", "seed", "red_score", "red_tips", "red_tip_teleop"} <= set(rows[0])
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["n_matches"] == 6
    assert summary["our_score"]["mean"] >= 0
    assert "our score" in capsys.readouterr().out


def test_cli_is_reproducible(tmp_path):
    for d in ("a", "b"):
        main(["--matches", "5", "--seed", "9", "--out", str(tmp_path / d)])
    first = (tmp_path / "a" / "matches.csv").read_text(encoding="utf-8")
    assert first == (tmp_path / "b" / "matches.csv").read_text(encoding="utf-8")
    assert len(set(match_seeds(9, 50))) == 50


def test_config_file(tmp_path):
    cfg = {
        "shot_model": {"type": "placeholder", "aim_noise_deg": 1.0},
        "red": [{"type": "profile", "name": "x", "balls_per_load": 2, "pickup_spot_in": [70, 30]}],
        "blue": [{"type": "noop", "leave": True}],
    }
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    setup = load_config(path)
    assert setup.red[0].balls_per_load == 2
    assert setup.red[0].pickup_spot_in == (70, 30)
    assert main(["--matches", "3", "--config", str(path), "--out", str(tmp_path / "o")]) == 0


def test_bad_config_key_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump({"red": [{"type": "profile", "speeed": 1}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown key"):
        load_config(path)
