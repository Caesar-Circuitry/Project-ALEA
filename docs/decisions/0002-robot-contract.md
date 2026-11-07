# 0002: Robot contract

**Status:** accepted, 2026-11-07

## Context

ALEA reads robot logs to critique shots and replay matches. Teams run different robot code, so
ALEA needs a small, stable set of log keys it can rely on, and a way to know the robot and the
simulator agree on field and launcher numbers. Without a check, a renamed key or a retuned
constant silently breaks the importers.

## Decision

- Robots log with PsiKit (`org.psilynx.psikit:core` and `:ftc` 0.2.0 from
  `repo.dairy.foundation`), which writes RLOG files and works with AdvantageScope.
- Every key ALEA defines lives under the `Alea/` prefix (`Alea/Aim/DistanceIn`), with units in
  the key name. PsiKit's own keys (`/Odometry`, `HardwareMap/...`) stay as PsiKit writes them.
- `docs/robot-interface.md` is the source of truth for keys, types, units, rates and sources.
- `tests/test_robot_contract.py` enforces it: every key recorded under `robot/` is documented
  and vice versa, all keys start with `Alea/`, and Java constants that duplicate
  `alea.game.biobuzz` values are equal.
- `robot/` is a TeamCode-only Gradle project on FTC SDK 12.0.0, built by the `robot` CI job.
  It is a sample, not the competition robot.

## Consequences

- Adding or renaming a key means editing the Java and the doc in the same change, or the test
  fails.
- A robot team can adopt ALEA by copying `AleaSampleOpMode` and calling `AimAssist.log()`.
- The contract test reads the Java with regular expressions, so keys must be string literals.
- Game values are still owned by `alea/game/`; the Java copies are checked, never the source.
- Upgrading PsiKit or the FTC SDK is a change to `robot/TeamCode/build.gradle` and must be
  green in the `robot` CI job.
