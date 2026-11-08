"""`python -m alea.web` prints the streamlit command; `--check` verifies the web extra."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

APP_PATH = Path(__file__).resolve().parent / "app.py"
MODULES = ("alea.web.common", "alea.web.study_demo", "alea.web.logs_demo")


def command() -> str:
    return f'uv run streamlit run "{APP_PATH}"'


def check() -> int:
    try:
        importlib.import_module("streamlit")
    except ImportError:
        print("streamlit is missing: install the web extra with `uv sync --extra web`.")
        return 1
    for name in MODULES:
        try:
            importlib.import_module(name)
        except ImportError as exc:
            print(f"cannot import {name}: {exc}")
            return 1
    print("web extra OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m alea.web")
    parser.add_argument("--check", action="store_true", help="verify streamlit and page modules")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    print(command())
    return 0


if __name__ == "__main__":
    sys.exit(main())
