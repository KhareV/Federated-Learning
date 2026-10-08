"""The default entry point must select connected Clerk, never implicit DemoAuth."""

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
