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


DEFAULT_DURABLE_WORKSPACE = Path.home() / ".nhm" / "demo_workspace"


def durable_workspace_args(args: list[str]) -> list[str]:
    """``--durable [DIR]`` keeps ONE workspace across restarts: it is created on first use and resumed afterwards, so runs, History, journals and exports are still there after a restart.
    Without it every launch uses a fresh temporary workspace (unchanged default). The directory must be outside the repository (the workspace layer enforces that)."""
    if "--durable" not in args:
        return args
    index = args.index("--durable")
    directory = Path(args[index + 1]).expanduser() if index + 1 < len(args) and not args[index + 1].startswith("--") else DEFAULT_DURABLE_WORKSPACE
    rest = args[:index] + args[index + (2 if index + 1 < len(args) and not args[index + 1].startswith("--") else 1):]
    from scripts.capstone_demo_workspace import SENTINEL

    mode = "resume" if (directory / SENTINEL).exists() else "fresh"
    return [*rest, "--workspace", str(directory), "--mode", mode]


def dispatch(argv: list[str]) -> tuple[str, list[str]]:
    args = durable_workspace_args(list(argv))
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
