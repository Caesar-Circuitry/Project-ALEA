"""The committed Claude Code configuration keeps its shape: Sonnet default, coordinate-only lead,
pinned subagent models, Fable gated, hooks pointing at files that exist, writers and judges
kept apart, and everything project-specific read from `.claude/repo.json`."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = ROOT / ".claude"
MODELS = {"haiku", "sonnet", "opus", "fable", "inherit"}


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    assert match, f"{path} has no frontmatter"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    fields["_body"] = match.group(2).strip()
    return fields


def agents() -> dict[str, dict[str, str]]:
    return {
        p.stem: frontmatter(p)
        for p in sorted((CLAUDE / "agents").glob("*.md"))
        if p.name != "README.md"
    }


def repo() -> dict:
    return json.loads((CLAUDE / "repo.json").read_text(encoding="utf-8"))


AGENTS = {
    "lead",
    "explorer",
    "planner",
    "plan-critic",
    "implementer",
    "implementer-fast",
    "test-writer",
    "physics-reviewer",
    "verifier",
    "heavy-check-operator",
    "ci-diagnoser",
    "docs-writer",
    "auditor",
    "orchestrator",
}
JUDGES = ("planner", "plan-critic", "physics-reviewer", "verifier", "heavy-check-operator")
COMMAND_SKILLS = {"pr", "physics-change", "start-pr", "audit", "feature", "plan", "verify",
                  "new-unit", "heavy"}  # fmt: skip
KNOWLEDGE_SKILLS = {"unit-tests", "fake-externals", "run-heavy-check", "new-unit-scaffold"}


def settings() -> dict:
    return json.loads((CLAUDE / "settings.json").read_text(encoding="utf-8"))


HOOK_PATH = re.compile(r'(\\?")\$CLAUDE_PROJECT_DIR/(\.claude/hooks/[\w.-]+)(\\?")')


def hook_script(command: str) -> Path:
    match = HOOK_PATH.search(command)
    assert match, f"hook must use a quoted $CLAUDE_PROJECT_DIR path: {command}"
    return ROOT / match.group(2)


def hook_commands() -> list[str]:
    """Every hook command in settings.json and in the agent frontmatter blocks."""
    commands: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            command = node.get("command")
            if isinstance(command, str):
                commands.append(command)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(settings().get("hooks", {}))
    for path in sorted((CLAUDE / "agents").glob("*.md")):
        if path.name == "README.md":
            continue
        match = re.match(r"^---\n(.*?)\n---", path.read_text(encoding="utf-8"), re.S)
        assert match, f"{path} has no frontmatter"
        commands += re.findall(r"^\s*(?:-\s*)?command:\s*(.+)$", match.group(1), re.M)
    return commands


def test_hook_commands_use_quoted_project_dir() -> None:
    hooks = [c for c in hook_commands() if ".claude/hooks/" in c]
    assert len(hooks) >= 12
    for command in hooks:
        match = HOOK_PATH.search(command)
        assert match, f"hook must use a quoted $CLAUDE_PROJECT_DIR path: {command}"
        assert match.group(1) == match.group(3)
        assert hook_script(command).is_file(), command


def test_settings_defaults() -> None:
    s = settings()
    assert s["model"] == "sonnet"
    assert s["advisorModel"] == "opus"
    assert s["agent"] == "lead"
    assert s["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] == "sonnet"
    assert s["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] in {"0", "1"}
    assert "teammateMode" not in s  # VS Code's terminal supports only in-process teammates
    ask = s["permissions"]["ask"]
    assert "Agent(orchestrator)" in ask
    assert "Agent(model:fable)" in ask
    assert "Bash(git push *)" in ask
    assert "Bash(gh pr create *)" in ask
    deny = s["permissions"]["deny"]
    assert "Read(./.env)" in deny
    assert "Bash(cat .env)" in deny  # `Bash(cat *)` is allowed, so .env needs its own deny
    assert "Bash(rm -rf *)" in deny
    for path in repo()["protected_paths"]:
        assert f"Edit(./{path})" in deny, path
    allow = s["permissions"]["allow"]
    # a plain `git commit` is neither allowed nor denied, so it always asks
    assert not [rule for rule in allow if rule.startswith("Bash(git commit")]
    assert "Bash(git commit *)" not in deny and "Bash(git commit*)" not in deny


def test_team_hooks_are_registered() -> None:
    hooks = settings()["hooks"]
    for event, script in (
        ("Stop", "test_touched.py"),
        ("TaskCreated", "task_shape.py"),
        ("TaskCompleted", "test_gate.py"),
        ("TeammateIdle", "test_gate.py"),
        ("PreCompact", "pre_compact.py"),
        ("SessionStart", "session_start.py"),
    ):
        commands = [h.get("command", "") for g in hooks[event] for h in g["hooks"]]
        assert any(script in c for c in commands), (event, script)
    pre = [h["command"] for g in hooks["PreToolUse"] for h in g["hooks"]]
    for script in ("guard_physics.py", "guard_lead.py", "guard_container.py", "guard_bash.py",
                   "guard_tests.py"):  # fmt: skip
        assert any(script in c for c in pre), script


def test_hooks_point_at_existing_scripts_and_fail_closed() -> None:
    for group in settings()["hooks"]["PreToolUse"]:
        for hook in group["hooks"]:
            assert hook_script(hook["command"]).exists(), hook["command"]
            assert hook.get("onFailure") == "block", "policy hooks must fail closed"


def test_lead_is_coordinate_only() -> None:
    lead = agents()["lead"]
    assert lead["model"] == "sonnet"
    tools = lead["tools"]
    for forbidden in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        assert not re.search(rf"\b{forbidden}\b", tools), forbidden
    allow = re.search(r"Agent\(([^)]*)\)", tools)
    assert allow, "lead must carry an Agent(...) allowlist"
    allowed = {a.strip() for a in allow.group(1).split(",")}
    assert allowed == AGENTS - {"lead"}
    for tool in ("TaskCreate", "TaskUpdate", "TaskList", "SendMessage"):
        assert tool in tools, f"the team lead needs {tool}"
    assert lead["_body"] == "", "a non-empty body would replace Claude Code's system prompt"


def test_agent_models_are_pinned() -> None:
    defs = agents()
    assert set(defs) == AGENTS
    for name, fields in defs.items():
        assert fields.get("model") in MODELS, name
    assert defs["explorer"]["model"] == "haiku"
    assert defs["docs-writer"]["model"] == "haiku"
    assert defs["implementer"]["model"] == "sonnet"
    assert defs["implementer-fast"]["model"] == "haiku"
    assert defs["test-writer"]["model"] == "sonnet"
    assert defs["plan-critic"]["model"] == "sonnet"
    assert defs["heavy-check-operator"]["model"] == "sonnet"
    # the judges follow the active profile (`just profile max|pro`)
    judge_model = repo()["profile_settings"]["judge_model"]
    assert judge_model in {"opus", "sonnet"}
    assert repo()["judge_agents"] == ["planner", "verifier", "physics-reviewer"]
    for judge in repo()["judge_agents"]:
        assert defs[judge]["model"] == judge_model, judge
    assert defs["ci-diagnoser"]["model"] == "opus"
    assert defs["auditor"]["model"] == "opus"
    assert [n for n, f in defs.items() if f["model"] == "fable"] == ["orchestrator"]
    for name, fields in defs.items():
        assert fields.get("effort") != "max", name
        if name not in {"lead", "orchestrator"}:
            assert fields["_body"].startswith("Read `CLAUDE.md`") or name in {
                "explorer", "auditor", "ci-diagnoser"}, name  # fmt: skip


def test_read_only_agents_have_no_write_tools() -> None:
    defs = agents()
    for name in ("explorer", "ci-diagnoser", "auditor", *JUDGES):
        tools = defs[name]["tools"]
        assert "Edit" not in tools and "Write" not in tools, name
        # `memory` would switch Read, Write and Edit on for the agent (subagent docs)
        assert "memory" not in defs[name], name
        assert defs[name].get("permissionMode", "default") == "default", name


def test_writers_never_judge_and_carry_the_gate() -> None:
    defs = agents()
    assert set(repo()["writer_agents"]) == {"implementer", "implementer-fast", "test-writer"}
    for name in repo()["writer_agents"]:
        text = (CLAUDE / "agents" / f"{name}.md").read_text(encoding="utf-8")
        assert "test_gate.py" in text, name
        assert "Agent" not in defs[name]["tools"], name
        assert "mark it completed" in defs[name]["_body"], name


def test_skills_commands_are_user_invoked_and_knowledge_is_agent_loaded() -> None:
    skills = {s.parent.name: frontmatter(s) for s in (CLAUDE / "skills").glob("*/SKILL.md")}
    assert set(skills) == COMMAND_SKILLS | KNOWLEDGE_SKILLS
    for name in COMMAND_SKILLS:
        assert skills[name].get("disable-model-invocation") == "true", name
    for name in KNOWLEDGE_SKILLS:
        # disable-model-invocation would also stop the preload into subagents
        assert "disable-model-invocation" not in skills[name], name
        assert skills[name].get("user-invocable") == "false", name
    for name, agent in (("plan", "planner"), ("verify", "verifier"),
                        ("heavy", "heavy-check-operator")):  # fmt: skip
        assert skills[name]["context"] == "fork" and skills[name]["agent"] == agent, name
    for name in ("feature", "new-unit"):
        assert "context" not in skills[name], f"/{name} runs in the lead, which leads the team"


def test_repo_json_drives_the_team() -> None:
    config = repo()
    assert (ROOT / config["rulebook"]).is_file()
    names = [u["name"] for u in config["units"]]
    assert len(names) == len(set(names))
    assert config["units"][-1]["prefixes"] == [""], "the last unit is the catch-all"
    for unit in config["units"]:
        for prefix in unit["prefixes"]:
            if prefix and prefix.endswith("/"):
                assert (ROOT / prefix).is_dir(), prefix
    for key in ("protected_paths", "frozen_paths"):
        for path in config[key]:
            assert list(ROOT.glob(path)), path
    assert config["profile"] in {"max", "pro"}
    for area in config["open_areas"]:
        assert {"path", "owner", "note"} <= set(area)
    for entry in config["assumed"]:
        assert {"key", "why"} <= set(entry)
    for text in (p.read_text(encoding="utf-8") for p in (CLAUDE / "agents").glob("*.md")):
        assert "effort: max" not in text


def test_auditor_is_read_only_and_audit_skill_runs_it() -> None:
    tools = {t.strip() for t in agents()["auditor"]["tools"].split(",")}
    assert tools == {"Read", "Grep", "Glob", "Bash"}
    skill = frontmatter(CLAUDE / "skills" / "audit" / "SKILL.md")
    assert skill["agent"] == "auditor"
    assert skill["context"] == "fork"
