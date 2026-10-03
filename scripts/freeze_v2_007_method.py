#!/usr/bin/env python3
"""V2-007 Section 26: freeze all scientific method artifacts BEFORE the first V2-007 fit.

Generates: entry_audit.json, source_identity_audit.json, v1_reference_preflight.json,
search_budget_preflight.json, experiment_matrix.csv, validation_bootstrap_draws.npz +
manifest, the ARMED one-shot official-VALIDATION guard, and method_freeze.json binding every
frozen identity/hash this phase depends on. No neural fit, no official VALIDATION access.
"""

from __future__ import annotations

import csv
import json
import subprocess

import scripts._v2_007_lib as lib
import scripts.build_v2_007_validation_bootstrap_draws as draws_builder
from nhm.hashing import hash_file
from nhm.model_v2_official_validation_guard import arm_guard

OUT_DIR = lib.ROOT / "reports/model_v2/v2_007"


def _sh(*args: str) -> str:
    return subprocess.run(args, cwd=lib.ROOT, capture_output=True, text=True, check=False).stdout


def entry_audit() -> dict:
    with (lib.ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {r["task_id"]: r["status"] for r in csv.DictReader(handle)}
    with (lib.ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {r["gate_id"]: r["status"] for r in csv.DictReader(handle)}
    data = {
        "head": _sh("git", "rev-parse", "HEAD").strip(),
        "origin_main": _sh("git", "rev-parse", "origin/main").strip(),
        "registry": {
            "V2-006": tasks.get("V2-006"), "V2-007": tasks.get("V2-007"),
            "V2-008": tasks.get("V2-008"), "V2G5": gates.get("V2G5"),
            "V2G6": gates.get("V2G6"), "V2G7": gates.get("V2G7"),
        },
        "status": "PASS" if (
            tasks.get("V2-006") == "PASS" and tasks.get("V2-007") == "NOT_STARTED"
            and gates.get("V2G5") == "PASS" and gates.get("V2G6") == "NOT_STARTED"
        ) else "FAIL",
    }
    (OUT_DIR / "entry_audit.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data


def source_identity_audit() -> dict:
    data = {
        "protocol_v3_lock_sha256": hash_file(
            lib.ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
        ),
        "shortlist_lock_sha256": hash_file(
            lib.ROOT / "manifests/model_v2/MODEL_V2_FINALIST_SHORTLIST_V1.lock.json"
        ),
        "final_inner_manifest_sha256": hash_file(lib.FINAL_INNER_CSV),
        "model_v1_config_sha256": hash_file(lib.CONFIG_PATH),
        "expected_protocol_v3_lock_sha256": (
            "287aff4ff3fcf583524f06e6af51f23bd65949a75abef14cde80ff0936873db8"
        ),
        "expected_final_inner_manifest_sha256": (
            "bb5b4f6f7205fe37d0132ebccaca7889a916b115f5ad096ecc967940421455ce"
        ),
    }
    data["status"] = "PASS" if (
        data["protocol_v3_lock_sha256"] == data["expected_protocol_v3_lock_sha256"]
        and data["final_inner_manifest_sha256"] == data["expected_final_inner_manifest_sha256"]
    ) else "FAIL"
    (OUT_DIR / "source_identity_audit.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data


EXPECTED_V1_CHECKPOINTS = {
    20260927: (
        "021352eb067932015b657f0570ac155f8ef00af2d43864e13a110d0252bc7bfe",
        0.5328607838787021,
    ),
    20260928: (
        "a346ce6c8b38c50c0c87c4c6ed72a85b36e829c7a27878d86e1e672404db9e8d",
        0.4794350072114173,
    ),
    20260929: (
        "63ab477810e65efca388ba53eb4a290b98aad51234f600f37f12b87950af9b74",
        0.4825433837968652,
    ),
}


def v1_reference_preflight() -> dict:
    checkpoints = {}
    all_available = True
    for seed, (expected_sha, _auprc) in EXPECTED_V1_CHECKPOINTS.items():
        path = lib.ROOT / f"checkpoints/candidates/MODEL_V1/MODEL_V1_seed_{seed}_best.pt"
        observed = hash_file(path) if path.exists() else None
        match = observed == expected_sha
        all_available = all_available and match
        checkpoints[str(seed)] = {
            "path": str(path.relative_to(lib.ROOT)),
            "expected_sha256": expected_sha,
            "observed_sha256": observed,
            "match": match,
        }
    data = {
        "checkpoints": checkpoints,
        "all_three_available_and_matching": all_available,
        "reconstruction_permitted": all_available,
        "v1_retraining_forbidden": True,
        "status": "PASS" if all_available else "BLOCKED_V1_VALIDATION_PAIRED_REFERENCE_UNAVAILABLE",
    }
    (OUT_DIR / "v1_reference_preflight.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data


def search_budget_preflight() -> dict:
    data = {
        "d0_d5_max_neural_fits": 90,
        "completed_before_v2_007": 65,
        "v2_007_planned_fits": 6,
        "max_cumulative_after_v2_007": 71,
        "cap_respected": 65 + 6 <= 90,
        "status": "PASS" if 65 + 6 <= 90 else "FAIL",
    }
    (OUT_DIR / "search_budget_preflight.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data


def experiment_matrix() -> None:
    order = [
        ("MODEL_V2_TCN_MEAN", "CONFIG_V2_TCN_MEAN_ORIGINAL_V1", 20260927),
        ("MODEL_V2_TCN_MEAN", "CONFIG_V2_TCN_MEAN_ORIGINAL_V1", 20260928),
        ("MODEL_V2_TCN_MEAN", "CONFIG_V2_TCN_MEAN_ORIGINAL_V1", 20260929),
        ("MODEL_V2_TCN_MEANMAX", "CONFIG_V2_TCN_MEANMAX_ORIGINAL_V1", 20260927),
        ("MODEL_V2_TCN_MEANMAX", "CONFIG_V2_TCN_MEANMAX_ORIGINAL_V1", 20260928),
        ("MODEL_V2_TCN_MEANMAX", "CONFIG_V2_TCN_MEANMAX_ORIGINAL_V1", 20260929),
    ]
    rows = [
        {"experiment_id": lib.experiment_id(arch, seed), "architecture_id": arch,
         "schedule_id": sched, "seed": seed}
        for arch, sched, seed in order
    ]
    with (OUT_DIR / "experiment_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entry = entry_audit()
    identity = source_identity_audit()
    v1_pre = v1_reference_preflight()
    budget = search_budget_preflight()
    experiment_matrix()

    if v1_pre["status"] != "PASS":
        print("V2-007 = BLOCKED_V1_VALIDATION_PAIRED_REFERENCE_UNAVAILABLE")
        return
    if entry["status"] != "PASS" or identity["status"] != "PASS" or budget["status"] != "PASS":
        raise RuntimeError("V2-007 method freeze preconditions failed")

    draws_manifest = draws_builder.build()

    config_sha256 = hash_file(lib.ROOT / "configs/model_v2/official_validation_v1.yaml")
    preconditions = {
        "official_validation_config_sha256": config_sha256,
        "bootstrap_draws_sha256": draws_manifest["draws_npz_sha256"],
        "shortlist_lock_sha256": identity["shortlist_lock_sha256"],
        "protocol_v3_lock_sha256": identity["protocol_v3_lock_sha256"],
        "final_inner_manifest_sha256": identity["final_inner_manifest_sha256"],
    }
    guard_state = arm_guard(lib.ROOT, preconditions=preconditions)

    method_freeze = {
        "component_id": "MODEL_V2_OFFICIAL_VALIDATION_V1",
        "owner_task": "V2-007",
        "official_validation_config_sha256": config_sha256,
        "finalists": list(lib.FINALISTS),
        "seeds": list(lib.SEEDS),
        "release_seed": lib.RELEASE_SEED,
        "final_inner_manifest_sha256": identity["final_inner_manifest_sha256"],
        "v1_reference_checkpoints": v1_pre["checkpoints"],
        "bootstrap_draws": draws_manifest,
        "guard_armed": guard_state["state"] == "ARMED",
        "promotion_threshold_auprc": 0.646,
        "search_budget": budget,
        "status": "PASS",
    }
    (OUT_DIR / "method_freeze.json").write_text(
        json.dumps(method_freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("V2-007 method freeze complete.")


if __name__ == "__main__":
    main()
