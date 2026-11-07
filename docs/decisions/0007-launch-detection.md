# 0007: Launch detection from the flywheel

Status: accepted (heuristic), contract change proposed only.

## Context

The robot contract (decision 0002) logs `Alea/Aim/*` every loop but has no "ball fired" key, so
`Shot` rows are loops, not launches. Phase 0 needs launches in the database now, and no robot is
available to add a key.

## Decision

Infer launches from the flywheel. PsiKit's hardware wrappers log motor state under
`HardwareMap/<name>/...`; we assume the flywheel speed is `HardwareMap/<name>/velocity` in ticks
per second. This key name is an assumption (the contract doc only says `HardwareMap/<name>/...`
holds "ticks/s"); it is configurable through `LaunchConfig.key_pattern`.

`alea/data/launches.py` marks a launch where the speed falls by at least 80 ticks/s within 0.1 s,
with a 0.5 s refractory period between launches. A drop to under 40 % of the earlier speed
within 0.15 s is treated as the wheel being switched off, not a ball. When several velocity keys
match, a name containing launch, fly or shoot wins, else the highest peak speed. Each launch is
stored as a `Launch` row with the flywheel speed before and after and the `Alea/Aim/*` sample
nearest in time. With no matching key the log gets zero launches and
`LogFile.launch_note` says so.

## Limits

- Thresholds are tuned on synthetic logs only. Real flywheel dips may be smaller or slower.
- Two balls in under 0.5 s count as one; a dip with the wheel commanded to a lower setpoint
  faster than 80 ticks/s per 0.1 s is a false launch.
- The detector cannot tell a scored ball from a miss, or a jam from a launch.
- Launch time is the first loop of the drop, so it can be a loop late.

## Proposed contract key (not implemented)

`Alea/Shot/Fired`: boolean, true for the one loop in which the launcher released a ball, logged
every loop by the robot code that feeds the ball. Adding it needs a `ContractVersion` bump, a row
in `docs/robot-interface.md` and Java in `robot/`; none of that is part of this decision. When it
exists the importer should prefer it and keep this detector as a fallback.

## Consequences

Launch analysis works on any PsiKit log today. Detected launches must be validated against real
logs and video once a robot is available.
