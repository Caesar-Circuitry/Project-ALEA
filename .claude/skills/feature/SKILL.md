---
name: feature
description: Build a feature with the agent team. Plans it, shows the plan, then runs writers on disjoint files in parallel, the verifier, the safety review and the docs sync. Ends with a commit message and PR text; commits nothing.
argument-hint: "[what to build]"
user-invocable: true
disable-model-invocation: true
---

Build: $ARGUMENTS

You are the team lead. You plan, delegate and check; you never implement. Read `team_cap`,
`team_threshold` and `plan_critic` from `profile_settings` in `.claude/repo.json` (the user
changes them with `just profile max|pro`; `just profile` prints them). Run `just dev-status`
first; if the sandbox is down, run `just dev-up`.

1. **Plan.** Spawn `planner` as an unnamed subagent on the request. If its answer starts with
   `STOP`, print it and end. If `plan_critic` applies to this plan, spawn `plan-critic` on it;
   if it lists gaps, resume the planner once with the gap list. Show the plan and ask the user
   to approve it with AskUserQuestion. Do nothing more until the answer is yes.
1b. **Small plan.** Count the items that can run at the same time. Fewer than
   `team_threshold`: do NOT form a team. Spawn the writers as unnamed subagents one after the
   other (implementers first, then `test-writer`), wait for each, spawn `verifier` unnamed on
   the working tree, then go to step 6.
2. **Tasks.** One task per plan item, subject `impl: <files>` or `test: <files>` exactly as the
   plan lists them; then `verify: all` blocked by all of them, `safety: all` blocked by verify,
   `docs: all` blocked by safety. No two tasks share a file. A hook rejects any other subject.
   Without the Task tools, keep the same list in your reply and assign by message.
3. **Team.** In one turn spawn the teammates, named by role and number: one `implementer-fast`
   per `[fast]` item as `fast-N`, one `implementer` per `[careful]` item as `careful-N`, up to
   `team_cap` in total; the rest stay pending for self-claim. Spawn one `test-writer` as
   `tests-1` with the whole plan. Each spawn prompt carries the item text verbatim, the file
   list, and "claim your task; when done, mark it completed". Teammates share this working
   tree, so do not pass `isolation`.
4. **Wait.** Implement nothing yourself. If a task sits in progress with no activity, message
   that teammate once.
5. **Verify.** When every impl and test task is done, spawn `verifier` as `verify-1` on the
   verify task. It messages owners their FAIL rows itself, two rounds at most. For BLOCKED
   rows, ask the user whether to run `/heavy <check>`.
6. **Safety and docs.** If the plan said `physics-reviewer needed: yes`, or the diff touches a
   `sensitive_paths` prefix, spawn `physics-reviewer` unnamed on the diff; a FAIL goes to the
   file's owner, two rounds at most. Otherwise say why it was skipped. Then spawn `docs-writer`
   on the docs task.
7. **Close.** Ask each teammate to shut down, then print: the verifier table, a commit message
   (imperative first line under 72 characters, body naming the rulebook sections touched), and
   a PR description that fills `.github/pull_request_template.md` from the verifier table. Do
   not run `git commit`; the user ships with `/pr`.
