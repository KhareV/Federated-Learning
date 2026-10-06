# ruff: noqa: E501
"""UFL-LITE-001 mutation controls (15): the STATIC controls that catch future implementation errors are executed now against temporary copies /
synthetic inputs; each must fail a NAMED check and leave the working tree byte-identical. Writes mutation_controls.json (or UFL_EVD)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts import ufl_lite_lib as lib

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("UFL_EVD", ROOT / "reports/ufl_lite/ufl_lite_001"))
BASE = lib.load_baseline(ROOT)
S0 = BASE["datasets"]["SIM_FL_SITE_00"]


def with_group_copy(group: str, rel: str, mutate) -> tuple[bool, str]:
    """Copy the whole protected group to a temp tree: clean copy shows no drift; the mutation shows exactly the mutated file."""
    d = Path(tempfile.mkdtemp(prefix="uflmut_"))
    try:
        for p in BASE["protected_hashes"][group]:
            (d / p).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / p, d / p)
        clean = lib.hash_drift(d, BASE, group)
        mutate(d / rel)
        drift = lib.hash_drift(d, BASE, group)
        return (clean == [] and drift == [rel]), f"hash_drift:{group}:{rel}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def with_source(rel: str, text: str, check):
    d = Path(tempfile.mkdtemp(prefix="uflmut_"))
    try:
        for sub in ("product/federation", "product/edge", "federated"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text)
        return check(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def append(path: Path) -> None:
    path.write_text(path.read_text() + "\n# mutated\n")


MUTATIONS = (
    ("CLIENT_COUNT_BECOMES_9", lambda: ((not lib.cohort_ok([*lib.CLIENT_IDS, "SIM_FL_SITE_08"])["ok"]), "cohort_ok:client_count_not_8")),
    ("CLIENT_IDS_CHANGE", lambda: ((not lib.cohort_ok(["USER_OWNER_CLIENT", *lib.CLIENT_IDS[1:]])["ok"]), "cohort_ok:client_ids_changed")),
    ("SITE_00_DATASET_CHANGES", lambda: ((not lib.site00_ok("0" * 64, S0["local_example_count"], BASE)["ok"]), "site00_ok:site00_dataset_changed")),
    ("SITE_00_EXAMPLE_COUNT_CHANGES", lambda: ((not lib.site00_ok(S0["dataset_sha256"], S0["local_example_count"] + 1, BASE)["ok"]), "site00_ok:site00_example_count_changed")),
    ("CLERK_ID_ENTERS_MODEL_OR_UPDATE_PAYLOAD", lambda: ((bool(lib.identity_in_payload({"payload": {"client_id": "SIM_FL_SITE_00", "user_id": "user_3KJdPexample"}}))), "identity_in_payload")),
    ("MONITORING_SESSION_ENTERS_LOCAL_BUFFER", lambda: with_source("product/edge/buffer_leak.py", "from product.history import summaries\n", lambda d: ((not lib.monitoring_isolation_audit(d)["ok"]), "monitoring_isolation_audit"))),
    ("CANDIDATE_DIGEST_CHANGES", lambda: ((not lib.candidate_digest_ok("0" * 64)), "candidate_digest_ok")),
    ("AGGREGATION_IMPLEMENTATION_CHANGES", lambda: with_group_copy("reused_unchanged", "federated/aggregation.py", append)),
    ("OWNER_BOUND_CLIENT_BECOMES_A_NEW_CLASS", lambda: with_source("product/federation/user_client.py", "class UserFlClient:\n    pass\n", lambda d: ((not lib.class_audit(d)["ok"]), "class_audit:new_client_class"))),
    ("NEW_TRAINING_BUFFER_INTRODUCED", lambda: with_source("product/edge/personal.py", "class PersonalTrainingBuffer:\n    pass\n", lambda d: ((not lib.class_audit(d)["ok"]), "class_audit:new_training_buffer"))),
    ("CANDIDATE_BECOMES_DEPLOYED", lambda: ((not lib.candidate_state_ok({"production_deployed": True, "governance_status": "ACCEPTED_TO_SANDBOX", "sandbox_status": "IN_SANDBOX"})), "candidate_state_ok")),
    ("AUTH_IMPLEMENTATION_CHANGED", lambda: with_group_copy("auth", "product/auth/clerk.py", append)),
    ("SCIENTIFIC_ARTIFACT_DRIFTS", lambda: with_group_copy("scientific", "artifacts/CAL_V2.json", append)),
    ("RELEASE_TAG_MOVES", lambda: ((lib.tags_ok(dict(lib.RELEASE_TAGS)) and not lib.tags_ok({**lib.RELEASE_TAGS, "capstone-release-v1": "0" * 40})), "tags_ok")),
    ("USER_BINDING_SHOWN_GLOBALLY", lambda: _global_binding()),
)


def _global_binding() -> tuple[bool, str]:
    d = Path(tempfile.mkdtemp(prefix="uflmut_"))
    try:
        p = d / "frontend/src/routes/app/federation/clients/+page.svelte"
        p.parent.mkdir(parents=True)
        p.write_text("<b>MY EDGE CLIENT</b>")
        return ((not lib.global_view_binding_audit(d)["ok"]), "global_view_binding_audit")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    before = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    results = []
    for name, fn in MUTATIONS:
        try:
            caught, failing = fn()
        except Exception as error:   # an exception is not a catch
            caught, failing = False, f"EXCEPTION:{type(error).__name__}"
        after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
        results.append({"mutation": name, "executed_now": True, "caught": bool(caught), "failing_check": failing[:120], "restored": after == before, "applied_to": "temporary copy / synthetic input"})
        print(name, caught, failing[:60], flush=True)
    payload = {"controls": results, "all_caught": all(r["caught"] for r in results), "all_restored": all(r["restored"] for r in results), "count": len(results),
               "note": "controls 1-15 of the specification; all are static and executed in UFL-LITE-001; runtime ones (digest, updates) are additionally asserted by tests/test_ufl_lite_contract.py"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mutation_controls.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("count", "all_caught", "all_restored")}))
    return 0 if payload["all_caught"] and payload["all_restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
