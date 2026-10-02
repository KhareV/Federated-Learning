#!/usr/bin/env python3
"""Create the MODEL_V2_RESEARCH_PROTOCOL_V1 component lock (V2-001).

This is a V2 component lock, NOT a new canonical Fxx freeze registry row. It binds the
machine-readable (configs/model_v2/research_protocol_v1.yaml) and human-readable
(docs/MODEL_V2_RESEARCH_PROTOCOL_V1.md) protocol documents by hash so any later mutation is
detectable; any future change requires an explicit MODEL_V2_RESEARCH_PROTOCOL_V2 successor.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "configs/model_v2/research_protocol_v1.yaml"
MD_PATH = ROOT / "docs/MODEL_V2_RESEARCH_PROTOCOL_V1.md"
DESTINATION = ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"


def main() -> None:
    protocol = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))

    lock = {
        "lock_id": "MODEL_V2_RESEARCH_PROTOCOL_V1",
        "status": "FROZEN_RESEARCH_PROTOCOL",
        "owner_task": "V2-001",
        "lineage": "MODEL_V2",
        "no_new_canonical_freeze_registry_row": True,
        "canonical_task_sequence_unaffected": True,
        "protocol_yaml_path": "configs/model_v2/research_protocol_v1.yaml",
        "protocol_yaml_sha256": hash_file(YAML_PATH),
        "protocol_md_path": "docs/MODEL_V2_RESEARCH_PROTOCOL_V1.md",
        "protocol_md_sha256": hash_file(MD_PATH),
        "fixed_scientific_constants": protocol["fixed_scientific_constants"],
        "model_seeds": protocol["model_seeds"],
        "primary_metrics": protocol["primary_metrics"],
        "patient_cluster_bootstrap_seed": protocol["patient_cluster_bootstrap"][
            "bootstrap_seed_value"
        ],
        "architecture_ids": [
            protocol["architectures"]["ARCH_A"]["component_id"],
            protocol["architectures"]["ARCH_B"]["component_id"],
            protocol["architectures"]["ARCH_C"]["component_id"],
        ],
        "practical_improvement_rule_min_delta_auprc": protocol[
            "architecture_search_policy"
        ]["practical_improvement_rule_min_delta_auprc"],
        "hybrid_trigger_condition": protocol["hybrid_trigger"]["condition"],
        "official_validation_promotion_requirement": protocol["official_validation"][
            "promotion_requirement"
        ],
        "calibration_policy_component_id": protocol["calibration_policy"][
            "component_id"
        ],
        "runtime_acceptance_guardrails": protocol["runtime_acceptance_guardrails"],
        "change_control": (
            "This lock is never mutated in place. Any change to the MODEL_V2 scientific "
            "protocol requires an explicit, additive MODEL_V2_RESEARCH_PROTOCOL_V2 successor "
            "lock with this lock preserved byte-identical as its predecessor."
        ),
    }

    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(hash_file(DESTINATION))


if __name__ == "__main__":
    main()
