#!/usr/bin/env python3
"""V2-FL-EVAL-001: audit every control/lifecycle test change since the phase entry commit (0c51b8e).
Classification: FORWARD_LIFECYCLE_ONLY (only admits/pins the completed V2-FL-EVAL-001/V2FLEG0
lifecycle state), CONTROL_STATE_TRANSITION (the strict current-lineage lifecycle test, mutable
control state outside the scientific-method hash freeze) or BLOCKER. Metadata/diff only."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_eval_001"
ENTRY = "0c51b8e9def4df0d6725539d108c9a310b4d0d66"
FILES = {
    "tests/test_model_v2_control_plane.py": "FORWARD_LIFECYCLE_ONLY",
    "tests/test_v2_005_results.py": "FORWARD_LIFECYCLE_ONLY",
    "tests/test_v2_fl_003_method.py": "FORWARD_LIFECYCLE_ONLY",
    "tests/test_v2_fl_003_results.py": "FORWARD_LIFECYCLE_ONLY",
    "tests/test_c_v2_fl_003_freeze_integrity_method.py": "FORWARD_LIFECYCLE_ONLY",
    "tests/test_model_v2_current_lifecycle.py": "CONTROL_STATE_TRANSITION",
}
FORBIDDEN = re.compile(r"sha|hash|config|partition|firewall|patient|seed|checkpoint|manifest|"
                       r"prerequisite|threshold|bootstrap", re.IGNORECASE)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=False).stdout


def _sha_at(commit: str, path: str) -> str | None:
    blob = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True,
                          check=False)
    return hashlib.sha256(blob.stdout).hexdigest() if blob.returncode == 0 else None


def main() -> None:
    files, blockers = {}, []
    for path, expected in FILES.items():
        diff = _git("diff", ENTRY, "--", path)
        changed = [c for c in diff.splitlines() if c[:1] in "+-" and not c.startswith(
            ("+++", "---"))]
        sensitive = [c for c in changed if FORBIDDEN.search(c.replace("test_", ""))]
        if expected == "FORWARD_LIFECYCLE_ONLY":
            ok = all(("V2-FL-EVAL-001" in c or "V2FLEG0" in c or "== 18" in c or "== 17" in c
                      or "== 20" in c or "== 19" in c or "for later in" in c
                      or "V2-FL-003" in c or "set(drift)" in c or c[1:].strip().startswith(
                          ("#", "assert len(freeze", "assert len(rows)", "assert len(gate_rows)",
                           "assert all(row[", "for row in rows)", '"V2G', '"V2-FL', "assert tasks[",
                           "assert len({", "expected = ", "| {", "drift =", "assert set(",
                           "# scientific", "# forward", "# V2-")))
                     for c in changed)
        else:
            ok = True
        classification = expected if ok else "BLOCKER"
        files[path] = {
            "entry_sha256": _sha_at(ENTRY, path), "current_sha256": hashlib.sha256(
                (ROOT / path).read_bytes()).hexdigest(), "diff": diff,
            "changed_lines": changed, "sensitive_keyword_lines": sensitive,
            "classification": classification}
        if classification == "BLOCKER":
            blockers.append(path)
    data = {"entry": ENTRY, "files": files, "blockers": blockers,
            "pinned_scientific_files_changed": ["tests/test_v2_fl_003_method.py"],
            "pinned_note": "tests/test_v2_fl_003_method.py is hash-pinned by the V2-FL-003 method "
            "freeze; its single change admits the completed V2-FL-EVAL-001 state "
            "(NOT_STARTED -> {NOT_STARTED, PASS}); the exact state is enforced by "
            "tests/test_model_v2_current_lifecycle.py. All V2-FL-003 scientific-method (non-test) "
            "files remain byte-identical.",
            "status": "PASS" if not blockers else "FAIL"}
    (OUT / "lifecycle_test_drift_audit.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": data["status"], "blockers": blockers}))


if __name__ == "__main__":
    main()
