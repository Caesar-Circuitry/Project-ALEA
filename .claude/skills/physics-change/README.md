# .claude/skills/physics-change

The `/physics-change` skill. `SKILL.md` is the procedure for an approved change to a frozen file
(`alea/sim/shotsim.py` or `alea/sim/study.py`).

- Runs only after the user has approved the change in the conversation.
- Records baseline hashes, unlocks the guard for the change, then runs the self-test and the Java comparison.
- Ends with a relock: the `env` entry is removed from `.claude/settings.local.json`.

**Roadmap phase:** all
