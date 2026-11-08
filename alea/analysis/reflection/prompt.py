"""Build the text prompt for a large model from a report. No API call is made here."""

from __future__ import annotations

import json

RULES = """\
- Use only the data in the report below. Do not invent events, scores or causes.
- Items with source "inferred" are uncertain: say so when you rely on one.
- Items listed under "gaps" are missing; do not guess them, name what would settle them.
- Do not identify or describe any person. Refer to "the drivers" and "the robot".
- Give exactly 3 concrete driver improvements, ranked most valuable first.
- Each improvement must cite evidence from the report (metric names and numbers, or timeline times).
- Keep the whole answer under 300 words."""

OUTPUT_FORMAT = """\
1. <improvement title>
   Evidence: <metric names, numbers, times from the report>
   Certainty: measured | inferred
   Action: <what the drivers do differently next match>
2. ...
3. ...
Then one line: "Data that would sharpen this:" followed by the most useful missing item."""


def build_prompt(report: dict) -> str:
    return (
        "You are an experienced FTC driver coach reviewing one robotics match for a team.\n"
        "You get a structured report built from the robot log, the on-screen score events and "
        "a simulator baseline. You see no video.\n\n"
        f"RULES\n{RULES}\n\n"
        f"REPORT (JSON)\n{json.dumps(report, indent=2)}\n\n"
        f"ANSWER FORMAT\n{OUTPUT_FORMAT}\n"
    )


def estimate_tokens(text: str) -> int:
    """Rough token count: characters divided by 4."""
    return (len(text) + 3) // 4
