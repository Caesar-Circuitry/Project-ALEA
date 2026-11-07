# ALEA agentic workflow

How Claude Code works in this repo: a coordinate-only main session, subagents pinned to the
cheapest adequate model, and the rules that are enforced by Claude Code rather than requested in
a prompt. Built from the Claude Code best-practices, subagent, hooks, permissions and model docs
(read in full on 2026-11-06).

## 1. The shape: a lead that never edits

`.claude/settings.json` sets `"agent": "lead"` and `"model": "sonnet"`, so every session in this
repo starts as the `lead` agent on Sonnet. Per the subagent docs, running the main thread as a
named agent applies that agent's `tools` list to the main session, so:

- `lead` has `Read, Grep, Glob, Bash, Agent(...)`, planning and web tools, and **no Edit, Write,
  MultiEdit or NotebookEdit**. It cannot edit a file even if asked.
- `lead`'s `Agent(explorer, implementer, physics-reviewer, verifier, ci-diagnoser, docs-writer, orchestrator)` entry is an
  allowlist. It cannot spawn the built-in Explore or Plan agents (Explore runs on Opus for
  subscription accounts, which is why we keep our own Haiku explorer).
- `.claude/hooks/guard_lead.py` limits the lead's Bash to checks, read-only git (also
  `git -C <path>`, `show`, `merge-tree`, `ls-files`, `worktree list`), read-only `gh` (`pr view|list|checks|diff`,
  `run list|view`, `api` GET) and read-only shell commands. It parses each pipeline segment with
  `shlex`, so quoted `|` and `2>&1` are fine. A shell write (`sed -i`, other redirects, `tee`,
  `mv`, `rm`, `git commit`) is rejected with a pointer to the right subagent. The hook only acts when the hook input's `agent_type` is `lead`.
- `lead`'s body is empty on purpose: a non-empty body would replace Claude Code's own system
  prompt. Its instructions come from `CLAUDE.md`, which still loads.

The lead's job each turn: understand, plan (plan mode for multi-file work), spawn, collect,
verify with `just lint` / `just test` / `just selftest`, report with evidence.

### Shell sandbox

Every agent except the lead runs its shell work in the dev container `alea-dev`
(`docs/decisions/0006-agent-sandbox.md`).

- Non-lead agents run commands as `just dev <cmd>` or `docker exec alea-dev <cmd>`. For `&&`,
  `;` or `|`, use `just dev bash -c '...'`. `guard_container.py` blocks any other shell command.
- The lead runs `just dev-up` on the host before it delegates. It runs `just dev-status` to check.
- `git push` and `gh` run on the host only, by the lead after the user approves each. The container has no push credentials.
- Push with `git push origin <branch>`, never `-u`: it rewrites `.git/config` and the container's overlay goes stale.
- Create branches with `git switch -c <name> --no-track origin/main`. Tracking writes to the
  read-only `.git/config`.
- If `just dev` says a read-only overlay is gone, the host rewrote `.git/config` or `.env`. The
  user runs `just dev-down` and then `just dev-up`.
- Edits still use the host's file tools. The hook keeps them inside the repo.

## 2. Model tiers by problem type

| Tier | Model | Agent | Use for |
|---|---|---|---|
| 0 | Haiku | `explorer`, `docs-writer` | lookups, renames, READMEs, decision records, commit text, CSV/log parsing scripts |
| 1 | Sonnet | `lead`, `implementer`, `verifier`, unlabeled spawns | planning, coordination, tests, importers, CI YAML, models, Streamlit, notebooks, non-physics refactors |
| 2 | Opus | `physics-reviewer`, `ci-diagnoser`, `auditor`; `/model opus` for a session | anything under `alea/sim`, `alea/game`, `alea/hifi`, `tests/golden`; `/code-review`; CI failure diagnosis; the dsim port; Warp kernels |
| 3 | Fable | `orchestrator` only | complex multi-agent, multi-PR work the user has explicitly approved for Fable |

The project also sets `advisorModel: opus` in `.claude/settings.json`. This is Claude Code's
built-in advisor (the `/advisor` command): Sonnet and Haiku sessions and subagents can consult
Opus through a server-side advisor tool, and it does not activate on a model that is not weaker
than the advisor, so the Opus agents are unaffected. It may use more tokens. A person can turn it
off for their own session with `/advisor`, or override it in `.claude/settings.local.json`.

Rules:
- Start cheap. Escalate one tier after two failures, not before.
- `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` (settings `env`) is the default for any spawn without a
  pinned model. It is not forced, so agent frontmatter still wins.
- Spawning `orchestrator` triggers a permission prompt (`permissions.ask: Agent(orchestrator)`),
  as does any spawn that passes `model: fable`. That prompt is the Fable gate.
- Periodic audit: run `/audit` weekly or at the end of each roadmap phase. The `auditor` is
  read-only (no Edit or Write) and reports findings on current practices, security and common
  AI mistakes; the user decides what to file or fix. It starts on Opus. Escalate it to Fable
  only if audits repeatedly miss issues the team later finds, and only with the user's approval.
- Effort stays at the model default (`medium`). Raise it per session with `/effort high` for a
  tricky physics bug; never leave it high for routine work.

## 3. Standard loop

1. **Plan mode** for anything multi-file (`Shift+Tab`). Ask questions early with
   `AskUserQuestion`; never ask "is the plan OK" in prose.
