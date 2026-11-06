# ALEA agentic workflow

How Claude Code (and any other agent) should work in this repo: which model for which problem,
the standard loop, and how to run work in parallel without stepping on the physics.

## 1. Model tiers by problem type

Start with the cheapest tier that can do the job. Escalate one tier when it fails twice, not before.

| Tier | Model | Use for | Never for |
|---|---|---|---|
| 0 | **Haiku** | file and symbol lookups, renames, README and boilerplate text, commit messages, docs nav, CSV/log parsing scripts, formatting fixes, dependency bumps | anything under the frozen paths (below), design decisions |
| 1 | **Sonnet** (default implementer) | tests, importers, CI YAML, Streamlit pages, notebooks, SQLAlchemy models, refactors that do not touch frozen paths, docs pages | physics, Warp kernels, release decisions |
| 2 | **Opus** | anything touching `alea/sim/`, `alea/game/`, `alea/hifi/`, `tests/golden/`; `/code-review`; CI failure diagnosis; decision records; the dsim port; Warp kernels; plan mode for multi-PR work | routine edits a lower tier can do |
| 3 | **Fable** | complex multi-agent orchestration only: for example running the dsim TypeScript → NumPy → Warp port with parallel validation agents, or a cross-cutting migration that spans five or more PRs | **anything else, and never without the user saying "use Fable" for that specific task** |

Rules:
- Interactive sessions run on Opus or Sonnet (`/model`). Do not switch to Fable yourself.
- When spawning a subagent, pass `model: haiku|sonnet|opus` per this table, or use an agent from
  `.claude/agents/`, whose frontmatter already pins the model.
- The `orchestrator` agent is the only Fable-pinned definition. Spawn it only after the user has
  approved Fable for the task in the current conversation. Say so in the spawn prompt.
- "Frozen paths" = `alea/sim/shotsim.py`, `alea/sim/study.py`, `alea/game/`, `tests/golden/`.
  Edits there are Opus-tier, hook-guarded, and need a human sign-off on the PR.

## 2. Standard loop

1. **Plan mode** for anything multi-file. Ask questions early; do not ask "is the plan OK" in text.
2. **Explore** (Haiku `explorer`): find the files, patterns and existing helpers. Read-only.
3. **Plan** (Opus, or Sonnet for a single-module task): write the plan file, name files to touch,
   name what must not change, say how it will be verified.
4. **Implement** (Sonnet `implementer`), in a git worktree when more than one agent is active.
   Small commits with clear messages on a `feature/…` or `setup/…` branch.
5. **Verify**: `just lint`, `just test`; `just selftest` whenever `alea/sim` or `alea/game` changed;
   `just docs` when `docs/` or `mkdocs.yml` changed; `just robot` when `robot/` changed.
6. **Review** (Opus `physics-reviewer` for frozen paths, `/code-review` otherwise).
7. **PR** with `.github/pull_request_template.md`: what changed, how tested, "self-test passed?",
   "changes physics?" (if yes: explanation + Java comparison attached). Humans merge.

## 3. Parallelism rules

- One worktree per agent (`isolation: "worktree"`), one branch per agent, one PR per agent.
- No two agents edit `alea/game/` or `conf/` at the same time. Serialize those.
- Agents that run studies write under Hydra `outputs/` (git-ignored); never into `tests/golden/`.
- A parent agent collects results from children; children do not message each other.
- Fan-out is for genuinely parallel work (independent importers, independent docs pages). It is
  not for "thoroughness". A single agent with the right tools is the default.

## 4. Cost hygiene

- Haiku first for anything that is lookup or boilerplate. Sonnet for most code.
- One Opus review is cheaper than three Sonnet retries on physics-adjacent code.
- No subagent for a task you can finish inline with your own tools.
- Long sessions: summarize state into the plan file so a restart does not re-explore.

## 5. Guard rails in this repo

- `.claude/settings.json` → `PreToolUse` hook `hooks/guard_physics.py` rejects Edit/Write/Bash
  writes to `alea/sim/shotsim.py` and `alea/sim/study.py` unless `ALEA_ALLOW_PHYSICS_EDIT=1`.
- Pre-commit: ruff, nbstripout, 1 MB file limit (except `tests/golden/`), private-key detection.
- CI (PR 3) runs lint + CPU tests on macOS arm64, Linux x86-64/arm64, Windows x86-64/arm64.
- CODEOWNERS routes physics paths to the physics maintainers.

See `docs/decisions/0003-agentic-workflow-and-models.md` for the reasoning.
