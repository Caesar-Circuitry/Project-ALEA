"""The container guard: non-lead agents run shell work only through the dev container."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".claude" / "hooks"
GUARD = HOOKS / "guard_container.py"
LEAD_GUARD = HOOKS / "guard_lead.py"
DEVCONTAINER = ROOT / ".devcontainer" / "cpu"


def run(
    hook: Path, payload: dict, env: dict[str, str] | None = None, stdin: str | None = None
) -> int:
    full_env = {k: v for k, v in os.environ.items() if k != "ALEA_ALLOW_HOST_AGENT_SHELL"}
    full_env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    full_env.update(env or {})
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload) if stdin is None else stdin,
        capture_output=True,
        text=True,
        env=full_env,
    )
    return proc.returncode


def bash(command: str, agent: str | None = "implementer") -> dict:
    payload: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
    if agent:
        payload["agent_type"] = agent
    return payload


@pytest.mark.parametrize(
    "command",
    [
        "just dev uv run pytest -q",
        "docker exec alea-dev ls",
        "just dev-status",
        "just dev bash -c 'ls && rm x; echo $(pwd) | cat'",
        'just dev bash -c "git status; ls"',
        "DEV_CWD=/home/u/proj/sub just dev ls",
        "docker exec -w /home/u/proj/sub alea-dev ls",
        "just dev ls 2>&1",
        "just dev --set x y",  # just 1.45 passes these on as recipe args
        "just dev --justfile /tmp/j ls",
        "docker exec alea-dev --privileged ls",  # after the container name: a command argument
    ],
)
def test_allowed_in_container(command: str) -> None:
    assert run(GUARD, bash(command)) == 0


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf x",
        "just dev ls; rm x",
        "just dev ls && curl x",
        "just dev ls | tee x",
        "just dev ls > out.txt",
        "git push",
        "git status",
        "docker run alpine ls",
        "docker exec other ls",
        "docker exec -u root alea-dev ls",
        "docker exec alea-dev",
        "just dev",
        "just dev-up",
        "just sync",
        "cat .env",
        "echo $(x)",
        "just dev ls `x`",
        "just dev echo $HOME",
        'just dev echo "$(id)"',
        "just dev ls &",
        "just dev ls >&file",
        "just dev ls &>file",
        "just dev ls\nrm x",
        "DEV_NETWORK=host just dev ls",
        "just dev 'unterminated",
    ],
)
def test_blocked_on_host(command: str) -> None:
    assert run(GUARD, bash(command)) == 2


def test_lead_and_plain_sessions_untouched() -> None:
    assert run(GUARD, bash("rm -rf x", agent="lead")) == 0
    assert run(GUARD, bash("rm -rf x", agent=None)) == 0
    outside = {"tool_name": "Write", "tool_input": {"file_path": "/etc/x"}, "agent_type": "lead"}
    assert run(GUARD, outside) == 0


@pytest.mark.parametrize("tool", ["Edit", "Write", "MultiEdit"])
def test_file_tools_confined_to_project(tool: str, tmp_path: Path) -> None:
    def payload(path: str) -> dict:
        return {"tool_name": tool, "tool_input": {"file_path": path}, "agent_type": "implementer"}

    assert run(GUARD, payload(str(ROOT / "alea" / "x.py"))) == 0
    assert run(GUARD, payload("alea/x.py")) == 0
    assert run(GUARD, payload(str(tmp_path / "x.py"))) == 2
    assert run(GUARD, payload(str(ROOT / ".." / "other" / "x.py"))) == 2
    assert run(GUARD, payload("../x.py")) == 2
    assert run(GUARD, payload("")) == 2


def test_symlink_out_of_project_is_blocked(tmp_path: Path) -> None:
    link = tmp_path / "proj" / "link"
    (tmp_path / "proj").mkdir()
    (tmp_path / "outside").mkdir()
    try:
        link.symlink_to(tmp_path / "outside", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not available")
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(link / "x.py")},
        "agent_type": "implementer",
    }
    assert run(GUARD, payload, env={"CLAUDE_PROJECT_DIR": str(tmp_path / "proj")}) == 2


@pytest.mark.parametrize("bad", ["", "not json", "[1, 2]", "null"])
def test_unreadable_input_fails_closed(bad: str) -> None:
    assert run(GUARD, {}, stdin=bad) == 2


def test_bypass_env() -> None:
    env = {"ALEA_ALLOW_HOST_AGENT_SHELL": "1"}
    assert run(GUARD, bash("rm -rf x"), env=env) == 0


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("just dev-up", 0),
        ("just dev-down", 0),
        ("just dev-status", 0),
        ("just dev ls", 2),
        ("just dev uv run pytest", 2),
    ],
)
def test_lead_runs_container_lifecycle_not_dev(command: str, expected: int) -> None:
    assert run(LEAD_GUARD, bash(command, agent="lead")) == expected


def test_devcontainer_files() -> None:
    assert (DEVCONTAINER / "Dockerfile").is_file()
    config = json.loads((DEVCONTAINER / "devcontainer.json").read_text(encoding="utf-8"))
    assert config["remoteUser"] == "dev"
    assert config["postCreateCommand"] == "just sync"
    mounts = json.dumps(config.get("mounts", [])) + json.dumps(config.get("workspaceMount", ""))
    for forbidden in (".ssh", ".gitconfig", ".config/gh", ".netrc"):
        assert forbidden not in mounts
    dockerfile = (DEVCONTAINER / "Dockerfile").read_text(encoding="utf-8")
    assert "UV_PROJECT_ENVIRONMENT=/home/dev/.venv" in dockerfile
    assert "USER dev" in dockerfile


def test_dev_start_mounts() -> None:
    """The repo mounts at its own path; hooks and config are read-only overlays."""
    just = (ROOT / "justfile").read_text(encoding="utf-8")
    start = just.split("dev-start:\n", 1)[1].split("\n\n", 1)[0]
    assert '-v "{{dev_root}}:{{dev_root}}"' in start
    assert "{{dev_ro_hooks}}" in start
    assert "{{dev_ro_config}}" in start
    assert "-v alea-dev-venv:/home/dev/.venv" in start
    assert "-v alea-dev-uv-cache:/home/dev/.cache/uv" in start
    assert "--cap-drop=ALL" in start
    assert "--security-opt=no-new-privileges" in start
    assert "--network {{dev_network}}" in start
    assert '/.git/hooks:" + dev_root + "/.git/hooks:ro' in just
    assert '/.git/config:" + dev_root + "/.git/config:ro' in just
    assert '"-v /dev/null:" + dev_root + "/.env:ro"' in just
    for forbidden in (".ssh", ".gitconfig", ".config/gh", ".netrc"):
        assert forbidden not in start


def test_devcontainer_json_overlays() -> None:
    config = json.loads((DEVCONTAINER / "devcontainer.json").read_text(encoding="utf-8"))
    mounts = config["mounts"]
    for name in ("hooks", "config"):
        assert any(f".git/{name}," in m and "readonly" in m for m in mounts), name
    assert config["workspaceFolder"] == "${localWorkspaceFolder}"
    assert "target=${localWorkspaceFolder}," in config["workspaceMount"]
    assert any("alea-dev-venv" in m for m in mounts)
    # Parity with `dev-start`: .git/info and .git/modules are overlaid there only when they exist,
    # and .env is masked there only when it exists. devcontainer.json cannot express "if present",
    # so it deliberately omits all three; this assertion pins that documented difference.
    just = (ROOT / "justfile").read_text(encoding="utf-8")
    for name in ("info", "modules"):
        assert f'/.git/{name}:" + dev_root + "/.git/{name}:ro' in just
        assert not any(f".git/{name}," in m for m in mounts)
    assert not any(".env" in m for m in mounts)


def test_dev_checks_overlays_before_running() -> None:
    just = (ROOT / "justfile").read_text(encoding="utf-8")
    assert "dev *args: _dev-check" in just
    check = just.split("_dev-check:\n", 1)[1].split("\n\n", 1)[0]
    assert ".git/config" in check
    assert "/proc/self/mountinfo" in check


def test_windows_dev_recipe_refuses() -> None:
    just = (ROOT / "justfile").read_text(encoding="utf-8")
    windows = just.split("[windows]\ndev *args:\n", 1)[1].split("\n\n", 1)[0]
    assert "error(" in windows
    assert "WSL2" in windows


def _read(tool: str, key: str, value: str, agent: str | None = "implementer") -> dict:
    payload: dict = {"tool_name": tool, "tool_input": {key: value}}
    if agent:
        payload["agent_type"] = agent
    return payload


def _scratch() -> Path:
    import tempfile

    return Path(tempfile.gettempdir(), f"claude-{os.getuid()}")


@pytest.mark.parametrize(
    ("tool", "key"), [("Read", "file_path"), ("Glob", "path"), ("Grep", "path")]
)
def test_read_tools_confined(tool: str, key: str, tmp_path: Path) -> None:
    assert run(GUARD, _read(tool, key, str(ROOT / "alea" / "x.py"))) == 0
    assert run(GUARD, _read(tool, key, "alea/x.py")) == 0
    assert run(GUARD, _read(tool, key, str(ROOT))) == 0
    assert run(GUARD, _read(tool, key, str(Path.home() / ".ssh" / "id_ed25519"))) == 2
    assert run(GUARD, _read(tool, key, "~/.config/gh/hosts.yml")) == 2
    assert run(GUARD, _read(tool, key, "/etc/passwd")) == 2
    assert run(GUARD, _read(tool, key, "../../etc/passwd")) == 2
    assert run(GUARD, _read(tool, key, str(tmp_path / "x"))) == 2
    assert run(GUARD, _read(tool, key, str(tmp_path / "x"), agent="lead")) == 0
    assert run(GUARD, _read(tool, key, str(tmp_path / "x"), agent=None)) == 0


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="needs a POSIX uid")
def test_read_scratchpad_allowed() -> None:
    scratch = _scratch()
    assert run(GUARD, _read("Read", "file_path", str(scratch / "sess" / "notes.txt"))) == 0
    assert run(GUARD, _read("Read", "file_path", str(scratch / ".." / "other"))) == 2
    # the scratchpad is read-only for the edit tools
    assert run(GUARD, _read("Write", "file_path", str(scratch / "x"))) == 2


def test_read_symlink_escape_blocked(tmp_path: Path) -> None:
    (tmp_path / "proj").mkdir()
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret").write_text("x", encoding="utf-8")
    try:
        (tmp_path / "proj" / "link").symlink_to(tmp_path / "outside", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not available")
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path / "proj")}
    payload = _read("Read", "file_path", str(tmp_path / "proj" / "link" / "secret"))
    assert run(GUARD, payload, env=env) == 2


def test_glob_pattern_and_missing_path() -> None:
    assert run(GUARD, _read("Glob", "pattern", "**/*.py")) == 0
    assert run(GUARD, _read("Glob", "pattern", "/home/*/.ssh/*")) == 2
    assert run(GUARD, _read("Glob", "pattern", "~/.ssh/*")) == 2
    assert run(GUARD, _read("Glob", "pattern", "../*/secret")) == 2
    assert run(GUARD, _read("Glob", "pattern", str(ROOT / "alea" / "*.py"))) == 0
    assert run(GUARD, _read("Grep", "pattern", "/etc/passwd")) == 0  # a regex, not a path
    assert run(GUARD, _read("Grep", "glob", "/etc/*")) == 2
    assert run(GUARD, _read("Read", "offset", "1")) == 2  # Read without a path blocks
