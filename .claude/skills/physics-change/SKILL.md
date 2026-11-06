---
name: physics-change
description: Procedure for an approved change to a frozen physics file (alea/sim/shotsim.py or alea/sim/study.py). Run only after the user has explicitly approved the change in this conversation.
disable-model-invocation: true
---

An approved physics change. Confirm the user said so in this conversation and quote it; if not,
stop here.

1. **Baseline.** Spawn `physics-reviewer` to record, before anything changes: the output of
   `just selftest`, and `git hash-object alea/sim/shotsim.py alea/sim/study.py`.
2. **Unlock.** Ask the user to add this to `.claude/settings.local.json` (git-ignored) for the
   duration of the change, then remove it afterwards. Settings reload live; no restart needed.

   ```json
   { "env": { "ALEA_ALLOW_PHYSICS_EDIT": "1" } }
   ```

3. **Change.** Spawn `implementer` with the exact edit, the reason, and the instruction to
   change nothing else in those files.
4. **Prove it.** The implementer runs `just selftest` and, on the team machine, the Java
   comparison in `alea/sim/verification/` (`verify_physics.py`, `compare.py`). Attach both
   outputs to the PR.
5. **Review.** Spawn `physics-reviewer` on the diff. It must classify every hunk and quote the
   before/after numbers.
6. **Ship** with `/pr`. Tick "changes physics?" in the template and paste the comparison.
7. **Relock.** Remind the user to remove the `env` entry from `.claude/settings.local.json`.
