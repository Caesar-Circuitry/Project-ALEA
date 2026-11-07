"""Regenerate tests/golden/sample_contract.rlog (run: uv run python tests/make_golden_rlog.py).

The file is a 5-loop log with every key in docs/robot-interface.md plus PsiKit-style prefixes
and one built-in key. Its bytes are pinned by tests/test_data_import.py, so only regenerate
on purpose.
"""

from pathlib import Path

from alea.data import rlog
from alea.data.contract import AIM_KEYS, META_KEYS

OUT = Path(__file__).resolve().parent / "golden" / "sample_contract.rlog"

META = dict(
    zip(META_KEYS, ["1", "13.5", "127.8", "130.0", "11.0", "55.0", "7.5", "2400.0"], strict=True)
)


def aim(i: int) -> list:
    return ["RED_AUDIENCE", True, 60.0 + i, 1.5 * i, 45.0, -2.0 + i, 0.1 * i, 1500.0 + 10 * i,
            i >= 3, True]  # fmt: skip


def frames() -> list:
    out = [(0.0, {f"/RealMetadata/{k}": v for k, v in META.items()})]
    for i in range(5):
        values = {f"RealOutputs/{k}": v for k, v in zip(AIM_KEYS, aim(i), strict=True)}
        values["/Odometry/PedroInches/x"] = 10.0 + i
        out.append((0.02 * (i + 1), values))
    return out


if __name__ == "__main__":
    OUT.write_bytes(rlog.encode(frames()))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
