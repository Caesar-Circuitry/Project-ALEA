# alea (Java package)

The ALEA helpers for the sample OpMode. Only `AleaSampleOpMode` touches the hardware map.

- `AimAssist.java`: aims the back-mounted launcher at the chosen hive cell (heading PD, LUT speed, ready flags). Logs `Alea/Aim/*`.
- `AleaSampleOpMode.java`: sample TeleOp. Sets up PsiKit logging, records constants as metadata, feeds the Pinpoint pose to `AimAssist`, and calls `aim.log()`.
- `Constants.java`: launcher, field, odometry, LUT and aim numbers. Units are in the names (`_IN`, `_DEG`, `_TICKS_PER_SEC`).
- `LaunchLut.java`: distance-to-flywheel-speed table with linear interpolation. No hardware.

Every `Logger.recordOutput` key (and every `Logger.recordMetadata` key) must be listed in `docs/robot-interface.md`. `tests/test_robot_contract.py` enforces this and fails if a Java key is missing from the doc.

**Roadmap phase:** Phase 0 (contract) — filled in PR 5
