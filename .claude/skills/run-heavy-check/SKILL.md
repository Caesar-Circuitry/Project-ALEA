---
name: run-heavy-check
description: Only for heavy-check-operator, only when a unit test cannot prove the claim. How to bring up, observe and tear down each heavy check listed in .claude/repo.json.
user-invocable: false
---

# Run one heavy check

Read the entry in `heavy_checks` of `.claude/repo.json`: `run`, `needs`, `where`. Run nothing
that `forbidden_commands` blocks. One check per run. Install nothing; if a need is missing,
report `BLOCKED: <need>` and stop.

## Bring-up, in order

1. `just dev-status`. Checks whose `where` is the container run as `just dev <run>`.
2. Check the needs before starting:
   - `robot-build`: `java -version` shows 17 and `ANDROID_HOME` or `ANDROID_SDK_ROOT` is set.
     The container has neither, so this runs on the host or is left to the CI `robot` job.
   - `gpu-tests`: `nvidia-smi` lists a device. Otherwise BLOCKED; point the user at
     `.github/workflows/gpu-tests.md` (Brev). GPU spend needs the user's approval.
   - `study-smoke`: nothing. Keep the shot count at 10000 on CPU.
   - `java-compare`: runs on the team machine only. Always BLOCKED here; print the commands
     from `alea/sim/verification/README.md` for the user.
3. Start the `run` command. Poll for the end with the command's own exit, not a sleep loop;
   allow 15 minutes for a cold Gradle cache.

## Evidence

- `robot-build`: the `BUILD SUCCESSFUL in ...` line and the path of the debug APK.
- `gpu-tests`: the pytest summary line and the device name from `nvidia-smi`.
- `study-smoke`: the self-test agreement percentage, the row count of `summary.csv`, and two
  rows of it with their `+/-`.

## Teardown

- `robot-build`: `./gradlew --stop` in `robot/`; confirm no Gradle daemon is left
  (`pgrep -f GradleDaemon` prints nothing).
- `study-smoke`: outputs stay under the git-ignored `results/`; confirm `git status --short`
  shows nothing new.
- Never leave a process running. Never commit, push or copy an output into `tests/golden/`.
