"""Default NHM website launcher: connected Clerk TEST authentication.

Run ``python -m scripts.run_nhm`` from the repository root. An ignored root .env
is used when present; environment variables take precedence. The accepted
connected launcher validates the keys and fails closed without DemoAuth fallback.
Use ``--demo`` only when an explicitly offline faculty demo is intended.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def dispatch(argv: list[str]) -> tuple[str, list[str]]:
    args = list(argv)
    if "--demo" in args:
        args.remove("--demo")
        if "--acknowledge-demo-auth" not in args:
            args.append("--acknowledge-demo-auth")
        return "DEMO", args
    explicit_env_file = any(
        arg == "--env-file" or arg.startswith("--env-file=") for arg in args
    )
    if not explicit_env_file and (ROOT / ".env").is_file():
        args.extend(["--env-file", str(ROOT / ".env")])
    if "--build" not in args and "--preflight-only" not in args:
        args.append("--build")
    return "CLERK", args


def main(argv: list[str] | None = None) -> int:
    mode, args = dispatch(list(sys.argv[1:] if argv is None else argv))
    if mode == "DEMO":
        from scripts.run_capstone_faculty_demo import main as launch
        return launch(args)
    else:
        from scripts.run_observatory_clerk_connected import main as launch
        original_argv = sys.argv
        try:
            sys.argv = [original_argv[0], *args]
            return launch()
        finally:
            sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
