"""Switch the agent team between usage profiles: `profile.py max|pro|--get`.

`max` and `pro` rewrite only the `model:` line of the judge agents named in `.claude/repo.json`
(`judge_agents`) and the `profile` / `profile_settings` entries of that file, then print the
result. `--get` prints the active settings and changes nothing. Run it as `just profile <name>`.
Pure stdlib.
"""

import json
import re
import sys
from pathlib import Path

CLAUDE = Path(__file__).resolve().parent
PROFILES = {
    "max": {"judge_model": "opus", "plan_critic": "always", "team_cap": 5, "team_threshold": 2},
    "pro": {
        "judge_model": "sonnet",
        "plan_critic": "only for [careful] items or plans of 3+ items",
        "team_cap": 3,
        "team_threshold": 3,
    },
}
MODEL_LINE = re.compile(r"^model:.*$", re.M)


def load(claude: Path) -> dict:
    return json.loads((claude / "repo.json").read_text(encoding="utf-8"))


def apply(name: str, claude: Path = CLAUDE) -> dict:
    """Write profile `name` into repo.json and the judge agents; return the new config."""
    settings = PROFILES[name]
    config = load(claude)
    config["profile"] = name
    config["profile_settings"] = settings
    text = json.dumps(config, indent=2) + "\n"
    (claude / "repo.json").write_text(text, encoding="utf-8", newline="\n")
    for agent in config.get("judge_agents", []):
        path = claude / "agents" / f"{agent}.md"
        head, sep, body = path.read_text(encoding="utf-8").partition("\n---\n")
        head = MODEL_LINE.sub(f"model: {settings['judge_model']}", head, count=1)
        path.write_text(head + sep + body, encoding="utf-8", newline="\n")
    return config


def describe(config: dict) -> str:
    settings = config.get("profile_settings", {})
    lines = [f"profile: {config.get('profile')}"]
    lines += [f"{key}: {value}" for key, value in settings.items()]
    lines.append(f"judge_agents: {', '.join(config.get('judge_agents', []))}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    arg = argv[0] if argv else "--get"
    if arg == "--get":
        print(describe(load(CLAUDE)))
        return 0
    if arg not in PROFILES:
        sys.stderr.write(f"usage: profile.py {'|'.join(PROFILES)}|--get\n")
        return 2
    print(describe(apply(arg)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