2. **Explore** with `explorer` when the answer needs a sweep of many files. For a known file,
   the lead reads it directly; a subagent costs more than a `Read`.
3. **Implement** with `implementer`. One task per spawn, with the files to touch, what must not
   change, and the check that defines done. Use `isolation: "worktree"` when two implementers run
   at once. The implementer's Stop hook (`.claude/hooks/subagent_gate.py`) re-runs lint and tests
   and refuses to let it finish while they fail, up to three times.
4. **Verify** in the lead: `just lint`, `just test`; `just selftest` after any sim or game change;
   `just docs` after docs changes; `just robot` after `robot/` changes. Quote the output. For a whole branch the lead also spawns
   `verifier` (fresh context, read-only) before `/pr`, and still runs the quick checks itself.
5. **Review** with `physics-reviewer` for frozen paths, `/code-review` otherwise.
6. **Ship** with `/pr`: `implementer` runs the checks and commits in the container; the lead
   then pushes and runs `gh pr create` on the host (each asks first) and prints the PR URL. If CI fails on the pushed branch,
   spawn `ci-diagnoser` (read-only, Opus) to classify the failure and propose the fix, then hand
   the fix to `implementer`. Humans merge.

## 4. What is enforced versus requested

Per the best-practices doc: a `CLAUDE.md` line is a guideline Claude may weigh; a hook, deny
rule or tool list is applied by Claude Code every time. Keep the enforced set small.

| Rule | Mechanism | Where |
|---|---|---|
| lead never edits files | `tools` allowlist on the `lead` agent | `.claude/agents/lead.md` |
| lead's shell is read-only + checks | PreToolUse hook, `agent_type == lead` | `.claude/hooks/guard_lead.py` |
| other agents' shell runs in `alea-dev`; file edits stay in the repo | PreToolUse hook, every agent but lead | `.claude/hooks/guard_container.py` |
| no push credentials in the sandbox | no mounts, no credential helper | `.devcontainer/cpu/`, decision 0006 |
| frozen physics files (real file targets, not command text) | PreToolUse hook, all agents | `.claude/hooks/guard_physics.py` |
| edited `.py` files get `ruff format` + `ruff check --fix` (never blocks) | PostToolUse hook, `Edit\|Write\|MultiEdit` | `.claude/hooks/autoformat.py` |
| session summary: branch, `.venv` freshness, golden data, roadmap next, worktrees | SessionStart hook | `.claude/hooks/session_start.py` |
| implementer finishes green | SubagentStop hook in frontmatter | `.claude/hooks/subagent_gate.py` |
| Fable only with approval | `permissions.ask` on `Agent(orchestrator)` and `Agent(model:fable)` | `.claude/settings.json` |
| push and PR creation ask the user | `permissions.ask: Bash(git push *)`, `Bash(gh pr create *)` | `.claude/settings.json` |
| no secrets read | `permissions.deny: Read(./.env)` | `.claude/settings.json` |
| big files, private keys | pre-commit | `.pre-commit-config.yaml` |
| no commits on `main` | pre-commit `no-commit-to-branch` | `.pre-commit-config.yaml` |
| physics review | CODEOWNERS + branch protection | `.github/CODEOWNERS`, decision 0004 |

Everything else (units in names, README per folder, cross-platform habits) is a guideline in
`CLAUDE.md` or a path-scoped rule in `.claude/rules/`.

## 5. Skills (procedures, loaded on demand)

| Skill | Invoked by | Does |
|---|---|---|
| `/pr` | user only | lead context: `implementer` checks and commits, lead pushes and runs `gh pr create` |
| `/physics-change` | user only | the procedure for an approved change to a frozen file |
| `/start-pr` | user only | forks an `implementer`: branch from `origin/main` for a ROADMAP stage, `just sync`, prints the done-when list; never commits |

Skills are for multi-step procedures with side effects; `CLAUDE.md` stays short. No MCP servers:
GitHub goes through `gh` (cheaper in context), and nothing else external is in scope yet.

## 6. Parallelism and scale

- One worktree per concurrent implementer; one branch, one PR each. Never two agents editing
  `alea/game/` or `conf/` at once.
- Studies write under `results/` (git-ignored; the `out:` key in `conf/study/brev72.yaml`), never into `tests/golden/`.
- Children report to the lead; they do not message each other.
- For work bigger than a handful of agents (the dsim hive-tipping port with parallel
  validation), the options in order of cost: an `orchestrator` run (Fable, asks first), or a
  dynamic workflow (`ultracode` keyword, runs on the session model, saved to
  `.claude/workflows/`). Agent teams stay off (experimental, ~7× tokens).
- Context hygiene: `/clear` between unrelated tasks, `/usage` to see what a subagent type costs,
  short summaries back from every spawn.

## 7. Path-scoped rules

`.claude/rules/physics.md` loads only when an agent touches `alea/sim`, `alea/game`,
`alea/hifi` or `tests/golden`; `.claude/rules/cross-platform.md` loads for Python, TOML, CI
and `justfile` edits. They cost nothing until needed.

## 8. Verify the setup

- `/status` shows `@lead` in the startup header and lists `Project settings` under sources.
- Ask the lead to edit a file: it should spawn `implementer` or say it has no Edit tool.
- `uv run pytest tests/test_claude_config.py tests/test_guard_hook.py tests/test_guard_container.py`
  checks the config shape, the model pins and the guard hooks.
