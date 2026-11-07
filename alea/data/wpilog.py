"""Reader for WPILib `.wpilog` files, same key contract as `alea.data.rlog`.

Needs the `logs` extra (robotpy-wpiutil): `uv sync --extra logs`. The import is lazy so the rest
of `alea.data` works without it.
"""

from __future__ import annotations

from pathlib import Path

from alea.data.logdata import LogData

_MICROS = 1_000_000.0


def read(path: str | Path) -> LogData:
    """Read the `.wpilog` file at `path`."""
    try:
        from wpiutil.log import DataLogReader
    except ImportError as exc:  # pragma: no cover - depends on install
        raise ImportError("reading .wpilog needs the 'logs' extra: uv sync --extra logs") from exc

    reader = DataLogReader(str(path))
    if not reader.isValid():
        raise ValueError(f"{path} is not a valid wpilog file")
    log = LogData(
        format="wpilog", format_version=f"{reader.getVersion() >> 8}.{reader.getVersion() & 0xFF}"
    )
    names: dict[int, tuple[str, str]] = {}
    for record in reader:
        if record.isStart():
            start = record.getStartData()
            names[start.entry] = (start.name, start.type)
            continue
        if record.isControl() or record.getEntry() not in names:
            continue
        key, type_name = names[record.getEntry()]
        t_s = record.getTimestamp() / _MICROS
        try:
            value = _value(record, type_name)
        except (ValueError, TypeError):
            log.truncated = True
            continue
        log.add(key, type_name, t_s, value)
    return log


def _value(record, type_name: str):
    getters = {
        "boolean": record.getBoolean,
        "int64": record.getInteger,
        "float": record.getFloat,
        "double": record.getDouble,
        "string": record.getString,
        "json": record.getString,
        "boolean[]": record.getBooleanArray,
        "int64[]": record.getIntegerArray,
        "float[]": record.getFloatArray,
        "double[]": record.getDoubleArray,
        "string[]": record.getStringArray,
    }
    getter = getters.get(type_name)
    if getter is None:
        return bytes(record.getRaw())
    value = getter()
    return list(value) if type_name.endswith("[]") else value
