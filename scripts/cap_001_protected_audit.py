"""CAP-001 protected-artifact audit.

``entry`` hashes (SHA-256) every git-tracked file plus the named protected scientific/runtime
components. ``final`` re-hashes and requires ZERO drift: every file tracked at entry must be
byte-identical, and every new file must live inside the additive capstone namespace.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_001"
ADDITIVE_PREFIXES = (
    "manifests/capstone/", "configs/capstone/", "contracts/capstone/", "docs/capstone/",
    "reports/capstone/", "artifacts/capstone/", "product/", "tests/test_capstone_",
    "scripts/cap_001_",
)
# Named protected components (CAP-001 prompt section 3) -> registry / lock evidence.
PROTECTED_COMPONENTS = (
    "MODEL_V1", "CAL_V1", "GATEWAY_ARTIFACT_V1", "MODEL_V2_FINAL", "CAL_V2", "GAP_POLICY_V1",
    "GATEWAY_ARTIFACT_V2", "PREPROC_V1", "QUALITY_V1", "ECG_HR_CONTEXT_V2", "ALERT_POLICY_V1",
    "ALERT_POLICY_V1_MODEL_V2_BINDING", "API_SCHEMA_V1", "API_RUNTIME_V2", "API_RUNTIME_V2_1",
    "DEFAULT_RUNTIME_BINDING_V2", "ROLLBACK_RUNTIME_BINDING_V1", "SOFTWARE_SYSTEM_V2",
    "MODEL_V2_FL_PROTOCOL_V1", "MODEL_V2_FL_PROTOCOL_V2", "FL_INIT_V2", "FL_IID_MODEL_V2_V1",
    "FL_NON_IID_MODEL_V2_V1", "FEDPROX_METHOD_V2", "FEDPROX_MU_V2", "V2_FL_EVAL_PROTOCOL_V1",
    "V2_FL_TEST_FAMILY_V1", "SECAGG_METHOD_V2", "SECAGG_CONFIG_V2", "WEARABLE_SIM_FL_COHORT_V1",
    "V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1", "WEARABLE_SIM_FL_SYSTEM_REPLAY_V1",
    "VIRTUAL_FL_CLIENT_SOURCE_V1", "WEARABLE_SIM_FL_SECAGG_COMPAT_V1",
    "MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1", "MODEL_V2_COMPLETE_REPRO_V1",
    "SYSTEM_V2_RELEASE_POLICY_V1", "SYSTEM_V2_RELEASE_DECISION_V1",
    "SYSTEM_V2_RELEASE_MANIFEST_V1",
)
# Components whose frozen bytes live in a non-lock file (resolved against the repository layout).
NAMED_PATH_OVERRIDES = {
    "MODEL_V1": ("checkpoints/MODEL_V1.pt",),
    "PREPROC_V1": ("manifests/preprocessing/PREPROC_V1.lock.json",),
    "QUALITY_V1": ("configs/quality_v1.yaml",),
    "GAP_POLICY_V1": ("preprocessing/gaps.py",),
    "API_SCHEMA_V1": ("contracts/API_SCHEMA_V1.json",),
}
# Frozen evidence directories (V2 FL lineage, reproducibility, release): digest of all file hashes.
EVIDENCE_DIRECTORIES = (
    "reports/model_v2/v2_fl_001", "reports/model_v2/v2_fl_002", "reports/model_v2/v2_fl_003",
    "reports/model_v2/v2_fl_eval_001", "reports/model_v2/v2_fl_004", "reports/model_v2/v2_fl_005",
    "reports/model_v2/v2_014", "reports/model_v2/v2_rel_001",
)
EXTRA_PROTECTED_FILES = (
    "contracts/API_SCHEMA_V1.json", "contracts/openapi_v1.json", "contracts/sample_schema_v1.json",
    "checkpoints/MODEL_V2_FINAL.pt", "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts",
    "artifacts/CAL_V2.json", "api/schemas.py", "api/app_default.py", "api/runtime_v2.py",
    "simulation/types.py", "simulation/stream_runtime_v2013.py",
)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout


def tracked_hashes() -> dict[str, str]:
    return {p: hash_file(ROOT / p) for p in _git("ls-files").splitlines() if (ROOT / p).is_file()}


def component_paths() -> dict[str, str | None]:
    rows: dict[str, str | None] = {}
    for reg in ("manifests/model_v2/component_registry_v1.csv",):
        with (ROOT / reg).open(newline="") as handle:
            for row in csv.DictReader(handle):
                rows[row["component_id"]] = row["lock_path"] or None
    return rows


def named_components() -> dict[str, dict[str, object]]:
    registry = component_paths()
    out: dict[str, dict[str, object]] = {}
    for name in PROTECTED_COMPONENTS:
        candidates = []
        if registry.get(name):
            candidates.append(registry[name])
        candidates += [f"artifacts/{name}.lock.json", f"artifacts/{name}.json",
                       f"manifests/model_v2/{name}.lock.json", *NAMED_PATH_OVERRIDES.get(name, ())]
        path = next((c for c in candidates if c and (ROOT / c).is_file()), None)
        out[name] = {"path": path, "sha256": hash_file(ROOT / path) if path else None,
                     "in_v2_component_registry": name in registry}
    for extra in EXTRA_PROTECTED_FILES:
        out[extra] = {"path": extra, "sha256": hash_file(ROOT / extra),
                      "in_v2_component_registry": False}
    for directory in EVIDENCE_DIRECTORIES:
        files = sorted(p for p in (ROOT / directory).rglob("*") if p.is_file())
        digest = hashlib.sha256()
        for path in files:
            digest.update(f"{path.relative_to(ROOT)}:{hash_file(path)}\n".encode())
        out[directory] = {"path": directory, "sha256": digest.hexdigest(),
                          "file_count": len(files), "in_v2_component_registry": False}
    return out


def entry() -> None:
    head = _git("rev-parse", "HEAD").strip()
    tree = tracked_hashes()
    payload = {
        "entry_sha": head, "expected_anchor": "8bbc0e1e17e314748ad7127544e46d8305efeb0c",
        "tracked_file_count": len(tree), "named_components": named_components(),
        "tracked_files_sha256": tree,
    }
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    (OUT / "upstream_protection_entry.json").write_text(text)
    unresolved = [k for k, v in payload["named_components"].items() if v["sha256"] is None]
    print(json.dumps({"entry_sha": head, "tracked": len(tree), "unresolved_named": unresolved}))


def final() -> int:
    entry_payload = json.loads((OUT / "upstream_protection_entry.json").read_text())
    base: dict[str, str] = entry_payload["tracked_files_sha256"]
    now = tracked_hashes()
    changed = sorted(p for p, h in base.items() if p in now and now[p] != h)
    removed = sorted(p for p in base if p not in now)
    # upstream_protection_entry.json itself is created in the additive namespace, so it is absent
    # from `base`; every added path must be additive-namespace.
    added = sorted(p for p in now if p not in base)
    non_additive = [p for p in added if not p.startswith(ADDITIVE_PREFIXES)]
    comps = named_components()
    comp_drift = sorted(k for k, v in comps.items()
                        if entry_payload["named_components"][k]["sha256"] != v["sha256"])
    result = {
        "entry_sha": entry_payload["entry_sha"], "head_sha": _git("rev-parse", "HEAD").strip(),
        "baseline_file_count": len(base), "modified_since_entry": changed,
        "removed_since_entry": removed, "added_count": len(added),
        "added_outside_additive_namespace": non_additive, "named_component_drift": comp_drift,
        "named_components_checked": len(comps), "protected_artifact_drift": bool(
            changed or removed or non_additive or comp_drift),
    }
    text = json.dumps(result, indent=1, sort_keys=True) + "\n"
    (OUT / "upstream_protection_final.json").write_text(text)
    print(json.dumps({k: v for k, v in result.items()}, indent=1))
    return 1 if result["protected_artifact_drift"] else 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "entry":
        entry()
    elif mode == "final":
        sys.exit(final())
    else:
        raise SystemExit("usage: cap_001_protected_audit.py entry|final")
