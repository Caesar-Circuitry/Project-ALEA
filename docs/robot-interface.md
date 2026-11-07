# Robot interface contract

What a robot must log so ALEA can read it. This file is the source of truth:
`tests/test_robot_contract.py` fails if the Java under `robot/` and this table disagree.
See [decision 0002](decisions/0002-robot-contract.md).

**Roadmap phase:** Phase 0 (contract), filled in PR 5. The importers that read these keys come in PR 6.

## Logging stack

Robots log with [PsiKit](https://github.com/psilynx-ftc/psikit) (`org.psilynx.psikit:core` and
`:ftc`, version 0.2.0), which writes RLOG files (`/sdcard/FIRST/PsiKit/`) and can stream them
live (port 5800). Values are written with `Logger.recordOutput(key, value)`; constants that do
not change during a match are written once with `Logger.recordMetadata(key, value)`.

Rules for every ALEA key:

- The key starts with `Alea/`.
- Units are in the key name (`DistanceIn`, `HeadingErrorDeg`) unless the value is unitless.
- Field frame: inches, 0..141.3 on both axes (Pedro / sim frame). Angles: radians in code,
  degrees in the log, counter-clockwise positive.
- Keys are string literals in the Java, so the contract test can find them.

## Alea keys (recorded with `Logger.recordOutput`)

Rate "every loop" means once per OpMode loop, about 50 to 100 Hz.

| Key | Type | Units | Rate | Source |
|---|---|---|---|---|
| `Alea/Aim/Target` | string | enum name: `RED_AUDIENCE`, `RED_REAR`, `BLUE_AUDIENCE`, `BLUE_REAR` | every loop | `AimAssist.log()` |
| `Alea/Aim/HasPose` | boolean | none | every loop | `AimAssist.log()` |
| `Alea/Aim/DistanceIn` | double | inches, launcher exit to cell mouth | every loop | `AimAssist.log()` |
| `Alea/Aim/OffAxisDeg` | double | degrees from straight out of the mouth | every loop | `AimAssist.log()` |
| `Alea/Aim/TargetHeadingDeg` | double | degrees, field frame, counter-clockwise | every loop | `AimAssist.log()` |
| `Alea/Aim/HeadingErrorDeg` | double | degrees, wrapped to -180..180 | every loop | `AimAssist.log()` |
| `Alea/Aim/TurnCommand` | double | unitless, -1..1, positive clockwise | every loop | `AimAssist.log()` |
| `Alea/Aim/LutTicksPerSec` | double | flywheel ticks per second | every loop | `AimAssist.log()` |
| `Alea/Aim/Aimed` | boolean | none | every loop | `AimAssist.log()` |
| `Alea/Aim/InRange` | boolean | none | every loop | `AimAssist.log()` |

## Alea metadata (recorded with `Logger.recordMetadata`)

Written once per log, as strings, when logging starts. They let an importer know which
constants the robot ran with.

| Key | Type | Units | Rate | Source |
|---|---|---|---|---|
| `Alea/Meta/ContractVersion` | string | integer version of this document | once | `AleaSampleOpMode.onPsiKitConfigureLogging()` |
| `Alea/Meta/RedHiveXIn` | string (double) | inches | once | `AleaSampleOpMode.onPsiKitConfigureLogging()` |
| `Alea/Meta/BlueHiveXIn` | string (double) | inches | once | `AleaSampleOpMode.onPsiKitConfigureLogging()` |
| `Alea/Meta/HiveAudienceMouthYIn` | string (double) | inches | once | `AleaSampleOpMode.onPsiKitConfigureLogging()` |
| `Alea/Meta/HiveRearMouthYIn` | string (double) | inches | once | `AleaSampleOpMode.onPsiKitConfigureLogging()` |
| `Alea/Meta/LaunchAngleDeg` | string (double) | degrees above level | once | `AleaSampleOpMode.onPsiKitConfigureLogging()` |
| `Alea/Meta/LauncherExitBehindIn` | string (double) | inches behind robot centre | once | `AleaSampleOpMode.onPsiKitConfigureLogging()` |
| `Alea/Meta/LauncherMaxTicksPerSec` | string (double) | ticks per second | once | `AleaSampleOpMode.onPsiKitConfigureLogging()` |

## PsiKit built-in keys

PsiKit writes these itself; they are not under `Alea/` and robot code does not record them.
ALEA's importer reads them as they are.

| Key | Type | Units | Rate | Source |
|---|---|---|---|---|
| `/Odometry` | Pose2d struct | meters and radians (AdvantageScope frame) | every loop | PsiKit Pinpoint or Pedro odometry logger |
| `/Odometry/PedroInches` | x, y, heading, headingDeg | inches, radians, degrees | every loop | `PedroFollowerOdometryLogger` (Pedro robots only) |
| `HardwareMap/<name>/...` | per device | motor ticks, ticks/s, mA, volts | every loop | PsiKit hardware wrappers |
| `OpModeControls/...` | booleans | none | every loop | PsiKit |

Motor current (`HardwareMap/<motor>/currentMilliamps`) is off by default because it is a slow
non-bulk read. A robot that wants it must set `FtcLogTuning.logMotorCurrent = true`
(and optionally `FtcLogTuning.motorCurrentReadPeriodSec`, default 0.1 s) before logging starts,
and must not use the bulk-only profile (`FtcLogTuning.bulkOnlyLogging = false`).
`AleaSampleOpMode` shows both settings.
