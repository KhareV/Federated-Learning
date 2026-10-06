# ruff: noqa: E501
"""CAP-011: clean-clone harness input isolation, exact target SHA, no copy-in / rescue path."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from scripts import capstone_release_lib as lib

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts/run_capstone_clean_release.py"
CLEAN = json.loads((ROOT / "configs/capstone/cap_011_clean_clone_protocol_v1.json").read_text())


def _repo(files: dict[str, str]) -> Path:
    d = Path(tempfile.mkdtemp(prefix="caprel_"))
    for args in (["init", "-q"], ["config", "user.email", "t@x"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True)
    for rel, body in files.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(body)
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=d, check=True, capture_output=True)
    return d


@pytest.mark.parametrize("rel,kind", [
    ("src/injected.py", "untracked_file_manual_injection"), (".venv/bin/python", "copied_python_environment"), ("frontend/node_modules/x/i.js", "copied_node_modules"),
    ("frontend/build/index.html", "copied_frontend_build"), (".env", "developer_dotenv"), ("state/product.sqlite3", "copied_runtime_state"),
    ("artifacts/candidates/CAPSTONE_FL_CANDIDATE_0001/w.bin", "copied_candidate_artifact"), ("data/raw/mitdb/1.0.0/100.dat", "copied_raw_data"),
])
def test_pre_install_audit_rejects_every_kind_of_copied_input(rel, kind) -> None:
    d = _repo({"README.md": "r", "frontend/package.json": "{}"})
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=d, capture_output=True, text=True).stdout.split()
        assert lib.pre_install_audit(d, tracked)["ok"]
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text("x")
        result = lib.pre_install_audit(d, tracked)
        assert not result["ok"] and kind in {v["kind"] for v in result["violations"]}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_python_environment_must_be_the_fresh_clone_venv(tmp_path) -> None:
    dev, clone = tmp_path / "dev", tmp_path / "clone"
    for base in (dev, clone):
        (base / ".venv/bin").mkdir(parents=True)
        (base / ".venv/bin/python").write_text("")
    assert lib.check_python_env(clone / ".venv/bin/python", clone, dev)["ok"]
    assert not lib.check_python_env(dev / ".venv/bin/python", clone, dev)["ok"]
    assert not lib.check_python_env(Path(sys.executable), clone, dev)["ok"]


def test_harness_reads_nothing_from_the_development_checkout_and_has_no_rescue_path() -> None:
    body = HARNESS.read_text()
    code = "\n".join(ln for ln in re.sub(r'""".*?"""', "", body, flags=re.S).splitlines() if not ln.strip().startswith("#"))
    for pattern in (r"shutil\.copy", r"shutil\.move", r"copytree", r'"cp"', r'"rsync"', r"os\.symlink", r"--force", r"git.{0,12}worktree", r'"--reference"', r'"--shared"', r'"--local"'):
        assert not re.search(pattern, code), pattern
    assert "pip" in CLEAN["prohibited"][-1] or "rescue" in CLEAN["prohibited"][-1]
    # only the three allowed development-side inputs are read: remote URL, the expected SHA (argument) and this script
    assert code.count("DEV_ROOT") <= 12 and "ambient=True" in code and code.count("ambient=True") == 1       # exactly one ambient-environment command: the git clone
    assert "No rescue" in body or "NO rescue" in body or "NO copy-in" in body


def test_harness_commands_come_from_the_frozen_protocol() -> None:
    ids = [c["id"] for c in CLEAN["commands"]]
    assert ids[:2] == ["clone", "checkout"] and "pip_dev" in ids and "npm_clerk" in ids and "demo" in ids
    harness = HARNESS.read_text()
    assert "self.protocol[\"commands\"]" in harness and "def argv" in harness
    assert not any("--no-deps" in " ".join(c["argv"] or []) for c in CLEAN["commands"])         # nothing installed outside the committed locks
    installs = [c["argv"] for c in CLEAN["commands"] if c["argv"] and "install" in c["argv"]]
    assert all("-r" in a for a in installs)                                                    # only `pip install -r <committed lock>`


def test_harness_refuses_non_full_sha_and_non_empty_evidence_dir(tmp_path) -> None:
    base = [sys.executable, str(HARNESS), "--label", "DRY", "--base-dir", str(tmp_path)]
    r = subprocess.run([*base, "--target-sha", "main", "--evidence-dir", str(tmp_path / "e1")], cwd=ROOT, capture_output=True, text=True, env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin:/opt/homebrew/bin"})
    assert r.returncode != 0 and "40-hex" in r.stderr
    (tmp_path / "e2").mkdir()
    (tmp_path / "e2/x.json").write_text("{}")
    r = subprocess.run([*base, "--target-sha", "a" * 40, "--evidence-dir", str(tmp_path / "e2")], cwd=ROOT, capture_output=True, text=True, env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin:/opt/homebrew/bin"})
    assert r.returncode != 0 and "empty" in (r.stderr + r.stdout)
    r = subprocess.run([*base, "--target-sha", "a" * 40, "--evidence-dir", str(ROOT / "reports/capstone/_never")], cwd=ROOT, capture_output=True, text=True, env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin:/opt/homebrew/bin"})
    assert r.returncode != 0 and "outside the development checkout" in r.stderr
    assert not (ROOT / "reports/capstone/_never").exists() or not any((ROOT / "reports/capstone/_never").iterdir())
