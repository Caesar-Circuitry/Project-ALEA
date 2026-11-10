"""The team hooks: task subjects, the bash and test guards, the test gate and the profiles.

Each hook is a script that reads the tool call as JSON on stdin; exit 2 blocks, exit 0 allows.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".claude" / "hooks"


def run(
    script: str, payload: dict, project: Path = ROOT, **env: str
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project), **env},
    )


def bash(command: str) -> subprocess.CompletedProcess:
    return run("guard_bash.py", {"tool_name": "Bash", "tool_input": {"command": command}})


def edit(path: Path | str, old: str, new: str, project: Path = ROOT) -> subprocess.CompletedProcess:
    tool_input = {"file_path": str(path), "old_string": old, "new_string": new}
    return run("guard_tests.py", {"tool_name": "Edit", "tool_input": tool_input}, project)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A tiny git repo with the real hooks' config, one unit and one passing test."""
    (tmp_path / ".claude").mkdir()
    config = json.loads((ROOT / ".claude" / "repo.json").read_text(encoding="utf-8"))
    config["units"] = [
        {"name": "pkg", "prefixes": ["pkg/", "tests/test_pkg"], "build": None,
         "test": "uv run pytest -q -p no:cacheprovider tests", "lint": None},
    ]  # fmt: skip
    config["gate_setup"] = None
    config["gate_checks"] = ["uv run pytest -q -p no:cacheprovider tests"]
    (tmp_path / ".claude" / "repo.json").write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / ".gitignore").write_text("__pycache__/\n.scratch/\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_pkg.py").write_text(
        "def test_one() -> None:\n    assert 1 == 1\n", encoding="utf-8"
    )
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "--no-verify", "-m", "init"]):
        subprocess.run([*git, *args], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def gate(project: Path, payload: dict) -> subprocess.CompletedProcess:
    payload = {"cwd": str(project), "scratchpad_dir": str(project / ".scratch"), **payload}
    return run("test_gate.py", payload, project, ALEA_HOOK_PYTHON=sys.executable)


# --- task_shape.py


@pytest.mark.parametrize(
    "subject",
    ["impl: alea/data/importer.py", "test: tests/test_data_import.py", "verify: all",
     "safety: all", "docs: all", "impl: alea/web/app.py alea/web/common.py"],
)  # fmt: skip
def test_task_shape_allows(subject: str) -> None:
    assert run("task_shape.py", {"task_subject": subject}).returncode == 0


@pytest.mark.parametrize("subject", ["fix stuff", "impl: the importer", "impl:", "Implement auth"])
def test_task_shape_blocks(subject: str) -> None:
    proc = run("task_shape.py", {"task_subject": subject})
    assert proc.returncode == 2
    assert "<kind>: <paths>" in proc.stderr


# --- guard_bash.py


@pytest.mark.parametrize(
    "command",
    ["just dev uv run pytest -q -k test_data", "git push origin feature/x", "just lint",
     "just dev git switch -c feature/x --no-track origin/main", "just dev rm -r build",
     "uv run pytest -m 'not gpu and not slow'", "cat .env.example",
     "shasum tests/golden/golden_shots.npy"],
)  # fmt: skip
def test_guard_bash_allows(command: str) -> None:
    assert bash(command).returncode == 0, command


@pytest.mark.parametrize(
    ("command", "rule"),
    [
        ("just dev bash -c 'rm -rf alea'", "rm -rf"),
        ("git push --force origin feature/x", "git push --force"),
        ("git push -u origin feature/x", "git push -u"),
        ("git push origin main", "git push origin main"),
        ("just dev git commit --no-verify -m x", "--no-verify"),
        ("just dev uv run pytest --deselect tests/test_data_import.py::test_a", "--deselect"),
        ("just dev uv run pytest --ignore=tests/test_web_app.py", "--ignore"),
        ("just dev uv run pytest -k 'not selftest'", "-k not"),
        ("just dev git switch -c feature/x", "--no-track"),
        ("just dev bash -c 'ALEA_ALLOW_PHYSICS_EDIT=1 python edit.py'", "ALEA_ALLOW_PHYSICS_EDIT"),
        ("just dev cp /tmp/new.npy tests/golden/golden_shots.npy", "golden"),
        ("adb install app.apk", "adb"),
    ],
)
def test_guard_bash_blocks(command: str, rule: str) -> None:
    proc = bash(command)
    assert proc.returncode == 2, command
    assert rule in proc.stderr


def test_guard_bash_fails_closed() -> None:
    proc = subprocess.run(
        [sys.executable, str(HOOKS / "guard_bash.py")],
        input="not json",
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2


# --- guard_tests.py


def test_guard_tests_allows_adding_a_test(project: Path) -> None:
    path = project / "tests" / "test_pkg.py"
    new = "    assert 1 == 1\n\n\ndef test_two() -> None:\n    assert 2 == 2\n"
    assert edit(path, "    assert 1 == 1\n", new, project).returncode == 0
    assert edit(project / "pkg" / "mod.py", "X = 1", "X = 2", project).returncode == 0


def test_guard_tests_blocks_removing_a_test(project: Path) -> None:
    proc = edit(project / "tests" / "test_pkg.py", "def test_one", "def helper_one", project)
    assert proc.returncode == 2
    assert "test_one" in proc.stderr


def test_guard_tests_blocks_skip_marker(project: Path) -> None:
    path = project / "tests" / "test_pkg.py"
    new = "import pytest\n\n\n@pytest.mark.skip\ndef test_one"
    assert edit(path, "def test_one", new, project).returncode == 2
    xfail = "@pytest.mark.xfail(reason='later')\ndef test_one"
    assert edit(path, "def test_one", xfail, project).returncode == 2


def test_guard_tests_blocks_write_that_drops_tests(project: Path) -> None:
    tool_input = {"file_path": str(project / "tests" / "test_pkg.py"), "content": "X = 1\n"}
    proc = run("guard_tests.py", {"tool_name": "Write", "tool_input": tool_input}, project)
    assert proc.returncode == 2


def test_guard_tests_protected_and_append_only(project: Path) -> None:
    (project / "uv.lock").write_text("lock\n", encoding="utf-8")
    assert edit(project / "uv.lock", "lock", "other", project).returncode == 2
    golden = project / "tests" / "golden"
    golden.mkdir()
    (golden / "answers.json").write_text("{}\n", encoding="utf-8")
    assert edit(golden / "answers.json", "{}", '{"a": 1}', project).returncode == 2
    new = {"file_path": str(golden / "more.json"), "content": "{}\n"}
    assert run("guard_tests.py", {"tool_name": "Write", "tool_input": new}, project).returncode == 0


def test_guard_tests_blocks_removed_ci_step(project: Path) -> None:
    workflow = project / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    shutil.copy(ROOT / ".github" / "workflows" / "ci.yml", workflow)
    removed = edit(workflow, "      - name: Pytest\n        run: uv run pytest\n", "", project)
    assert removed.returncode == 2
    assert "Pytest" in removed.stderr
    bumped = edit(workflow, "astral-sh/setup-uv@68559e99", "astral-sh/setup-uv@00000000", project)
    assert bumped.returncode == 0


# --- test_gate.py


def test_gate_passes_on_green_unit(project: Path) -> None:
    (project / "pkg" / "mod.py").write_text("X = 2\n", encoding="utf-8")
    done = {"hook_event_name": "TaskCompleted", "task_id": "1", "task_subject": "impl: pkg/mod.py"}
    assert gate(project, done).returncode == 0
    idle = {"hook_event_name": "TeammateIdle", "teammate_name": "careful-1"}
    assert gate(project, idle).returncode == 0
    stop = {"hook_event_name": "SubagentStop", "agent_type": "implementer", "agent_id": "a1"}
    assert gate(project, stop).returncode == 0


def test_gate_blocks_on_red_unit_then_gives_up(project: Path) -> None:
    (project / "tests" / "test_pkg.py").write_text(
        "def test_one() -> None:\n    assert 1 == 2\n", encoding="utf-8"
    )
    done = {"hook_event_name": "TaskCompleted", "task_id": "7",
            "task_subject": "test: tests/test_pkg.py"}  # fmt: skip
    for _ in range(3):
        proc = gate(project, done)
        assert proc.returncode == 2
        assert "1 failed" in proc.stderr
    assert gate(project, done).returncode == 0  # the fourth try reaches the lead instead
    idle = {"hook_event_name": "TeammateIdle", "teammate_name": "tests-1"}
    assert gate(project, idle).returncode == 2
    stop = {"hook_event_name": "SubagentStop", "agent_type": "test-writer", "agent_id": "a2"}
    assert gate(project, stop).returncode == 2


def test_gate_skips_judges_and_non_code_tasks(project: Path) -> None:
    (project / "tests" / "test_pkg.py").write_text(
        "def test_one() -> None:\n    assert 1 == 2\n", encoding="utf-8"
    )
    for subject in ("verify: all", "safety: all", "docs: all", "plan: all"):
        done = {"hook_event_name": "TaskCompleted", "task_id": "9", "task_subject": subject}
        assert gate(project, done).returncode == 0, subject
    idle = {"hook_event_name": "TeammateIdle", "teammate_name": "verify-1"}
    assert gate(project, idle).returncode == 0
    stop = {"hook_event_name": "SubagentStop", "agent_type": "verifier", "agent_id": "a3"}
    assert gate(project, stop).returncode == 0


# --- test_touched.py, pre_compact.py, teamlib.py, profile.py


def test_touched_reports_and_never_blocks(project: Path) -> None:
    (project / "pkg" / "mod.py").write_text("X = 3\n", encoding="utf-8")
    payload = {"cwd": str(project), "scratchpad_dir": str(project / ".scratch")}
    proc = run("test_touched.py", payload, project, ALEA_HOOK_PYTHON=sys.executable)
    assert proc.returncode == 0
    assert "pkg: ok: 1 passed" in json.loads(proc.stdout)["systemMessage"]
    again = run("test_touched.py", payload, project, ALEA_HOOK_PYTHON=sys.executable)
    assert again.returncode == 0 and again.stdout == ""  # unchanged tree: no second run


def test_pre_compact_prints_instructions() -> None:
    proc = run("pre_compact.py", {"hook_event_name": "PreCompact", "trigger": "auto"})
    assert proc.returncode == 0
    assert "plan items" in proc.stdout and "FAIL" in proc.stdout


def test_files_map_to_units() -> None:
    sys.path.insert(0, str(HOOKS))
    teamlib = importlib.import_module("teamlib")

    config = teamlib.load_config(ROOT)
    for rel, unit in (
        ("alea/sim/conditions.py", "sim"),
        ("alea/hifi/hive.py", "hifi"),
        ("tests/test_hifi_frame.py", "hifi"),
        ("alea/data/importer.py", "data"),
        ("tests/test_web_app.py", "web"),
        (".claude/hooks/test_gate.py", "claude"),
        ("robot/build.gradle", "robot"),
        ("docs/robot-interface.md", "robot"),
        ("docs/summary.md", "docs"),
        ("pyproject.toml", "all"),
    ):
        found = teamlib.unit_for(rel, config)
        assert found and found["name"] == unit, rel


def test_profile_switch_rewrites_only_judges(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    shutil.copytree(ROOT / ".claude" / "agents", claude / "agents")
    shutil.copy(ROOT / ".claude" / "repo.json", claude / "repo.json")
    spec = importlib.util.spec_from_file_location("profile", ROOT / ".claude" / "profile.py")
    assert spec and spec.loader
    profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profile)

    def models() -> dict[str, str]:
        out = {}
        for path in (claude / "agents").glob("*.md"):
            lines = path.read_text(encoding="utf-8").splitlines()
            out[path.stem] = next((ln for ln in lines if ln.startswith("model:")), "")
        return out

    before = models()
    config = profile.apply("pro", claude)
    assert config["profile"] == "pro"
    assert config["profile_settings"]["team_cap"] == 3
    assert config["profile_settings"]["team_threshold"] == 3
    after = models()
    judges = set(config["judge_agents"])
    assert {name for name in after if after[name] != before[name]} <= judges
    assert all(after[name] == "model: sonnet" for name in judges)
    config = profile.apply("max", claude)
    assert config["profile_settings"]["team_cap"] == 5
    assert all(models()[name] == "model: opus" for name in judges)
    for text in (p.read_text(encoding="utf-8") for p in (claude / "agents").glob("*.md")):
        assert "effort: max" not in text
