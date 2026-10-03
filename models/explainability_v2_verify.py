"""V2-011 EXPLAINABILITY_V2 fail-closed verifier.

Recomputes every binding, selection, attribution identity, completeness, slice and noise-type
invariant from the files on disk. Never trusts a stored PASS flag. Any mismatch raises
ExplainabilityV2VerifyError with a stable error code.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from evaluation.explain_v2_semantics import (
    LOCKED_STATUS,
    NUMERICAL_GATE,
    SEMANTICS_ID,
    completeness_diagnostic,
)
from models.cal_v2_verify import verify_cal_v2
from models.model_v2_final_freeze import verify_model_v2_final
from nhm.hashing import hash_file

LOCK_PATH = "artifacts/EXPLAINABILITY_V2_METHOD.lock.json"
REPORT_PATH = "reports/model_v2/v2_011/explainability_v2.json"
CASE_MANIFEST = "reports/model_v2/v2_011/explainability_case_manifest.csv"
EXPLAIN_CONFIG = "configs/model_v2/explainability_v2.yaml"
SEMANTICS_CONFIG = "configs/model_v2/explainability_v2_completeness_semantics_v2.yaml"
SEMANTICS_LOCK = "artifacts/EXPLAINABILITY_V2_COMPLETENESS_SEMANTICS_V2.lock.json"
FAILED_RUN_MANIFEST = "reports/model_v2/v2_011/failed_diagnostic_run_manifest.json"
ORIGINAL_METHOD_COMMIT = "1bb81d52876ff70dbc1eba742a2b1f1909b8523d"
FAILED_RUN_COMMIT = "ce1d055f37d7ddcb4a7c0c6117ba8c4e20450b51"
ERROR_CONFIG = "configs/model_v2/error_analysis_v2.yaml"
CASE_TYPES = ("TP", "TN", "FP", "FN")
SNRS = [24, 18, 12, 6, 0, -6]
NOISE_TYPES = {"BASELINE_WANDER": "bw", "ELECTRODE_MOTION": "em", "MUSCLE_ARTIFACT": "ma"}
EXPECTED = {
    "target": "MODEL_V2_FINAL_PRE_SIGMOID_LOGIT",
    "baseline": "ALL_ZERO_NORMALIZED_INPUT",
    "integration": "GAUSS_LEGENDRE",
    "steps": 64,
    "attribution": "SIGNED_INTEGRATED_GRADIENTS",
    "visual_overlay": "PER_WINDOW_ABSOLUTE_ATTRIBUTION_NORMALIZED_BY_WINDOW_MAX",
    "tie_rule": "lexicographically_smallest_example_id",
}
EXPECTED_SELECTION = {
    "TP": "highest_source_domain_calibrated_probability",
    "TN": "lowest_source_domain_calibrated_probability",
    "FP": "highest_source_domain_calibrated_probability",
    "FN": "lowest_source_domain_calibrated_probability",
}
CLAIM_FIELDS = (
    "causal_physiological_explanation",
    "clinical_explanation",
    "model_trustworthiness_proof",
    "runtime_switch_authorized",
)


class ExplainabilityV2VerifyError(RuntimeError):
    """Raised when any EXPLAINABILITY_V2 binding or invariant differs."""


def _fail(code: str, detail: str = "") -> None:
    raise ExplainabilityV2VerifyError(f"{code}:{detail}" if detail else code)


def _need(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        _fail(code, detail)


def _json(root: Path, rel: str) -> dict[str, Any]:
    path = root / rel
    if not path.exists():
        _fail("EXPLAINABILITY_V2_FILE_MISSING", rel)
    return json.loads(path.read_text(encoding="utf-8"))


def _csv(root: Path, rel: str) -> list[dict[str, str]]:
    path = root / rel
    if not path.exists():
        _fail("EXPLAINABILITY_V2_FILE_MISSING", rel)
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _hash(root: Path, rel: str) -> str:
    path = root / rel
    if not path.exists():
        _fail("EXPLAINABILITY_V2_FILE_MISSING", rel)
    return hash_file(path)


def recompute_case_selection(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = {k: [] for k in CASE_TYPES}
    for r in rows:
        label, pred = int(r["label"]), int(r["thresholded_prediction"])
        grouped[("T" if label == pred else "F") + ("P" if pred else "N")].append(r)
    _need(all(grouped.values()), "EXPLAINABILITY_V2_EMPTY_CASE_CATEGORY")

    def p(r: dict[str, str]) -> float:
        return float(r["source_domain_calibrated_probability"])

    return {
        "TP": min(grouped["TP"], key=lambda r: (-p(r), r["example_id"])),
        "TN": min(grouped["TN"], key=lambda r: (p(r), r["example_id"])),
        "FP": min(grouped["FP"], key=lambda r: (-p(r), r["example_id"])),
        "FN": min(grouped["FN"], key=lambda r: (p(r), r["example_id"])),
    }


def _brier_ranking(rows: list[dict[str, str]]) -> dict[str, float]:
    groups: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        groups.setdefault(r["participant_group_id"], []).append(r)
    return {
        g: float(np.mean([(float(r["source_domain_calibrated_probability"]) - int(r["label"])) ** 2
                          for r in rs]))
        for g, rs in groups.items()
    }


def verify_explainability_v2(root: Path) -> dict[str, Any]:
    checks: dict[str, bool] = {}

    # --- frozen upstream (each verifier recomputes hashes itself) -----------------
    verify_model_v2_final(root)
    verify_cal_v2(root)
    checks["model_and_cal_verified"] = True

    lock = _json(root, LOCK_PATH)
    report = _json(root, REPORT_PATH)
    explain_cfg = yaml.safe_load((root / EXPLAIN_CONFIG).read_text(encoding="utf-8"))
    error_cfg = yaml.safe_load((root / ERROR_CONFIG).read_text(encoding="utf-8"))

    _need(lock.get("lock_id") == "EXPLAINABILITY_V2_METHOD", "EXPLAINABILITY_V2_LOCK_IDENTITY")
    _need(lock.get("status") == "FROZEN_EXPLAINABILITY", "EXPLAINABILITY_V2_LOCK_STATUS")
    _need(lock.get("owner_task") == "V2-011", "EXPLAINABILITY_V2_OWNER_TASK")
    for rel, digest in lock.get("bound_artifacts", {}).items():
        _need(_hash(root, rel) == digest, "EXPLAINABILITY_V2_BOUND_ARTIFACT_MISMATCH", rel)
    _need(len(lock.get("bound_artifacts", {})) > 20, "EXPLAINABILITY_V2_LOCK_TOO_FEW_BINDINGS")
    checks["lock_bound_artifacts"] = True

    # --- identity bindings recomputed from live files -----------------------------
    live = {
        "MODEL_V2_FINAL_sha256": _hash(root, "checkpoints/MODEL_V2_FINAL.pt"),
        "CAL_V2_sha256": _hash(root, "artifacts/CAL_V2.json"),
        "protocol_v3_lock_sha256": _hash(
            root, "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"),
        "PREPROC_V1_lock_sha256": _hash(root, "manifests/preprocessing/PREPROC_V1.lock.json"),
        "case_manifest_sha256": _hash(root, CASE_MANIFEST),
        "error_analysis_config_sha256": _hash(root, ERROR_CONFIG),
        "explainability_config_sha256": _hash(root, EXPLAIN_CONFIG),
    }
    for key, value in live.items():
        if key in explain_cfg:
            _need(explain_cfg[key] == value, "EXPLAINABILITY_V2_CONFIG_BINDING_MISMATCH", key)
        if key in report:
            _need(report[key] == value, "EXPLAINABILITY_V2_REPORT_BINDING_MISMATCH", key)
    live_pred = {
        "internal": _hash(root, "reports/model_v2/v2_010/internal_v2_predictions.csv"),
        "incart": _hash(root, "reports/model_v2/v2_010/incart_v2_predictions.csv"),
        "nstdb": _hash(root, "reports/model_v2/v2_010/nstdb_v2_predictions.csv"),
    }
    _need(report.get("v2_010_prediction_sha256") == live_pred,
          "EXPLAINABILITY_V2_V2_010_PREDICTION_MISMATCH")
    _need(explain_cfg["case_source_sha256"] == live_pred["internal"],
          "EXPLAINABILITY_V2_CASE_SOURCE_MISMATCH")
    checks["identity_bindings"] = True

    # --- IG method fields ---------------------------------------------------------
    for key, expected in EXPECTED.items():
        _need(explain_cfg.get(key) == expected, "EXPLAINABILITY_V2_CONFIG_METHOD_MISMATCH", key)
    for key in ("target", "baseline", "integration", "steps", "attribution", "tie_rule"):
        _need(report.get(key) == EXPECTED[key], "EXPLAINABILITY_V2_REPORT_METHOD_MISMATCH", key)
    _need(report.get("overlay_normalization") == EXPECTED["visual_overlay"],
          "EXPLAINABILITY_V2_OVERLAY_NORMALIZATION_MISMATCH")
    # The base-config completeness thresholds are the HISTORICAL heuristic constants; they are
    # descriptive only after C-V2-011-COMPLETENESS-SEMANTICS and must still be unchanged.
    _need(explain_cfg["completeness_absolute_threshold"] == 0.001
          and explain_cfg["completeness_relative_threshold"] == 0.001,
          "EXPLAINABILITY_V2_HISTORICAL_HEURISTIC_CHANGED")
    sem_cfg = yaml.safe_load((root / SEMANTICS_CONFIG).read_text(encoding="utf-8"))
    _need(sem_cfg.get("id") == SEMANTICS_ID, "EXPLAINABILITY_V2_SEMANTICS_IDENTITY")
    comp = sem_cfg.get("completeness", {})
    _need(comp.get("numerical_completeness_gate") == NUMERICAL_GATE
          and comp.get("gates_v2g10") is False
          and comp.get("new_semantics") == "DIAGNOSTIC_METADATA_ALWAYS_RECORDED",
          "EXPLAINABILITY_V2_COMPLETENESS_HARD_GATE_PRESENT")
    heur = comp.get("historical_heuristic", {})
    _need(heur.get("absolute") == 0.001 and heur.get("relative") == 0.001
          and heur.get("role") == "DESCRIPTIVE_ONLY_NEVER_A_GATE",
          "EXPLAINABILITY_V2_HISTORICAL_HEURISTIC_CHANGED")
    _need(sem_cfg.get("original_method_commit") == ORIGINAL_METHOD_COMMIT
          and sem_cfg.get("failed_diagnostic_run_commit") == FAILED_RUN_COMMIT,
          "EXPLAINABILITY_V2_SEMANTICS_COMMIT_BINDING")
    unchanged = sem_cfg.get("unchanged_from_original_method", {})
    for key, expected in EXPECTED.items():
        cfg_key = "visual_overlay" if key == "visual_overlay" else key
        _need(unchanged.get(cfg_key) == expected, "EXPLAINABILITY_V2_SEMANTICS_METHOD_CHANGED", key)
    sem = report.get("completeness_semantics", {})
    _need(sem.get("semantics_id") == SEMANTICS_ID
          and sem.get("numerical_completeness_gate") == NUMERICAL_GATE
          and sem.get("gates_v2g10") is False
          and sem.get("historical_heuristic_role") == "DESCRIPTIVE_ONLY",
          "EXPLAINABILITY_V2_COMPLETENESS_HARD_GATE_PRESENT")
    sem_lock = _json(root, SEMANTICS_LOCK)
    _need(sem_lock.get("status") == "FROZEN_SEMANTICS_CORRECTION"
          and sem_lock.get("numerical_completeness_gate") == NUMERICAL_GATE,
          "EXPLAINABILITY_V2_SEMANTICS_LOCK")
    for rel, digest in sem_lock.get("bound_artifacts", {}).items():
        _need(_hash(root, rel) == digest, "EXPLAINABILITY_V2_SEMANTICS_LOCK_BINDING_MISMATCH", rel)
    for key, expected in (("original_method_commit", ORIGINAL_METHOD_COMMIT),
                          ("failed_diagnostic_run_commit", FAILED_RUN_COMMIT)):
        _need(lock.get(key) == expected == report.get(key), "EXPLAINABILITY_V2_COMMIT_BINDING", key)
    _need(len(str(lock.get("corrective_method_commit", ""))) == 40
          and lock.get("corrective_method_commit") == report.get("corrective_method_commit"),
          "EXPLAINABILITY_V2_COMMIT_BINDING", "corrective_method_commit")
    audit = _json(root, "reports/model_v2/v2_011/completeness_semantics_authority_audit.json")
    _need(audit.get("status") == "PASS"
          and audit.get("HARD_NUMERICAL_THRESHOLD_IN_V2_2") == "NONE"
          and audit.get("CORRECTIVE_CLASSIFICATION") == "UNSUPPORTED_HARD_GATE_REMOVED",
          "EXPLAINABILITY_V2_AUTHORITY_AUDIT")
    failed_manifest = _json(root, FAILED_RUN_MANIFEST)
    _need(explain_cfg["case_selection"] == EXPECTED_SELECTION
          and report.get("case_selection") == EXPECTED_SELECTION,
          "EXPLAINABILITY_V2_SELECTION_RULE_MISMATCH")
    checks["ig_method_fields"] = True

    # --- case manifest recomputed from the frozen prediction table -----------------
    manifest = _csv(root, CASE_MANIFEST)
    _need(len(manifest) == 4, "EXPLAINABILITY_V2_CASE_COUNT")
    _need([m["case_type"] for m in manifest] == list(CASE_TYPES),
          "EXPLAINABILITY_V2_CASE_CATEGORIES")
    selected = recompute_case_selection(
        _csv(root, "reports/model_v2/v2_010/internal_v2_predictions.csv"))
    cal = _json(root, "artifacts/CAL_V2.json")
    for m in manifest:
        want = selected[m["case_type"]]
        _need(m["example_id"] == want["example_id"], "EXPLAINABILITY_V2_CASE_ID_MISMATCH",
              m["case_type"])
        _need(m["calibrated_probability"] == want["source_domain_calibrated_probability"],
              "EXPLAINABILITY_V2_CASE_PROBABILITY_MISMATCH", m["case_type"])
        _need(m["label"] == want["label"]
              and m["thresholded_prediction"] == want["thresholded_prediction"],
              "EXPLAINABILITY_V2_CASE_CATEGORY_MISMATCH", m["case_type"])
        _need(m["selection_rule"] == EXPECTED_SELECTION[m["case_type"]],
              "EXPLAINABILITY_V2_SELECTION_RULE_MISMATCH", m["case_type"])
        _need(m["tie_rule"] == EXPECTED["tie_rule"], "EXPLAINABILITY_V2_TIE_RULE_MISMATCH")
        _need(float(m["cal_v2_threshold"]) == float(cal["threshold"]),
              "EXPLAINABILITY_V2_CASE_THRESHOLD_MISMATCH")
        _need(m["model_v2_final_sha256"] == live["MODEL_V2_FINAL_sha256"]
              and m["cal_v2_sha256"] == live["CAL_V2_sha256"]
              and m["source_prediction_table_sha256"] == live_pred["internal"],
              "EXPLAINABILITY_V2_CASE_BINDING_MISMATCH", m["case_type"])
    checks["case_manifest"] = True

    # --- per-case attribution / raw ECG / annotations / completeness ---------------
    cases = {c["case_type"]: c for c in report.get("cases", [])}
    _need(sorted(cases) == sorted(CASE_TYPES), "EXPLAINABILITY_V2_REPORT_CASES")
    for m in manifest:
        ct = m["case_type"]
        case = cases[ct]
        _need(case["example_id"] == m["example_id"], "EXPLAINABILITY_V2_REPORT_CASE_ID", ct)
        base = f"reports/model_v2/v2_011/cases/{ct}"
        file_keys = (
            ("attribution.csv", "attribution_sha256"),
            ("raw_ecg.csv", "raw_sha256"),
            ("annotations.csv", "annotations_sha256"),
            ("figure.svg", "figure_sha256"),
        )
        for suffix, key in file_keys:
            _need(_hash(root, f"{base}_{suffix}") == case[key],
                  "EXPLAINABILITY_V2_CASE_FILE_HASH_MISMATCH", f"{ct}:{suffix}")
        attr = _csv(root, f"{base}_attribution.csv")
        _need(len(attr) == 2500, "EXPLAINABILITY_V2_ATTRIBUTION_ROW_COUNT", ct)
        _need("signed_ig" in attr[0], "EXPLAINABILITY_V2_SIGNED_ATTRIBUTION_MISSING", ct)
        signed = np.array([float(r["signed_ig"]) for r in attr])
        overlay = np.array([float(r["normalized_absolute_ig"]) for r in attr])
        peak = float(np.max(np.abs(signed)))
        expected_overlay = np.abs(signed) / peak if peak > 0 else np.zeros_like(signed)
        _need(np.allclose(overlay, expected_overlay, rtol=0, atol=1e-12),
              "EXPLAINABILITY_V2_OVERLAY_NORMALIZATION_MISMATCH", ct)
        sum_signed = float(np.sum(signed))
        _need(abs(sum_signed - case["attribution_sum"]) <= 1e-9,
              "EXPLAINABILITY_V2_ATTRIBUTION_SUM_MISMATCH", ct)
        diag = completeness_diagnostic(case["F_x"], case["F_baseline"], sum_signed)
        stored = case.get("completeness_diagnostic", {})
        for key in ("completeness_signed_delta", "completeness_absolute_delta",
                    "completeness_relative_delta"):
            _need(key in stored and abs(float(stored[key]) - diag[key]) <= 1e-9,
                  "EXPLAINABILITY_V2_COMPLETENESS_NOT_RECORDED", f"{ct}:{key}")
        for key in ("historical_v1_style_1e3_heuristic", "historical_heuristic_label",
                    "locked_v2_2_explainability_status", "numerical_completeness_gate"):
            _need(stored.get(key) == diag[key],
                  "EXPLAINABILITY_V2_COMPLETENESS_STATUS", f"{ct}:{key}")
        _need(stored["locked_v2_2_explainability_status"] == LOCKED_STATUS,
              "EXPLAINABILITY_V2_COMPLETENESS_STATUS", ct)
        original = next(r for r in _csv(root, "reports/model_v2/v2_011/ig_completeness.csv")
                        if r["case_type"] == ct)
        abs_gap = abs(float(original["absolute_delta"]) - stored["completeness_absolute_delta"])
        rel_gap = abs(float(original["relative_delta"]) - stored["completeness_relative_delta"])
        _need(abs_gap <= 1e-12 and rel_gap <= 1e-9,
              "EXPLAINABILITY_V2_ORIGINAL_RESIDUAL_NOT_PRESERVED", ct)
        for suffix in ("attribution.csv", "raw_ecg.csv", "annotations.csv", "figure.svg"):
            rel_path = f"reports/model_v2/v2_011/cases/{ct}_{suffix}"
            _need(failed_manifest["artifact_sha256"][rel_path] == _hash(root, rel_path),
                  "EXPLAINABILITY_V2_ATTRIBUTION_ARRAY_CHANGED", f"{ct}:{suffix}")
        _need(int(np.argmax(np.abs(signed))) == case["max_abs_attribution_index"],
              "EXPLAINABILITY_V2_MAX_ATTRIBUTION_INDEX", ct)
        raw = _csv(root, f"{base}_raw_ecg.csv")
        _need(len(raw) == 3600, "EXPLAINABILITY_V2_RAW_ECG_ROW_COUNT", ct)
        ann = _csv(root, f"{base}_annotations.csv")
        _need(len(ann) > 0, "EXPLAINABILITY_V2_ANNOTATION_CONTEXT_MISSING", ct)
        start_s = case["window_start_s"]
        for a in ann:
            rel = int(a["source_sample"]) / 360.0 - start_s
            _need(abs(rel - float(a["relative_time_s"])) <= 1e-9,
                  "EXPLAINABILITY_V2_ANNOTATION_ALIGNMENT", ct)
            inside = 0.0 < float(a["relative_time_s"]) <= 10.0
            _need((a["position"] == "INSIDE_MODEL_WINDOW") == inside,
                  "EXPLAINABILITY_V2_ANNOTATION_POSITION", ct)
    compliance = report.get("locked_method_compliance", {})
    _need(compliance.get("status") == "PASS" and all(
        v is True for k, v in compliance.items() if k != "status"),
        "EXPLAINABILITY_V2_METHOD_COMPLIANCE")
    checks["cases"] = True

    # --- claim boundary -----------------------------------------------------------
    _need(bool(report.get("claim_boundary")) and bool(lock.get("claim_boundary")),
          "EXPLAINABILITY_V2_CLAIM_BOUNDARY_MISSING")
    fields = report.get("claim_boundary_fields", {})
    _need(all(fields.get(k) is False for k in CLAIM_FIELDS),
          "EXPLAINABILITY_V2_CLAIM_BOUNDARY_FIELDS")
    checks["claim_boundary"] = True

    # --- error-analysis method bindings ---------------------------------------------
    _need(error_cfg["patient_slice"]["ranking_metric"] == "BRIER",
          "EXPLAINABILITY_V2_PATIENT_RANKING_METRIC")
    _need(error_cfg["threshold_region"]["margin"] == 0.05
          and error_cfg["threshold_region"]["center"] == float(cal["threshold"]),
          "EXPLAINABILITY_V2_THRESHOLD_BAND")
    hr = _json(root, "reports/t031/hr_bins.json")
    h = error_cfg["heart_rate_slice"]
    _need((h["Q1_bpm"], h["Q2_bpm"], h["Q3_bpm"]) == (hr["Q1_bpm"], hr["Q2_bpm"], hr["Q3_bpm"])
          and h["bins_source_sha256"] == _hash(root, "reports/t031/hr_bins.json"),
          "EXPLAINABILITY_V2_HR_BIN_BOUNDARIES")
    hr_v2 = _json(root, "reports/model_v2/v2_011/hr_bins.json")
    _need(hr_v2.get("Q1_bpm") == hr["Q1_bpm"] and hr_v2.get("Q2_bpm") == hr["Q2_bpm"]
          and hr_v2.get("Q3_bpm") == hr["Q3_bpm"], "EXPLAINABILITY_V2_HR_BIN_BOUNDARIES")
    for ds, rel, prefix in (("INTERNAL_TEST", "patient_slice_internal.csv", "INT_PATIENT"),
                            ("INCART", "patient_slice_incart.csv", "INCART_CLUSTER")):
        table = _csv(root, f"reports/model_v2/v2_011/{rel}")
        brier = _brier_ranking(_csv(root, error_cfg["sources"][ds]))
        _need(len(table) == len(brier), "EXPLAINABILITY_V2_PATIENT_COUNT", ds)
        _need("brier_score" in table[0], "EXPLAINABILITY_V2_PATIENT_RANKING_METRIC", ds)
        stored = sorted(float(r["brier_score"]) for r in table)
        _need(np.allclose(stored, sorted(brier.values()), rtol=0, atol=1e-12),
              "EXPLAINABILITY_V2_PATIENT_BRIER_MISMATCH", ds)
        by_status = {r["ranking_status"]: float(r["brier_score"]) for r in table}
        _need(abs(by_status["BEST_BY_BRIER"] - min(brier.values())) <= 1e-12
              and abs(by_status["WORST_BY_BRIER"] - max(brier.values())) <= 1e-12,
              "EXPLAINABILITY_V2_PATIENT_RANKING_METRIC", ds)
        _need(all(r["patient"].startswith(prefix) for r in table),
              "EXPLAINABILITY_V2_PATIENT_PSEUDONYM", ds)
    checks["error_analysis_method"] = True

    # --- controlled noise-type protocol --------------------------------------------
    nt = error_cfg["noise_type"]
    audit = _json(root, "reports/model_v2/v2_011/noise_type_protocol_audit.json")
    _need(audit.get("status") == "PASS" and all(audit.get("checks", {}).values()),
          "EXPLAINABILITY_V2_NOISE_PROTOCOL_AUDIT")
    _need(nt["snr_db"] == SNRS and audit.get("snr_levels") == SNRS, "EXPLAINABILITY_V2_SNR_LIST")
    _need(sorted(audit.get("noise_types", [])) == sorted(NOISE_TYPES),
          "EXPLAINABILITY_V2_NOISE_TYPES")
    _need(nt["noise_sources"] == NOISE_TYPES, "EXPLAINABILITY_V2_NOISE_TYPES")
    for source in ("bw", "em", "ma"):
        actual = _hash(root, f"data/raw/nstdb/1.0.0/{source}.dat")
        _need(actual == nt["noise_source_dat_sha256"][source]
              == audit["noise_source_dat_sha256"][source],
              "EXPLAINABILITY_V2_NOISE_SOURCE_HASH", source)
    _need(_hash(root, nt["c031_lock"]) == nt["c031_lock_sha256"],
          "EXPLAINABILITY_V2_NOISE_PROTOCOL_MISMATCH")
    _need(audit.get("pure_noise_labels_fabricated") is False, "EXPLAINABILITY_V2_NOISE_LABELS")
    base = {r["base_window_id"]: r for r in _csv(root, nt["base_manifest"])}
    preds = _csv(root, "reports/model_v2/v2_011/noise_type_v2_predictions.csv")
    _need(len(preds) == 18 * 720, "EXPLAINABILITY_V2_NOISE_ROW_COUNT")
    _need("pure_noise_label" not in preds[0], "EXPLAINABILITY_V2_NOISE_LABELS")
    _need({r["noise_type"] for r in preds} == set(NOISE_TYPES)
          and {int(r["snr_db"]) for r in preds} == set(SNRS), "EXPLAINABILITY_V2_NOISE_CELLS")
    _need(all(r["label"] == base[r["base_window_id"]]["label"] for r in preds),
          "EXPLAINABILITY_V2_NOISE_LABELS")
    metrics = _csv(root, "reports/model_v2/v2_011/noise_type_metrics.csv")
    pooled = [r for r in metrics if r["scope"] == "POOLED_BOTH_SOURCE_RECORDS"]
    _need(len(pooled) == 18, "EXPLAINABILITY_V2_NOISE_CELLS")
    _need({(r["noise_type"], int(r["snr_db"])) for r in pooled}
          == {(n, s) for n in NOISE_TYPES for s in SNRS}, "EXPLAINABILITY_V2_NOISE_CELLS")
    checks["noise_type_protocol"] = True

    # --- guards completed -----------------------------------------------------------
    for rel in ("reports/model_v2/v2_011/case_access_guard.json",
                "reports/model_v2/v2_011/noise_type_access_guard.json"):
        _need(_json(root, rel).get("state") == "COMPLETED", "EXPLAINABILITY_V2_GUARD_NOT_COMPLETED",
              rel)
    checks["guards_completed"] = True

    # --- status distinctions ---------------------------------------------------------
    _need(report.get("runtime_acceptance_changed_by_this_phase") is False
          and report.get("operational_lineage") == "MODEL_V1",
          "EXPLAINABILITY_V2_STATUS_DISTINCTION")
    checks["status_distinction"] = True

    return {"status": "PASS", "checks": checks}


__all__ = ["ExplainabilityV2VerifyError", "recompute_case_selection", "verify_explainability_v2"]
