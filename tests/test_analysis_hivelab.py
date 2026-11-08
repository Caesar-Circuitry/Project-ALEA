import math

import pytest

from alea.analysis.hivelab import (
    MEASUREMENT_COLUMNS,
    HiveLabFormatError,
    LogLaunch,
    efficiency,
    read_hivelab_csv,
    read_measurements_csv,
    to_measurements,
    wheel_surface_speed_in_s,
    write_measurements_csv,
)
from alea.game.biobuzz import TICKS_TO_IN_S

HEADER = (
    "video,setup,robot,hood_deg,rpm,flywheel_g,shot,burst,index,burst_size,kind,time_s,"
    "v0_in_s,v0_ft_s,angle_deg,apex_in,at_opening_in,result,points,fit_rms_in,drag_per_s,"
    "gravity_check"
)


def _write(tmp_path, header=HEADER):
    lines = [header]
    for i in range(12):
        burst = i // 4
        t = 5.0 + burst * 3.0 + (i % 4) * 0.3
        lines.append(
            f"clip.mp4,s1,bot,40,3000,60,{i},{burst},{i % 4},4,shot,{t},"
            f"{200 + i},{(200 + i) / 12},{45 + i * 0.1},30.5,28,IN,40,0.4,0.2,ok"
        )
    p = tmp_path / "hive.csv"
    p.write_text("\n".join(lines) + "\n")
    return p


def test_parse(tmp_path):
    shots = read_hivelab_csv(_write(tmp_path))
    assert len(shots) == 12
    assert {s.burst_index for s in shots} == {0, 1, 2}
    s = shots[5]
    assert (s.video_file, s.shot_index, s.burst_size, s.result) == ("clip.mp4", 5, 4, "IN")
    assert s.v_exit_in_s == 205 and s.drag_per_s == 0.2 and s.extra["rpm"] == "3000"


def test_mapping_override(tmp_path):
    p = _write(tmp_path, HEADER.replace("v0_in_s", "speed"))
    with pytest.raises(HiveLabFormatError):
        read_hivelab_csv(p)
    assert read_hivelab_csv(p, {"v_exit_in_s": "speed"})[0].v_exit_in_s == 200


def test_missing_required_column(tmp_path):
    p = _write(tmp_path, HEADER.replace("angle_deg", "ang"))
    with pytest.raises(HiveLabFormatError, match="angle_deg"):
        read_hivelab_csv(p)


def test_measurement_round_trip(tmp_path):
    shots = read_hivelab_csv(_write(tmp_path))
    joins = [LogLaunch(10.0 + i, 1000.0, 800.0, 200.0, launch_id=i) if i < 6 else None
             for i in range(12)]  # fmt: skip
    rows = to_measurements(shots, joins)
    out = tmp_path / "m.csv"
    write_measurements_csv(out, rows)
    assert out.read_text().splitlines()[0] == ",".join(MEASUREMENT_COLUMNS)
    back = read_measurements_csv(out)
    assert back == rows
    assert back[0].source == "hivelab" and back[0].launch_id == 0
    assert back[9].launch_id is None and back[9].efficiency is None
    assert len({r.measurement_id for r in rows}) == 12


def test_efficiency_formula():
    ticks = 1000.0
    assert wheel_surface_speed_in_s(ticks) == pytest.approx(1000 / 28 * 2 * math.pi * 1.89)
    assert efficiency(210.0, ticks) == pytest.approx(210.0 / (ticks * TICKS_TO_IN_S / 0.45))
