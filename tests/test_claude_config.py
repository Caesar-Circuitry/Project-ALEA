"""The committed Claude Code configuration keeps its shape: Sonnet default, coordinate-only lead,
pinned subagent models, Fable gated, hooks pointing at files that exist."""

from __future__ import annotations

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
    return {p.stem: frontmatter(p) for p in sorted((CLAUDE / "agents").glob("*.md"))}


def settings() -> dict:
    return json.loads((CLAUDE / "settings.json").read_text(encoding="utf-8"))


def test_settings_defaults() -> None:
    s = settings()
    assert s["model"] == "sonnet"
    assert s["agent"] == "lead"
    assert s["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] == "sonnet"
    ask = s["permissions"]["ask"]
    assert "Agent(orchestrator)" in ask
    assert "Agent(model:fable)" in ask
    assert "Bash(git push *)" in ask
    assert "Read(./.env)" in s["permissions"]["deny"]


def test_hooks_point_at_existing_scripts_and_fail_closed() -> None:
    for group in settings()["hooks"]["PreToolUse"]:
        for hook in group["hooks"]:
            script = hook["command"].split()[-1]
            assert (ROOT / script).exists(), script
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
    assert allowed == {
        "explorer",
        "implementer",
        "physics-reviewer",
        "verifier",
        "docs-writer",
        "orchestrator",
    }
    assert lead["_body"] == "", "a non-empty body would replace Claude Code's system prompt"


def test_agent_models_are_pinned() -> None:
    defs = agents()
    assert set(defs) == {
        "lead",
        "explorer",
        "implementer",
        "physics-reviewer",
        "verifier",
        "docs-writer",
        "orchestrator",
    }
    for name, fields in defs.items():
        assert fields.get("model") in MODELS, name
    assert defs["explorer"]["model"] == "haiku"
    assert defs["docs-writer"]["model"] == "haiku"
    assert defs["implementer"]["model"] == "sonnet"
    assert defs["physics-reviewer"]["model"] == "opus"
    assert defs["verifier"]["model"] == "sonnet"
    assert [n for n, f in defs.items() if f["model"] == "fable"] == ["orchestrator"]


def test_read_only_agents_have_no_write_tools() -> None:
    defs = agents()
    for name in ("explorer", "physics-reviewer", "verifier"):
        tools = defs[name]["tools"]
        assert "Edit" not in tools and "Write" not in tools, name


def test_implementer_has_stop_gate() -> None:
    text = (CLAUDE / "agents" / "implementer.md").read_text(encoding="utf-8")
    assert "subagent_gate.py" in text
    assert (CLAUDE / "hooks" / "subagent_gate.py").exists()


def test_skills_are_user_invoked_only() -> None:
    skills = list((CLAUDE / "skills").glob("*/SKILL.md"))
    assert {s.parent.name for s in skills} == {"pr", "physics-change"}
    for skill in skills:
        assert frontmatter(skill).get("disable-model-invocation") == "true", skill
