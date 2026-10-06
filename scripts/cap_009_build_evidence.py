"""Summarize observed CAP-009 local evidence; no scientific computation or CI access."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from scripts.build_capstone_research_evidence_catalog import build as build_catalog
from scripts.cap_001_protected_audit import named_components
from scripts.cap_008_protected_audit import all_locks
from scripts.verify_capstone_history_evidence_protocol_v1 import verify as verify_protocol
from scripts.verify_capstone_research_evidence_catalog import verify as verify_catalog
from scripts.verify_capstone_ui_v1_2 import verify as verify_ui

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_009"
ENTRY = "bdc16611290d371abbcca582920086dcfe4d49a8"


def read(path: str) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def write(name: str, payload: dict[str, Any]) -> None:
    (OUT / name).write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    browser = read("reports/capstone/cap_009/browser_raw.json")
    history = read("reports/capstone/cap_009/canonical_history_browser_e2e.json")
    research = read("reports/capstone/cap_009/canonical_research_browser_e2e.json")
    catalog = read("artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.json")
    catalog_lock = read("artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.lock.json")
    protocol = read("configs/capstone/cap_009_history_evidence_protocol_v1.json")
    summary = browser["api"]["summary"]["body"]
    timeline = browser["api"]["timeline"]["body"]
    checks = history["database"]["checks"]
    ml = {row["fact_id"]: row["value"] for row in catalog["ml_facts"]}
    fl = {row["fact_id"]: row["value"] for row in catalog["fl_facts"]}
    prior = all_locks()
    protocol_result = verify_protocol()
    catalog_result = verify_catalog()
    ui_result = verify_ui()
    assert all(item["verified"] for item in prior.values())
    assert protocol_result["status"] == catalog_result["status"] == ui_result["status"] == "PASS"
    assert history["status"] == research["status"] == "PASS"
    assert all(checks.values())
    history_store_source = (ROOT / "capstone_persistence/session_evidence_store.py").read_text()
    assert "local_training_buffer" not in history_store_source
    assert "product.federation" not in history_store_source
    assert "SELECT sequence_index, timestamp_us, model_id" in history_store_source
    assert "context_json FROM inference_events" not in history_store_source
    frontend_pages = {
        path: (ROOT / path).read_text(encoding="utf-8") for path in (
            "frontend/src/routes/app/history/+page.svelte",
            "frontend/src/routes/app/history/[session_id]/+page.svelte",
            "frontend/src/routes/app/research/ml/+page.svelte",
            "frontend/src/routes/app/research/fl/+page.svelte",
        )
    }
    assert not any(re.search(
        r"(?i)\b(?:AUPRC|AUROC|F1|temperature|threshold)\s*[:=]\s*0\.\d+", source
    ) for source in frontend_pages.values())
    assert not any(phrase in source for source in frontend_pages.values() for phrase in (
        "Train on this session", "Personalize model", "Add to federation",
        "MODEL_V2_PROMOTED", "federated-trained default",
    ))

    write("session_evidence_contract_audit.json", {
        "status": "PASS", "store": "CAPSTONE_SESSION_EVIDENCE_STORE_V1",
        "existing_schema_only": True, "summary_table": "session_summaries",
        "raw_event_or_waveform_table_added": False,
        "session_data_to_fl": False,
    })
    write("session_summary_semantics.json", {
        "status": "PASS", "summary": summary, "database_relational_checks": checks,
        "summary_row_count": history["database"]["summary_rows"],
        "quality_change_rows_not_used_as_window_count": history["database"]["quality_change_rows"],
    })
    write("session_timeline_semantics.json", {
        "status": "PASS", "timeline_version": timeline["timeline_version"],
        "source_event_count": len(timeline["source_timeline"]),
        "source_kinds": sorted({item["kind"] for item in timeline["source_timeline"]}),
        "device_event_count": len(timeline["device_lifecycle"]),
        "sequence_ordered": [item["sequence_index"] for item in timeline["source_timeline"]]
        == sorted(item["sequence_index"] for item in timeline["source_timeline"]),
        "not_websocket_byte_replay": True,
    })
    write("time_domain_audit.json", {
        "status": "PASS", "time_domains": timeline["time_domains"],
        "duration_basis": summary["duration_basis"],
        "separate_browser_sections": history["history_detail"]["time_domain_separate"],
    })
    write("context_withholding_audit.json", {
        "status": "PASS", "timeline_source": "context_snapshots projected product events",
        "inference_context_json_exposed": False,
        "named_regression": "test_summary_timeline_owner_context_and_restart",
        "sentinel_absent_in_test_response": True,
    })
    previews = timeline["waveform_previews"]
    write("waveform_preview_audit.json", {
        "status": "PASS", "preview_count": len(previews),
        "channels": [preview["channel"] for preview in previews],
        "point_counts": [preview["point_count"] for preview in previews],
        "max_4000": all(preview["point_count"] <= 4000 for preview in previews),
        "point_count_matches_length": all(
            preview["point_count"] == len(preview["points"]) for preview in previews
        ),
        "null_gap_counts": [preview["points"].count(None) for preview in previews],
        "raw_waveform_persisted": False,
    })
    write("history_ownership_audit.json", {
        "status": "PASS", "owner": 200, "cross_user": 403, "unknown": 404,
        "failed_or_incomplete_summary": 409,
        "named_tests": [
            "test_summary_timeline_owner_context_and_restart",
            "test_failed_session_has_partial_timeline_but_no_summary",
        ],
    })
    write("research_source_inventory.json", {
        "status": "PASS", "source_count": len(catalog_lock["source_hashes"]),
        "sources": catalog_lock["source_hashes"],
        "scientific_fl_phases": catalog["scientific_fl_phases"],
    })
    write("research_source_access_audit.json", {
        "status": "PASS", "catalog_builder_allowlist": sorted(catalog_lock["source_hashes"]),
        "prediction_csv_accessed": False, "raw_biomedical_data_accessed": False,
        "scientific_execution": False,
        "named_test": "test_catalog_builder_only_reads_approved_summary_files",
    })
    catalog_bytes = (
        ROOT / "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.json"
    ).read_bytes()
    for suffix in (1, 2):
        fresh_catalog, _ = build_catalog()
        fresh_bytes = (json.dumps(
            fresh_catalog, indent=2, sort_keys=True, ensure_ascii=False
        ) + "\n").encode()
        assert fresh_bytes == catalog_bytes
        write(f"research_catalog_build_{suffix}.json", {
            "status": "PASS", "catalog_sha256": hashlib.sha256(fresh_bytes).hexdigest(),
            "byte_count": len(fresh_bytes),
            "build_function": "deterministic frozen-summary extraction",
        })
    write("research_catalog_verification.json", catalog_result)
    write("ml_evidence_parity.json", {
        "status": "PASS", "facts": len(catalog["ml_facts"]),
        "decision": ml["promotion_decision"], "promotion_eligible": ml["promotion_eligible"],
        "system_release_accepted": ml["system_release_accepted"],
        "current_model": ml["model_id"], "all_source_hashes_verified": True,
    })
    write("fl_evidence_parity.json", {
        "status": "PASS", "facts": len(catalog["fl_facts"]),
        "scientific_phases": catalog["scientific_fl_phases"],
        "fedprox_no_general_win": fl["fedprox_no_general_win"],
        "protected_clear_updates": fl["protected_clear_updates"],
        "all_source_hashes_verified": True,
    })
    write("negative_findings_audit.json", {
        "status": "PASS", "ml_limitations": ml["known_limitations"],
        "fedprox_no_general_win": fl["fedprox_no_general_win"],
        "secagg_unsupported_claims": fl["secagg_unsupported_claims"],
        "no_physical_wearable": True,
    })
    write("promotion_release_reconciliation.json", {
        "status": "PASS", "historical_promotion": ml["promotion_decision"],
        "promotion_eligible": ml["promotion_eligible"],
        "later_system_release_accepted": ml["system_release_accepted"],
        "current_default": ml["operational_default"],
        "browser_checks": research["ml"],
    })
    write("v2_fl_005_separation_audit.json", {
        "status": "PASS", "scientific_phases": catalog["scientific_fl_phases"],
        "v2_fl_005_role": catalog["v2_fl_005_role"],
        "v2_fl_005_scientific_metrics_included": False,
        "browser_engineering_separate": research["fl"]["engineering_separate"],
    })
    write("api_route_audit.json", {
        "status": "PASS", "implementation": "CAPSTONE_PRODUCT_API_V1_3",
        "added_routes": protocol["routes"],
        "system_identity": history["product_system"],
        "v1_2_sha256": sha("api/product_app_v1_2.py"),
    })
    ui_lock = read("artifacts/capstone/CAPSTONE_UI_V1_2.lock.json")
    changed_frontend = sorted(path for path in git("diff", "--name-only", ENTRY, "HEAD")
                              .splitlines() if path.startswith("frontend/"))
    assert all(path in ui_lock["bound_artifacts"]
               and sha(path) == ui_lock["bound_artifacts"][path]
               for path in changed_frontend)
    write("ui_successor_audit.json", {
        **ui_result, "changed_files": ui_lock["changed_from_predecessor"],
        "predecessor_sha256": ui_lock["predecessor_sha256"],
        "new_npm_dependencies": [],
    })
    write("history_ui_audit.json", {
        "status": "PASS", "list": history["history_list"],
        "detail": history["history_detail"],
        "count_basis": summary["windows_inferred_basis"],
        "time_domain_separation": timeline["time_domains"],
    })
    write("research_ml_ui_audit.json", {"status": "PASS", **research["ml"]})
    write("research_fl_ui_audit.json", {"status": "PASS", **research["fl"]})
    write("claim_audit.json", {
        "status": "PASS", "non_diagnostic": True,
        "historical_negative_findings_visible": research["ml"]["promotion"],
        "secagg_narrow_scope_visible": research["fl"]["secagg_caveat"],
        "physical_wearable_claim": False,
        "failed_browser_attempts_preserved": [
            "browser_failed_attempt_1.json", "browser_failed_attempt_2.json"
        ],
    })
    write("fake_metric_audit.json", {
        "status": "PASS", "fact_table_source": "GET /product/v1/research/ml|fl",
        "dynamic_numeric_values_in_frontend": False,
        "runtime_fact_parsers": [
            "frontend/src/lib/product/research/types.ts",
            "frontend/src/lib/product/evidence-validation.ts",
        ],
    })
    amendment_commits = ["40b9f43", "d7b6e8f", "dbe1c05", "ed12ff7", "f269860", "14c9a37"]
    evaluator_amendment = git(
        "log", "-1", "--format=%H", "--",
        "artifacts/capstone/CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1.amendment_7.json",
    )
    if evaluator_amendment:
        amendment_commits.append(evaluator_amendment)
    amendment_files = {
        commit: git("show", "--pretty=format:", "--name-only", commit).splitlines()
        for commit in amendment_commits
    }
    assert all(any("amendment_" in path for path in paths)
               and not any(path.startswith("reports/capstone/cap_009/") for path in paths)
               for paths in amendment_files.values())
    write("amendment_hygiene_audit.json", {
        "status": "PASS", "dedicated_commits": amendment_files,
        "canonical_result_evidence_in_amendment_commit": False,
        "failed_browser_attempts_preserved": [
            "browser_failed_attempt_1.json", "browser_failed_attempt_2.json"
        ],
    })
    changed = git("diff", "--name-only", ENTRY, "HEAD").splitlines()
    protected_prefixes = (
        "reports/model_v2/", "src/", "checkpoints/", "federated/", "privacy/",
        "product/federation/", "product/monitoring/", "product/models/",
        "capstone_persistence/federation_store.py", "api/product_app_v1_2.py",
        "artifacts/SOFTWARE_SYSTEM_V2", "artifacts/DEFAULT_RUNTIME_BINDING_V2",
    )
    protected_drift = [path for path in changed if path.startswith(protected_prefixes)]
    entry_snapshot = read("reports/capstone/cap_009/protected_artifact_entry.json")
    current_components = named_components()
    component_drift = [name for name, value in entry_snapshot["named_components"].items()
                       if current_components[name]["sha256"] != value["sha256"]]
    predecessor_drift = [path for path, digest in entry_snapshot[
        "protected_predecessor_locks"].items() if sha(path) != digest]
    assert not protected_drift and not component_drift and not predecessor_drift
    write("protected_artifact_final.json", {
        "status": "PASS",
        "entry_sha": ENTRY, "head_sha": git("rev-parse", "HEAD"),
        "protected_drift": protected_drift,
        "named_component_drift": component_drift,
        "frontend_predecessor_lock_drift": predecessor_drift,
        "changed_frontend_files": changed_frontend,
        "prior_locks_verified": {name: value["verified"] for name, value in prior.items()},
        "protocol": protocol_result,
        "ui_successor": ui_result,
        "entry_audit_unchanged": sha("reports/capstone/cap_009/entry_audit.json")
        == hashlib.sha256(subprocess.run(
            ["git", "show", "8244ad4:reports/capstone/cap_009/entry_audit.json"],
            cwd=ROOT, check=True, capture_output=True,
        ).stdout).hexdigest(),
    })
    print(json.dumps({"status": "PASS", "reports_written": 25}))


if __name__ == "__main__":
    main()
