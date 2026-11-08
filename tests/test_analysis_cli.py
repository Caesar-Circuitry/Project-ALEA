import pytest

from alea.analysis.cli import main
from alea.analysis.hivelab import read_measurements_csv
from alea.data.importer import read_log
from alea.data.launches import detect_launches
from alea.data.synthetic import synth_match

SHIFT_S = 12.5
HEADER = "video,shot,burst,burst_size,time_s,v0_in_s,angle_deg,result"


def _hive(tmp_path, times_s, header=HEADER):
    lines = [header] + [f"c.mp4,{i},0,1,{t},210,45,IN" for i, t in enumerate(times_s)]
    p = tmp_path / "hive.csv"
    p.write_text("\n".join(lines) + "\n")
    return p


def test_end_to_end_with_log(tmp_path, capsys):
    m = synth_match(5)
    log = tmp_path / "s.rlog"
    log.write_bytes(m.data)
    video = [t + SHIFT_S for t in m.launch_times_s[:12]]
    out = tmp_path / "out.csv"
    assert main(["hivelab-import", str(_hive(tmp_path, video)), "--log", str(log),
                 "--out", str(out)]) == 0  # fmt: skip
    rows = read_measurements_csv(out)
    assert len(rows) == 12 and all(r.efficiency is not None for r in rows)
    assert "12 of 12" in capsys.readouterr().out


def test_launches_csv_and_cue(tmp_path):
    m = synth_match(5)
    found = detect_launches(read_log_from(tmp_path, m)).launches
    lp = tmp_path / "l.csv"
    lp.write_text(
        "t_s,before,after,dip\n"
        + "".join(
            f"{d.t_s},{d.ticks_per_sec_before},{d.ticks_per_sec_after},{d.dip_ticks_per_sec}\n"
            for d in found
        )
    )
    video = [d.t_s + SHIFT_S for d in found[:6]]
    out = tmp_path / "o.csv"
    args = ["hivelab-import", str(_hive(tmp_path, video)), "--launches-csv", str(lp)]
    args += ["--cue-video-s", str(video[0]), "--cue-log-s", str(found[0].t_s)]
    args += ["--out", str(out)]
    assert main(args) == 0
    assert sum(r.t_log_s is not None for r in read_measurements_csv(out)) == 6


def read_log_from(tmp_path, m):
    p = tmp_path / "x.rlog"
    p.write_bytes(m.data)
    return read_log(p)


def test_missing_column_exits_nonzero(tmp_path, capsys):
    p = _hive(tmp_path, [1.0, 2.0], header=HEADER.replace("angle_deg", "ang"))
    lp = tmp_path / "l.csv"
    lp.write_text("t_s,before,after,dip\n1,1000,800,200\n")
    assert main(["hivelab-import", str(p), "--launches-csv", str(lp),
                 "--out", str(tmp_path / "o.csv")]) != 0  # fmt: skip
    assert "angle_deg" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["hivelab-import", str(p)])
