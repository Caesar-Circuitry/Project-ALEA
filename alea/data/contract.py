"""The ALEA log keys, as listed in docs/robot-interface.md (decision 0002).

tests/test_data_import.py checks these tuples against the doc table, so a key renamed in the
doc but not here fails a test.
"""

from __future__ import annotations

PREFIX = "Alea/"
AIM_PREFIX = "Alea/Aim/"
META_PREFIX = "Alea/Meta/"

# Log key -> Shot column name.
AIM_COLUMNS: dict[str, str] = {
    "Alea/Aim/Target": "target",
    "Alea/Aim/HasPose": "has_pose",
    "Alea/Aim/DistanceIn": "distance_in",
    "Alea/Aim/OffAxisDeg": "off_axis_deg",
    "Alea/Aim/TargetHeadingDeg": "target_heading_deg",
    "Alea/Aim/HeadingErrorDeg": "heading_error_deg",
    "Alea/Aim/TurnCommand": "turn_command",
    "Alea/Aim/LutTicksPerSec": "lut_ticks_per_sec",
    "Alea/Aim/Aimed": "aimed",
    "Alea/Aim/InRange": "in_range",
}

# Log key -> LogFile column name. Metadata values are strings in the log.
META_COLUMNS: dict[str, str] = {
    "Alea/Meta/ContractVersion": "contract_version",
    "Alea/Meta/RedHiveXIn": "red_hive_x_in",
    "Alea/Meta/BlueHiveXIn": "blue_hive_x_in",
    "Alea/Meta/HiveAudienceMouthYIn": "hive_audience_mouth_y_in",
    "Alea/Meta/HiveRearMouthYIn": "hive_rear_mouth_y_in",
    "Alea/Meta/LaunchAngleDeg": "launch_angle_deg",
    "Alea/Meta/LauncherExitBehindIn": "launcher_exit_behind_in",
    "Alea/Meta/LauncherMaxTicksPerSec": "launcher_max_ticks_per_sec",
}

AIM_KEYS: tuple[str, ...] = tuple(AIM_COLUMNS)
META_KEYS: tuple[str, ...] = tuple(META_COLUMNS)
ALL_KEYS: tuple[str, ...] = AIM_KEYS + META_KEYS


def canonical_key(key: str) -> str | None:
    """Map a logged key to its contract form, or None if it is not an Alea key.

    PsiKit/AdvantageKit nest what robot code records: outputs appear as `RealOutputs/Alea/...`
    and metadata as `/RealMetadata/Alea/...`. Everything before the first `Alea/` is dropped.
    """
    i = key.find(PREFIX)
    if i < 0 or (i > 0 and key[i - 1] != "/"):
        return None
    return key[i:]
