# ruff: noqa: E501
"""UFL-LITE-001 pure invariant checks shared by the frozen UFLG0 evaluator, the targeted tests and the static mutation controls.
No network, no training, no inference. The frozen baseline is reports/ufl_lite/ufl_lite_001/zero_drift_baseline.json."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "reports/ufl_lite/ufl_lite_001/zero_drift_baseline.json"
CONTRACT = "configs/ufl_lite/user_bound_fl_participation_v1.json"
CANONICAL_CANDIDATE_DIGEST = "3f0b7762ae7e05f21eb1709521404ed4d7968cae34f89e1797a0cbabd47c70e4"
CLIENT_IDS = tuple(f"SIM_FL_SITE_{i:02d}" for i in range(8))
RELEASE_TAGS = {"capstone-release-v1": "3ad1b07408a0c3556fbc5039f1a7a4fee824db96", "capstone-clerk-connected-v1": "4cb20ec1093f3a8697827abfffc1e5c1fd787055"}
# modules the future identity binding must REUSE UNCHANGED, the scientific artifacts and the accepted auth implementation
REUSED_UNCHANGED = (
    "product/federation/service.py", "product/federation/local_cohort.py", "product/federation/client.py", "product/federation/client_v2.py", "product/federation/update_bridge.py", "product/federation/execution_binding.py",
    "product/federation/replay.py", "product/federation/secagg_shadow.py", "product/edge/local_training_buffer.py", "product/edge/label_adapter.py", "capstone_persistence/federation_store.py",
    "federated/aggregation.py", "federated/wearable_fl_system_v1.py", "federated/wearable_fl_runner_v1.py", "federated/model_v2_fl.py", "federated/model_v2_fedprox.py", "federated/wearable_fl_secagg_shadow_v1.py",
    "product/models/governance.py", "product/models/registry.py", "api/product_app_v1_2.py", "api/product_app_v1_3.py",
)
SCIENTIFIC = ("checkpoints/MODEL_V2_FINAL.pt", "artifacts/CAL_V2.json", "artifacts/FEDPROX_MU_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "configs/model_v2/fl_init_v2.yaml",
              "reports/model_v2/v2_fl_005/federation_run.json", "reports/model_v2/v2_fl_005/cohort_manifest_run.json")
AUTH_FILES = ("product/auth/clerk.py", "product/auth/resolver.py", "product/auth/demo.py", "product/auth/factory.py", "frontend/src/lib/product/auth.ts")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hashes(root: Path, paths: tuple[str, ...]) -> dict[str, str]:
    return {p: sha(root / p) for p in paths if (root / p).exists()}


def load_baseline(root: Path = ROOT) -> dict[str, Any]:
    return json.loads((root / BASELINE).read_text())


def cohort_ok(client_ids: list[str] | tuple[str, ...]) -> dict[str, Any]:
    failures = []
    if len(client_ids) != 8:
        failures.append("client_count_not_8")
    if tuple(client_ids) != CLIENT_IDS:
        failures.append("client_ids_changed")
    return {"ok": not failures, "failures": failures}


def site00_ok(dataset_sha: str, example_count: int, baseline: dict[str, Any]) -> dict[str, Any]:
    failures = []
    if dataset_sha != baseline["datasets"]["SIM_FL_SITE_00"]["dataset_sha256"]:
        failures.append("site00_dataset_changed")
    if example_count != baseline["datasets"]["SIM_FL_SITE_00"]["local_example_count"]:
        failures.append("site00_example_count_changed")
    return {"ok": not failures, "failures": failures}


IDENTITY_LEAK = re.compile(r"clerk|user_[A-Za-z0-9]{6,}|@[A-Za-z0-9.-]+\.[a-z]{2,}|display_name|email|auth_session|sess_[A-Za-z0-9]{6,}", re.I)


def identity_in_payload(payload: Any) -> list[str]:
    """Keys/values of an FL update envelope or artifact that look like a Clerk identity (must be empty)."""
    hits: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if IDENTITY_LEAK.search(str(k)):
                    hits.append(f"{path}/{k}")
                walk(v, f"{path}/{k}")
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str) and IDENTITY_LEAK.search(node) and len(node) < 200:
            hits.append(f"{path}='{node[:30]}'")

    walk(payload, "")
    return hits


def candidate_digest_ok(digest: str) -> bool:
    return digest == CANONICAL_CANDIDATE_DIGEST


def monitoring_isolation_audit(root: Path) -> dict[str, Any]:
    """Federation + edge/training code must not import monitoring/history/session/auth stores."""
    banned = re.compile(r"^\s*(from|import)\s+(product\.history|product\.monitoring|product\.session|product\.sessions|capstone_persistence\.session_evidence_store|product\.auth|capstone_persistence\.store)\b", re.M)
    failures = []
    for rel in ("product/federation", "product/edge", "federated"):
        for p in (root / rel).rglob("*.py"):
            if banned.search(p.read_text(errors="ignore")):
                failures.append(str(p.relative_to(root)))
    return {"ok": not failures, "failures": failures}


def class_audit(root: Path) -> dict[str, Any]:
    """No new FL client class and no new training buffer in the federation/edge/federated packages."""
    client = re.compile(r"^class\s+(User|Clerk|Personal|RealUser|OwnerBound|Authenticated)\w*Fl\w*Client\w*|^class\s+(User|Clerk|Personal|RealUser)\w*Client\b", re.M | re.I)
    buffer = re.compile(r"^class\s+(User|Clerk|Personal|RealUser|OwnerBound)\w*(Training)?Buffer\w*", re.M | re.I)
    failures = []
    for rel in ("product/federation", "product/edge", "federated"):
        for p in (root / rel).rglob("*.py"):
            text = p.read_text(errors="ignore")
            if client.search(text):
                failures.append(f"new_client_class:{p.relative_to(root)}")
            if buffer.search(text):
                failures.append(f"new_training_buffer:{p.relative_to(root)}")
    return {"ok": not failures, "failures": failures}


def hash_drift(root: Path, baseline: dict[str, Any], group: str) -> list[str]:
    return sorted(p for p, h in baseline["protected_hashes"][group].items() if not (root / p).exists() or sha(root / p) != h)


def global_view_binding_audit(root: Path) -> dict[str, Any]:
    """The GLOBAL client list page must never present a user binding."""
    failures = []
    for rel in ("frontend/src/routes/app/federation/clients/+page.svelte",):
        p = root / rel
        if p.exists() and re.search(r"MY EDGE CLIENT|AUTHENTICATED_OWNER|ownerBound", p.read_text(errors="ignore")):
            failures.append(rel)
    return {"ok": not failures, "failures": failures}


def tags_ok(actual: dict[str, str]) -> bool:
    return all(actual.get(t) == sha_ for t, sha_ in RELEASE_TAGS.items())


def candidate_state_ok(candidate: dict[str, Any]) -> bool:
    return candidate.get("production_deployed") is False and candidate.get("governance_status") == "ACCEPTED_TO_SANDBOX" and candidate.get("sandbox_status") == "IN_SANDBOX"
