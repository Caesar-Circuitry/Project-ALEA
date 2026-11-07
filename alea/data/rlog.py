"""Pure-Python decoder (and small writer) for RLOG revision 2, the format PsiKit writes.

Layout, all integers big-endian (Java ByteBuffer default):

    file    := revision:u8(=2) record*
    record  := 0 time_s:f64                       # sets the time of the records after it
             | 1 id:i32 key:str type:str          # declares a key
             | 2 id:i32 value                     # a new value of a declared key
    str     := len:i32 utf8
    value   := by type string:
        boolean u8 | int64 i64 | float f32 | double f64 | string str | json str
        boolean[] len:i32 u8* | int64[] len:i32 i64* | float[] len:i32 f32*
        double[] len:i32 f64* | string[] count:i32 str*
        raw, struct:*, proto:*, anything else: len:i32 bytes

A robot that loses power leaves a half-written last record; the decoder keeps everything before
it and sets `LogData.truncated`.
"""

from __future__ import annotations

import struct
from pathlib import Path

from alea.data.logdata import LogData, Value

REVISION = 2
_TIMESTAMP, _KEY, _VALUE = 0, 1, 2


class RlogError(ValueError):
    """The bytes are not a valid RLOG revision 2 file."""


class _Truncated(Exception):
    pass


class _Reader:
    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.data = data
        self.pos = pos

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise _Truncated
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return out

    def unpack(self, fmt: str) -> tuple:
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))

    def string(self) -> str:
        (n,) = self.unpack(">i")
        return self.take(n).decode("utf-8")

    def array(self, fmt: str) -> list:
        (n,) = self.unpack(">i")
        if n < 0:
            raise _Truncated
        size = struct.calcsize(fmt)
        raw = self.take(n * size)
        return [v[0] for v in struct.iter_unpack(fmt, raw)]


_SCALARS = {"int64": ">q", "float": ">f", "double": ">d"}
_ARRAYS = {"int64[]": ">q", "float[]": ">f", "double[]": ">d", "boolean[]": ">?"}


def _read_value(r: _Reader, type_name: str) -> Value:
    if type_name == "boolean":
        return r.unpack(">?")[0]
    if type_name in _SCALARS:
        return r.unpack(_SCALARS[type_name])[0]
    if type_name in ("string", "json"):
        return r.string()
    if type_name in _ARRAYS:
        return r.array(_ARRAYS[type_name])
    if type_name == "string[]":
        (n,) = r.unpack(">i")
        if n < 0:
            raise _Truncated
        return [r.string() for _ in range(n)]
    (n,) = r.unpack(">i")  # raw, struct:*, proto:* and unknown types
    return r.take(n)


def decode(data: bytes) -> LogData:
    """Decode the bytes of an RLOG revision 2 file."""
    if not data:
        raise RlogError("empty file")
    if data[0] != REVISION:
        raise RlogError(f"unsupported RLOG revision {data[0]}, expected {REVISION}")
    log = LogData(format="rlog", format_version=str(REVISION))
    r = _Reader(data, 1)
    keys: dict[int, tuple[str, str]] = {}
    t_s = 0.0
    while r.pos < len(data):
        start = r.pos
        try:
            (kind,) = r.unpack(">B")
            if kind == _TIMESTAMP:
                (t_s,) = r.unpack(">d")
            elif kind == _KEY:
                (key_id,) = r.unpack(">i")
                key = r.string()
                keys[key_id] = (key, r.string())
            elif kind == _VALUE:
                (key_id,) = r.unpack(">i")
                if key_id not in keys:
                    raise RlogError(f"value for undeclared key id {key_id} at byte {start}")
                key, type_name = keys[key_id]
                log.add(key, type_name, t_s, _read_value(r, type_name))
            else:
                raise RlogError(f"unknown record type {kind} at byte {start}")
        except (_Truncated, UnicodeDecodeError):
            log.truncated = True
            break
    return log


def read(path: str | Path) -> LogData:
    """Decode the RLOG file at `path`."""
    return decode(Path(path).read_bytes())


# --- writer: enough to build test logs; PsiKit is the real producer ---------------------------


def _str(s: str) -> bytes:
    raw = s.encode("utf-8")
    return struct.pack(">i", len(raw)) + raw


def _type_of(value: Value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "int64"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "string"
    raise TypeError(f"cannot write {type(value).__name__}")


def _value_bytes(value: Value, type_name: str) -> bytes:
    if type_name == "boolean":
        return struct.pack(">?", value)
    if type_name in _SCALARS:
        return struct.pack(_SCALARS[type_name], value)
    return _str(str(value))


def encode(frames: list[tuple[float, dict[str, Value]]]) -> bytes:
    """Encode (t_s, {key: value}) frames; bool, int, float and str values only."""
    out = bytearray([REVISION])
    ids: dict[str, int] = {}
    for t_s, values in frames:
        out += struct.pack(">Bd", _TIMESTAMP, t_s)
        for key, value in values.items():
            type_name = _type_of(value)
            if key not in ids:
                ids[key] = len(ids)
                out += struct.pack(">Bi", _KEY, ids[key]) + _str(key) + _str(type_name)
            out += struct.pack(">Bi", _VALUE, ids[key]) + _value_bytes(value, type_name)
    return bytes(out)
