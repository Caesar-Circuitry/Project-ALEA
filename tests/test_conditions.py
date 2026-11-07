from pathlib import Path

import pytest
import yaml

from alea.sim.conditions import DEFAULTS, all_conditions


def test_unknown_condition_key_raises():
    with pytest.raises(ValueError, match="aim_degs") as e:
        all_conditions({"aim_degs": [1.0]})
    assert all(k in str(e.value) for k in DEFAULTS)


def test_known_keys_ok():
    assert len(all_conditions({"aim_deg": [1.0]})) == 24


def test_defaults_match_brev72_yaml():
    path = Path(__file__).resolve().parents[1] / "conf" / "study" / "brev72.yaml"
    conf = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert conf["conditions"] == DEFAULTS
