"""A sample log imports into SQLite with every contract key (roadmap stage 6)."""

import re
import struct
from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select

from alea.data import rlog
from alea.data.contract import AIM_COLUMNS, AIM_KEYS, ALL_KEYS, META_COLUMNS, META_KEYS
from alea.data.db import make_engine, make_session, upgrade
from alea.data.importer import import_log
from alea.data.models import LogFile, Shot

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden" / "sample_contract.rlog"
DOC = ROOT / "docs" / "robot-interface.md"


@pytest.fixture
def session(tmp_path):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    upgrade(url)
    engine = make_engine(url)
    with make_session(engine) as s:
        yield s
    engine.dispose()


def test_contract_keys_match_doc() -> None:
    doc = set(re.findall(r"^\|\s*`(Alea/[^`]+)`\s*\|", DOC.read_text(encoding="utf-8"), re.M))
    assert doc == set(ALL_KEYS)


def test_golden_file_is_tiny() -> None:
    assert GOLDEN.stat().st_size < 10_000


def test_rlog_decodes_golden() -> None:
    log = rlog.read(GOLDEN)
    assert not log.truncated
    assert log.types["RealOutputs/Alea/Aim/DistanceIn"] == "double"
    assert log.types["RealOutputs/Alea/Aim/Aimed"] == "boolean"
    assert len(log.entries["RealOutputs/Alea/Aim/Target"]) == 5
    assert log.entries["RealOutputs/Alea/Aim/Target"][0] == (0.02, "RED_AUDIENCE")


def test_rlog_roundtrip() -> None:
    frames = [(0.5, {"a": 1, "b": 2.5, "c": "x", "d": False}), (1.0, {"a": -7})]
    log = rlog.decode(rlog.encode(frames))
    assert log.entries["a"] == [(0.5, 1), (1.0, -7)]
    assert log.entries["d"] == [(0.5, False)]


def test_rlog_arrays_and_raw() -> None:
    def s(x: str) -> bytes:
        return struct.pack(">i", len(x)) + x.encode()

    body = bytes([2])
    body += struct.pack(">Bd", 0, 1.0)
    for i, (key, typ) in enumerate([("d", "double[]"), ("s", "string[]"), ("p", "struct:Pose2d")]):
        body += struct.pack(">Bi", 1, i) + s(key) + s(typ)
    body += struct.pack(">Bi", 2, 0) + struct.pack(">i2d", 2, 1.5, 2.5)
    body += struct.pack(">Bi", 2, 1) + struct.pack(">i", 2) + s("a") + s("bc")
    body += struct.pack(">Bi", 2, 2) + struct.pack(">i", 3) + b"\x01\x02\x03"
    log = rlog.decode(body)
    assert log.entries["d"] == [(1.0, [1.5, 2.5])]
    assert log.entries["s"] == [(1.0, ["a", "bc"])]
    assert log.entries["p"] == [(1.0, b"\x01\x02\x03")]


def test_rlog_truncated_keeps_earlier_records() -> None:
    data = GOLDEN.read_bytes()
    log = rlog.decode(data[:-5])
    assert log.truncated
    assert len(log.entries["RealOutputs/Alea/Aim/Target"]) >= 4


def test_rlog_rejects_wrong_revision() -> None:
    with pytest.raises(rlog.RlogError):
        rlog.decode(bytes([1, 0, 0]))
    with pytest.raises(rlog.RlogError):
        rlog.decode(b"")


def test_import_has_every_contract_key(session) -> None:
    log = import_log(session, GOLDEN)
    session.commit()
    assert log.missing_keys == []
    assert set(log.metadata_json) == set(META_KEYS)
    for column in META_COLUMNS.values():
        assert getattr(log, column) is not None, column
    assert log.contract_version == 1
    assert log.launch_angle_deg == 55.0
    shots = session.scalars(select(Shot).order_by(Shot.t_s)).all()
    assert len(shots) == 5
    for column in AIM_COLUMNS.values():
        assert all(getattr(s, column) is not None for s in shots), column
    assert shots[0].target == "RED_AUDIENCE"
    assert shots[4].distance_in == pytest.approx(64.0)
    assert [s.aimed for s in shots] == [False, False, False, True, True]
    assert len(AIM_KEYS) == 10


def test_import_is_idempotent(session) -> None:
    first = import_log(session, GOLDEN)
    second = import_log(session, GOLDEN)
    assert first.id == second.id
    assert session.scalar(select(func.count()).select_from(LogFile)) == 1


def test_missing_keys_are_reported(session, tmp_path) -> None:
    path = tmp_path / "partial.rlog"
    path.write_bytes(rlog.encode([(0.1, {"Alea/Aim/DistanceIn": 50.0})]))
    log = import_log(session, path)
    assert "Alea/Aim/Target" in log.missing_keys
    assert "Alea/Meta/ContractVersion" in log.missing_keys
    assert "Alea/Aim/DistanceIn" not in log.missing_keys
    assert log.shots[0].distance_in == 50.0


def test_migration_creates_all_tables(tmp_path) -> None:
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    upgrade(url)
    engine = make_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert {"team", "event", "match", "robot", "log_file", "shot", "alembic_version"} <= tables
    engine.dispose()


def _wpilog_bytes(entries: list[tuple[str, str, list[tuple[int, bytes]]]]) -> bytes:
    """Hand-written WPILOG v1.0: header, a Start record per entry, then data records."""

    def record(entry: int, t_us: int, payload: bytes) -> bytes:
        # bitfield: entry id 4 bytes, payload size 4 bytes, timestamp 8 bytes (each length - 1)
        head = bytes([3 | (3 << 2) | (7 << 4)])
        return head + struct.pack("<IIQ", entry, len(payload), t_us) + payload

    def s(x: str) -> bytes:
        return struct.pack("<I", len(x)) + x.encode()

    out = b"WPILOG" + struct.pack("<HI", 0x0100, 0)
    for i, (name, typ, _) in enumerate(entries, start=1):
        out += record(0, 0, bytes([0]) + struct.pack("<I", i) + s(name) + s(typ) + s(""))
    for i, (_, _, samples) in enumerate(entries, start=1):
        for t_us, payload in samples:
            out += record(i, t_us, payload)
    return out


def test_wpilog_imports_same_contract(session, tmp_path) -> None:
    pytest.importorskip("wpiutil.log")
    entries = [
        (f"/RealMetadata/{k}", "string", [(1_000, b"1" if k.endswith("Version") else b"12.5")])
        for k in META_KEYS
    ]
    entries.append(
        (
            "RealOutputs/Alea/Aim/DistanceIn",
            "double",
            [(20_000 * (i + 1), struct.pack("<d", 60.0 + i)) for i in range(3)],
        )
    )
    entries.append(
        (
            "RealOutputs/Alea/Aim/Target",
            "string",
            [(20_000 * (i + 1), b"BLUE_REAR") for i in range(3)],
        )
    )
    path = tmp_path / "sample.wpilog"
    path.write_bytes(_wpilog_bytes(entries))
    row = import_log(session, path)
    assert row.format == "wpilog"
    assert set(row.metadata_json) == set(META_KEYS)
    assert row.contract_version == 1
    assert [s.distance_in for s in sorted(row.shots, key=lambda s: s.t_s)] == [60.0, 61.0, 62.0]
    assert row.shots[0].target == "BLUE_REAR"
    assert "Alea/Aim/Aimed" in row.missing_keys
