"""The default entry point must select connected Clerk, never implicit DemoAuth."""

from pathlib import Path

from scripts.run_nhm import ROOT, dispatch


def test_default_uses_connected_clerk_and_builds_public_key_bundle():
    mode, args = dispatch([])
    assert mode == "CLERK"
    assert "--build" in args
    if (ROOT / ".env").is_file():
        assert args[args.index("--env-file") + 1] == str(ROOT / ".env")


def test_explicit_demo_is_the_only_demo_selection():
    mode, args = dispatch(["--demo", "--frontend-port", "5195"])
    assert mode == "DEMO"
    assert "--demo" not in args
    assert "--acknowledge-demo-auth" in args
    assert "--env-file" not in args
    assert "--build" not in args


def test_explicit_env_file_and_preflight_are_preserved():
    mode, args = dispatch(["--env-file", "/tmp/nhm-test-env", "--preflight-only"])
    assert mode == "CLERK"
    assert args.count("--env-file") == 1
    assert "--build" not in args
    mode, equals_args = dispatch(["--env-file=/tmp/nhm-test-env"])
    assert mode == "CLERK"
    assert "--env-file" not in equals_args


# ---- --durable: one workspace kept across restarts --------------------------------------------------------------------------------------------------------------------------

def test_without_durable_every_launch_keeps_the_fresh_temporary_workspace_default():
    _, args = dispatch([])
    assert "--workspace" not in args and "--mode" not in args


def test_durable_creates_the_workspace_on_first_use_and_resumes_it_afterwards(tmp_path):
    from scripts.capstone_demo_workspace import SENTINEL

    target = tmp_path / "nhm_ws"
    mode, first = dispatch(["--durable", str(target)])
    assert mode == "CLERK" and "--durable" not in first
    assert first[first.index("--workspace") + 1] == str(target) and first[first.index("--mode") + 1] == "fresh"
    target.mkdir()
    (target / SENTINEL).write_text("{}")
    _, second = dispatch(["--durable", str(target)])
    assert second[second.index("--mode") + 1] == "resume"


def test_durable_without_a_directory_uses_the_default_location_and_keeps_other_flags(tmp_path):
    from scripts.run_nhm import DEFAULT_DURABLE_WORKSPACE

    _, args = dispatch(["--durable", "--frontend-port", "5195"])
    assert args[args.index("--workspace") + 1] == str(DEFAULT_DURABLE_WORKSPACE) and "--frontend-port" in args and args[args.index("--frontend-port") + 1] == "5195"
    assert not DEFAULT_DURABLE_WORKSPACE.is_relative_to(Path(__file__).resolve().parents[1])         # outside the repository, as the workspace layer requires
    mode, demo = dispatch(["--demo", "--durable", str(tmp_path / "w2")])
    assert mode == "DEMO" and demo[demo.index("--mode") + 1] == "fresh"
