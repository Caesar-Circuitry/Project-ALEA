# robot (sample robot code)

A small, clean FTC SDK sample showing how any robot is set up to work with ALEA (PsiKit logging with the keys in docs/robot-interface.md). This is NOT the competition robot code.

**Roadmap phase:** Phase 0 (contract) — filled in PR 5

## Contents

- `TeamCode/src/main/java/org/firstinspires/ftc/teamcode/alea/`
  - `AleaSampleOpMode`: sets up PsiKit, records constants as metadata, calls `AimAssist.log()`.
  - `AimAssist`, `LaunchLut`, `Constants`: aim math and launch look-up table (no hardware).
- TeamCode-only Gradle project: FTC SDK 12.0.0 (Maven Central) and PsiKit 0.2.0
  (`https://repo.dairy.foundation/releases`), both pinned in `TeamCode/build.gradle`.

## Build

Needs JDK 17 and the Android SDK (`ANDROID_HOME` or `sdk.dir` in `robot/local.properties`,
with platform 34). CI builds it on every change under `robot/`.

```
cd robot
./gradlew assembleDebug        # Windows: gradlew.bat assembleDebug
```

or `just robot` from the repo root. The `tests/test_robot_contract.py` test keeps the Java keys
and constants in step with `docs/robot-interface.md` and `alea.game`; it needs no JDK.
