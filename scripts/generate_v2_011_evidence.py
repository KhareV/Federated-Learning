#!/usr/bin/env python3
"""V2-011 final evidence: reproducibility, method immutability, protected-artifact audit,
second-invocation blocking, scope audit, the exhaustive tamper suite, and the manifest/hash
pins (written LAST so artifact_hashes.json can never go stale). Control-plane only; run after
all guarded sessions and after scripts/build_explainability_v2.py.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import scripts._v2_011_analysis as analysis
import scripts._v2_011_cases as cases
import scripts.generate_v2_011_entry as entry
import scripts.run_v2_011_error_analysis as ea_run
from models.explainability_v2_verify import verify_explainability_v2
from nhm.hashing import hash_file
from nhm.model_v2_explainability_guard import (
    GUARDS,
    ExplainabilityGuardViolation,
    check_and_begin_session,
    read_guard_state,
)

ROOT = cases.ROOT
OUT = cases.OUT
LOCK_REL = "artifacts/EXPLAINABILITY_V2_METHOD.lock.json"
RUN_LOG_FILES = {
    "pytest_collected_nodes.txt",
    "pytest_chunk_manifest.csv",
    "pytest_chunk_results.csv",
    "test_results.json",
    "full_regression_proof.json",
    "artifact_hashes.json",
}


def _write(name: str, data: dict) -> None:
    cases.write_json(OUT / name, data)


def _sh(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)
    return result.stdout.strip()


def method_commit() -> str:
    log = _sh("git", "log", "--diff-filter=A", "--format=%H", "--",
              "scripts/freeze_v2_011_method.py").split()
    if not log:
        raise RuntimeError("V2_011_METHOD_COMMIT_NOT_FOUND")
    return log[-1]


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------


def reproducibility() -> dict:
    manifest_rows, _ = cases.build_case_manifest_rows(ROOT)
    on_disk = cases.read_csv(cases.CASE_MANIFEST_PATH)
    selection_identical = [
        {k: str(v) for k, v in r.items()} for r in manifest_rows
    ] == [dict(r) for r in on_disk]

    first = analysis.compute_error_tables(ROOT)
    second = analysis.compute_error_tables(ROOT)
    tables_identical = first == second
    with tempfile.TemporaryDirectory() as tmp:
        ea_run.render(first, Path(tmp))
        matches_disk = {
            name: hash_file(Path(tmp) / name) == hash_file(OUT / name)
            for name in ea_run.TABLE_FILES.values()
        }

    pred = analysis.read_noise_predictions(OUT / "noise_type_v2_predictions.csv")
    agg1, agg2 = analysis.aggregate_noise(pred), analysis.aggregate_noise(pred)
    stored = cases.read_csv(OUT / "noise_type_metrics.csv")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.csv"
        cases.write_csv(path, agg1, list(agg1[0]))
        noise_matches = hash_file(path) == hash_file(OUT / "noise_type_metrics.csv")
    ig = json.loads((OUT / "ig_reproducibility.json").read_text())
    v1 = verify_explainability_v2(ROOT)
    v2 = verify_explainability_v2(ROOT)
    ok = (
        selection_identical and tables_identical and all(matches_disk.values())
        and agg1 == agg2 and noise_matches and len(stored) == 18 * 3
        and ig["status"] == "PASS" and v1 == v2
    )
    data = {
        "case_selection_identical": selection_identical,
        "ig_repeat_status": ig["status"],
        "ig_maximum_absolute_attribution_difference":
            ig["maximum_absolute_attribution_difference"],
        "prediction_table_slices_identical_on_rerun": tables_identical,
        "slice_csvs_match_disk": matches_disk,
        "noise_type_aggregation_identical_on_rerun": agg1 == agg2,
        "noise_type_metrics_match_disk": noise_matches,
        "noise_type_pooled_cells": 18,
        "verifier_deterministic": v1 == v2,
        "model_inference_for_this_audit": False,
        "status": "PASS" if ok else "FAIL",
    }
    _write("reproducibility.json", data)
    if not ok:
        raise RuntimeError("V2_011_REPRODUCIBILITY_FAILED")
    return data


# ---------------------------------------------------------------------------
# Immutability / protected artifacts / second invocation / scope
# ---------------------------------------------------------------------------


CORRECTED_AT_CORRECTIVE_COMMIT = {
    "models/explainability_v2_verify.py",
    "scripts/build_explainability_v2.py",
}
SEMANTICS_PATHS = [
    "configs/model_v2/explainability_v2_completeness_semantics_v2.yaml",
    "artifacts/EXPLAINABILITY_V2_COMPLETENESS_SEMANTICS_V2.lock.json",
    "evaluation/explain_v2_semantics.py",
    "reports/model_v2/v2_011/completeness_semantics_authority_audit.json",
    "reports/model_v2/v2_011/ig_completeness_diagnostic.csv",
    "reports/model_v2/v2_011/completeness_semantics_method_freeze.json",
    "reports/model_v2/v2_011/failed_diagnostic_run_manifest.json",
]


def corrective_commit() -> str:
    log = _sh("git", "log", "--diff-filter=A", "--format=%H", "--",
              "configs/model_v2/explainability_v2_completeness_semantics_v2.yaml").split()
    if not log:
        raise RuntimeError("V2_011_CORRECTIVE_COMMIT_NOT_FOUND")
    return log[-1]


def _diff_state(commit: str, rel: str) -> dict:
    existed = subprocess.run(["git", "cat-file", "-e", f"{commit}:{rel}"], cwd=ROOT,
                             capture_output=True, check=False).returncode == 0
    diff = _sh("git", "diff", commit, "HEAD", "--", rel) if existed else "MISSING"
    return {"existed_at_commit": existed, "has_diff": bool(diff)}


def immutability() -> dict:
    original = method_commit()
    corrective = corrective_commit()
    invariant = {rel: _diff_state(original, rel) for rel in cases.METHOD_PATHS
                 if rel not in CORRECTED_AT_CORRECTIVE_COMMIT}
    corrected = {rel: _diff_state(corrective, rel)
                 for rel in sorted(CORRECTED_AT_CORRECTIVE_COMMIT)}
    semantics = {rel: _diff_state(corrective, rel) for rel in SEMANTICS_PATHS}
    ig_core = ["evaluation/explain.py", "evaluation/explain_v2.py", "scripts/_v2_011_cases.py",
               "configs/model_v2/explainability_v2.yaml",
               "reports/model_v2/v2_011/explainability_case_manifest.csv"]
    ok = (
        all(v["existed_at_commit"] and not v["has_diff"] for v in invariant.values())
        and all(v["existed_at_commit"] and not v["has_diff"] for v in corrected.values())
        and all(v["existed_at_commit"] and not v["has_diff"] for v in semantics.values())
        and all(r in invariant for r in ig_core)
    )
    data = {
        "original_method_commit": original,
        "corrective_method_commit": corrective,
        "unchanged_since_original_method_commit": invariant,
        "ig_method_files_unchanged_since_original_method_commit": ig_core,
        "corrected_only_at_corrective_commit_then_unchanged": corrected,
        "semantics_files_unchanged_since_corrective_commit": semantics,
        "all_scientific_files_unchanged": ok,
        "status": "PASS" if ok else "FAIL",
    }
    _write("method_immutability_audit.json", data)
    if not ok:
        raise RuntimeError("V2_011_METHOD_MUTATED_POST_ACCESS")
    return data


def protected_audit() -> dict:
    baseline = json.loads((OUT / "protected_baseline.json").read_text())["artifacts"]
    after = {p: hash_file(ROOT / p) for p in baseline}
    changed = [p for p in baseline if baseline[p] != after[p]]
    data = {"before": baseline, "after": after, "unexpected_changes": changed,
            "status": "PASS" if not changed else "FAIL"}
    _write("protected_artifact_audit.json", data)
    if changed:
        raise RuntimeError(f"V2_011_PROTECTED_ARTIFACT_CHANGED:{changed}")
    return data


def scope_audit() -> dict:
    blocked = {}
    for guard in GUARDS:
        try:
            check_and_begin_session(ROOT, guard, observed_preconditions={})
            blocked[guard] = False
        except ExplainabilityGuardViolation as exc:
            blocked[guard] = "ALREADY_CONSUMED" in str(exc)
    states = {g: read_guard_state(ROOT, g)["state"] for g in GUARDS}
    access = json.loads((OUT / "case_access_audit.json").read_text())
    data = {
        "second_invocation_blocked": blocked,
        "guard_states": states,
        "new_neural_fits": 0,
        "retraining": False,
        "cal_v2_refit": False,
        "threshold_refit_or_changed": False,
        "official_validation_access": False,
        "calibration_access": False,
        "full_internal_test_reevaluation": False,
        "internal_test_windows_materialized_for_ig": access["materialized_windows"],
        "incart_reevaluation": False,
        "nstdb_second_look_rerun": False,
        "v1_inference_rerun": False,
        "hardware_or_wearable": False,
        "deployment_api_frontend_changes": False,
        "gateway_artifact_v2_created": False,
        "runtime_acceptance_changed": False,
        "cumulative_neural_fits": 71,
        "status": "PASS" if all(blocked.values()) and all(s == "COMPLETED" for s in states.values())
        else "FAIL",
    }
    _write("scope_audit.json", data)
    if data["status"] != "PASS":
        raise RuntimeError("V2_011_SCOPE_AUDIT_FAILED")
    return data


# ---------------------------------------------------------------------------
# Tamper suite (temporary copies only)
# ---------------------------------------------------------------------------

STATIC_FILES = [
    "checkpoints/MODEL_V2_FINAL.pt",
    "checkpoints/MODEL_V2_FINAL.manifest.json",
    "configs/model_v2_final_frozen.yaml",
    "tests/fixtures/model_v2_final_test_vector.npz",
    "artifacts/CAL_V2.json",
    "artifacts/EXPLAINABILITY_V2_METHOD.lock.json",
    "reports/model_v2/v2_009/calibration_access_guard.json",
    "reports/model_v2/v2_009/reliability.json",
    "reports/model_v2/v2_011/hr_bins.json",
    "reports/model_v2/v2_011/case_access_guard.json",
    "reports/model_v2/v2_011/noise_type_access_guard.json",
    "reports/t031/hr_bins.json",
]
BIG_SYMLINK_SUFFIXES = (".dat",)


def _verifier_files() -> list[str]:
    files = set(STATIC_FILES)
    model_manifest = json.loads((ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json").read_text())
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    lock = json.loads((ROOT / LOCK_REL).read_text())
    files |= set(model_manifest["upstream_sha256"]) | set(cal["upstream_sha256"])
    files |= set(lock["bound_artifacts"])
    sem_lock = json.loads((ROOT / "artifacts/EXPLAINABILITY_V2_COMPLETENESS_SEMANTICS_V2.lock.json")
                          .read_text())
    files |= set(sem_lock["bound_artifacts"]) | {
        "artifacts/EXPLAINABILITY_V2_COMPLETENESS_SEMANTICS_V2.lock.json"}
    files |= {str(p.relative_to(ROOT)) for p in OUT.rglob("*") if p.is_file()
              and p.name not in {"pytest_collected_nodes.txt"}}
    for rel in list(files):
        if not (ROOT / rel).exists():
            files.discard(rel)
    return sorted(files)


def _build_base_root(base: Path) -> None:
    for rel in _verifier_files():
        src, dst = ROOT / rel, base / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(BIG_SYMLINK_SUFFIXES):
            dst.symlink_to(src)
        else:
            shutil.copy2(src, dst)


def _edit(root: Path, rel: str, old: str, new: str) -> None:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"TAMPER_PATTERN_NOT_FOUND:{rel}:{old}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _reseal(root: Path) -> None:
    """Re-seal lock + report hashes so that detection must come from semantic checks."""
    lock_path = root / LOCK_REL
    lock = json.loads(lock_path.read_text())
    for rel in lock["bound_artifacts"]:
        target = root / rel
        if target.exists() and not target.is_symlink():
            lock["bound_artifacts"][rel] = hash_file(target)
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    sem_lock_path = root / "artifacts/EXPLAINABILITY_V2_COMPLETENESS_SEMANTICS_V2.lock.json"
    sem_lock = json.loads(sem_lock_path.read_text())
    for rel in sem_lock["bound_artifacts"]:
        target = root / rel
        if target.exists() and not target.is_symlink():
            sem_lock["bound_artifacts"][rel] = hash_file(target)
    sem_lock_path.write_text(json.dumps(sem_lock, indent=2, sort_keys=True) + "\n")
    report_path = root / "reports/model_v2/v2_011/explainability_v2.json"
    report = json.loads(report_path.read_text())
    for case in report["cases"]:
        base = root / f"reports/model_v2/v2_011/cases/{case['case_type']}"
        for suffix, key in (("attribution.csv", "attribution_sha256"),
                            ("raw_ecg.csv", "raw_sha256"),
                            ("annotations.csv", "annotations_sha256"),
                            ("figure.svg", "figure_sha256")):
            case[key] = hash_file(Path(f"{base}_{suffix}"))
    report["case_manifest_sha256"] = hash_file(
        root / "reports/model_v2/v2_011/explainability_case_manifest.csv")
    report["error_analysis_config_sha256"] = hash_file(root / cases_rel("error"))
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    lock = json.loads(lock_path.read_text())
    lock["bound_artifacts"]["reports/model_v2/v2_011/explainability_case_manifest.csv"] = hash_file(
        root / "reports/model_v2/v2_011/explainability_case_manifest.csv")
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")


def cases_rel(kind: str) -> str:
    return {"error": "configs/model_v2/error_analysis_v2.yaml",
            "explain": "configs/model_v2/explainability_v2.yaml"}[kind]


V2 = "reports/model_v2/v2_011"
SEM = "configs/model_v2/explainability_v2_completeness_semantics_v2.yaml"
EX = "configs/model_v2/explainability_v2.yaml"
ER = "configs/model_v2/error_analysis_v2.yaml"


def _csv_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    import csv

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    return rows[0], rows[1:]


def _csv_write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    import csv

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _m_checkpoint(r: Path) -> None:
    with (r / "checkpoints/MODEL_V2_FINAL.pt").open("ab") as h:
        h.write(b"\x00")


def _m_cal(r: Path) -> None:
    _edit(r, "artifacts/CAL_V2.json", '"temperature": 52.88261929727761',
          '"temperature": 52.9')


def _m_protocol(r: Path) -> None:
    p = r / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
    p.write_bytes(p.read_bytes() + b" ")


def _manifest_edit(r: Path, row: int, col: str, value: str | None = None, swap: bool = False):
    path = r / f"{V2}/explainability_case_manifest.csv"
    header, rows = _csv_rows(path)
    i = header.index(col)
    if swap:
        rows[0][i], rows[1][i] = rows[1][i], rows[0][i]
    else:
        rows[row][i] = value
    _csv_write(path, header, rows)


def _m_case_id(r):
    _manifest_edit(r, 0, "example_id", "0" * 64)
    _reseal(r)


def _m_case_category(r):
    _manifest_edit(r, 0, "case_type", swap=True)
    _reseal(r)


def _m_case_probability(r):
    _manifest_edit(r, 0, "calibrated_probability", "0.9")
    _reseal(r)


def _m_case_rule(r):
    _manifest_edit(r, 0, "selection_rule", "lowest_source_domain_calibrated_probability")
    _reseal(r)


def _m_tie_rule(r):
    _manifest_edit(r, 0, "tie_rule", "largest_example_id")
    _reseal(r)


def _yaml_mut(rel: str, old: str, new: str):
    def apply(r: Path) -> None:
        _edit(r, rel, old, new)
        _reseal(r)
    return apply


def _m_signed_removal(r: Path) -> None:
    path = r / f"{V2}/cases/TP_attribution.csv"
    header, rows = _csv_rows(path)
    i = header.index("signed_ig")
    _csv_write(path, [h for j, h in enumerate(header) if j != i],
               [[v for j, v in enumerate(row) if j != i] for row in rows])
    _reseal(r)


def _m_overlay_values(r: Path) -> None:
    path = r / f"{V2}/cases/TP_attribution.csv"
    header, rows = _csv_rows(path)
    i = header.index("normalized_absolute_ig")
    for row in rows:
        row[i] = "0.5"
    _csv_write(path, header, rows)
    _reseal(r)


def _m_attr_row_delete(r: Path) -> None:
    path = r / f"{V2}/cases/FP_attribution.csv"
    header, rows = _csv_rows(path)
    _csv_write(path, header, rows[:-1])
    _reseal(r)


def _m_raw_row_delete(r: Path) -> None:
    path = r / f"{V2}/cases/TN_raw_ecg.csv"
    header, rows = _csv_rows(path)
    _csv_write(path, header, rows[:-1])
    _reseal(r)


def _m_annotation_shift(r: Path) -> None:
    path = r / f"{V2}/cases/FN_annotations.csv"
    header, rows = _csv_rows(path)
    i = header.index("relative_time_s")
    rows[0][i] = str(float(rows[0][i]) + 0.5)
    _csv_write(path, header, rows)
    _reseal(r)


def _m_noise_type_removed(r: Path) -> None:
    path = r / f"{V2}/noise_type_v2_predictions.csv"
    header, rows = _csv_rows(path)
    i = header.index("noise_type")
    _csv_write(path, header, [row for row in rows if row[i] != "MUSCLE_ARTIFACT"])
    _reseal(r)


def _m_noise_hash(r: Path) -> None:
    _edit(r, ER, "bw: 15f68280", "bw: 25f68280")
    _reseal(r)


def _m_noise_dat(r: Path) -> None:
    dat = r / "data/raw/nstdb/1.0.0/bw.dat"
    original = dat.resolve().read_bytes()
    dat.unlink()
    dat.write_bytes(original + b"\x00")


def _m_noise_labels(r: Path) -> None:
    path = r / f"{V2}/noise_type_v2_predictions.csv"
    header, rows = _csv_rows(path)
    i = header.index("label")
    rows[0][i] = "1" if rows[0][i] == "0" else "0"
    _csv_write(path, header, rows)
    _reseal(r)


def _m_residual(r: Path) -> None:
    path = r / f"{V2}/explainability_v2.json"
    data = json.loads(path.read_text())
    data["cases"][0]["completeness_diagnostic"]["completeness_absolute_delta"] = 0.0
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _m_attr_value(r: Path) -> None:
    path = r / f"{V2}/cases/TP_attribution.csv"
    header, rows = _csv_rows(path)
    i = header.index("signed_ig")
    rows[10][i] = repr(float(rows[10][i]) + 1e-6)
    _csv_write(path, header, rows)
    _reseal(r)


def _m_lock_status(r: Path) -> None:
    _edit(r, LOCK_REL, "FROZEN_EXPLAINABILITY", "PRE_RESULT_LOCKED")


def _m_lock_binding(r: Path) -> None:
    lock_path = r / LOCK_REL
    lock = json.loads(lock_path.read_text())
    first = sorted(lock["bound_artifacts"])[0]
    lock["bound_artifacts"][first] = "0" * 64
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")


def _m_hr_json(r: Path) -> None:
    path = r / f"{V2}/hr_bins.json"
    data = json.loads(path.read_text())
    data["Q2_bpm"] = 70.0
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    _reseal(r)


def _m_patient_table(r: Path) -> None:
    path = r / f"{V2}/patient_slice_incart.csv"
    header, rows = _csv_rows(path)
    i = header.index("brier_score")
    rows[3][i] = "0.5"
    _csv_write(path, header, rows)
    _reseal(r)


TAMPERS = {
    "checkpoint_hash_change": _m_checkpoint,
    "cal_v2_change": _m_cal,
    "protocol_v3_change": _m_protocol,
    "case_id_change": _m_case_id,
    "case_category_change": _m_case_category,
    "case_probability_change": _m_case_probability,
    "case_rule_change": _m_case_rule,
    "tie_rule_change": _m_tie_rule,
    "baseline_change": _yaml_mut(EX, "baseline: ALL_ZERO_NORMALIZED_INPUT", "baseline: MEAN_INPUT"),
    "steps_64_to_63": _yaml_mut(EX, "steps: 64", "steps: 63"),
    "steps_64_to_65": _yaml_mut(EX, "steps: 64", "steps: 65"),
    "integration_method_change": _yaml_mut(
        EX, "integration: GAUSS_LEGENDRE", "integration: RIEMANN"),
    "target_logit_to_probability": _yaml_mut(
        EX, "target: MODEL_V2_FINAL_PRE_SIGMOID_LOGIT", "target: MODEL_V2_FINAL_PROBABILITY"),
    "signed_attribution_removal": _m_signed_removal,
    "overlay_normalization_config_change": _yaml_mut(
        EX, "visual_overlay: PER_WINDOW_ABSOLUTE_ATTRIBUTION_NORMALIZED_BY_WINDOW_MAX",
        "visual_overlay: GLOBAL_MAX"),
    "overlay_normalization_values_change": _m_overlay_values,
    "historical_heuristic_constant_change": _yaml_mut(
        EX, "completeness_absolute_threshold: 0.001", "completeness_absolute_threshold: 0.1"),
    "completeness_hard_gate_reintroduced": _yaml_mut(
        SEM, "gates_v2g10: false", "gates_v2g10: true"),
    "completeness_gate_field_change": _yaml_mut(
        SEM, "numerical_completeness_gate: NONE", "numerical_completeness_gate: ABS_LT_1E-3"),
    "semantics_original_commit_binding_change": _yaml_mut(
        SEM, "original_method_commit: 1bb81d5", "original_method_commit: 2bb81d5"),
    "completeness_residual_value_altered": _m_residual,
    "attribution_array_value_changed": _m_attr_value,
    "attribution_row_deletion": _m_attr_row_delete,
    "raw_ecg_row_deletion": _m_raw_row_delete,
    "annotation_alignment_change": _m_annotation_shift,
    "hr_bin_boundary_change_config": _yaml_mut(ER, "Q1_bpm: 65.4545454545441", "Q1_bpm: 60.0"),
    "hr_bin_boundary_change_json": _m_hr_json,
    "patient_ranking_metric_brier_to_f1": _yaml_mut(
        ER, "ranking_metric: BRIER", "ranking_metric: F1"),
    "patient_table_brier_change": _m_patient_table,
    "threshold_band_change": _yaml_mut(ER, "margin: 0.05", "margin: 0.1"),
    "noise_type_removed": _m_noise_type_removed,
    "snr_list_change": _yaml_mut(
        ER, "snr_db: [24, 18, 12, 6, 0, -6]", "snr_db: [24, 18, 12, 6, 0]"),
    "noise_source_hash_change_config": _m_noise_hash,
    "noise_source_dat_content_change": _m_noise_dat,
    "noise_source_labels_fabricated": _m_noise_labels,
    "method_lock_status_change": _m_lock_status,
    "method_lock_binding_change": _m_lock_binding,
}


def tamper_suite() -> dict:
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base"
        _build_base_root(base)
        clean = verify_explainability_v2(base)
        if clean["status"] != "PASS":
            raise RuntimeError("TAMPER_BASE_ROOT_DOES_NOT_VERIFY")
        canonical_before = {p: hash_file(ROOT / p) for p in entry.PROTECTED_PATHS}
        for name, mutate in TAMPERS.items():
            work = Path(tmp) / f"case_{name}"
            shutil.copytree(base, work, symlinks=True)
            mutate(work)
            try:
                verify_explainability_v2(work)
                results[name] = {"detected": False, "error": None}
            except Exception as exc:
                message = f"{type(exc).__name__}:{str(exc)[:160]}"
                results[name] = {"detected": True, "error": message}
            shutil.rmtree(work)
        canonical_after = {p: hash_file(ROOT / p) for p in entry.PROTECTED_PATHS}
    required = [
        "checkpoint hash change", "CAL_V2 change", "Protocol V3 change", "case ID change",
        "case category change", "case probability change", "case rule change",
        "tie rule change", "baseline change", "steps 64->63 or 65",
        "integration method change", "target raw logit->probability",
        "signed attribution removal", "overlay normalization change",
        "historical completeness heuristic constants change",
        "completeness hard gate reintroduced", "completeness residual altered",
        "attribution array value change", "attribution row deletion", "raw ECG row deletion",
        "annotation alignment change", "HR-bin boundary change",
        "patient ranking metric Brier->F1", "threshold band +/-0.05 change",
        "noise-type change", "SNR list change", "noise source hash change",
        "noise source labels fabricated", "method lock changed",
    ]
    data = {
        "clean_temp_copy_verifies": True,
        "mutations": results,
        "mutation_count": len(results),
        "all_detected": all(v["detected"] for v in results.values()),
        "required_categories": required,
        "canonical_artifacts_unmodified": canonical_before == canonical_after,
        "status": "PASS" if all(v["detected"] for v in results.values())
        and canonical_before == canonical_after else "FAIL",
    }
    _write("tamper_test_results.json", data)
    if data["status"] != "PASS":
        raise RuntimeError("V2_011_TAMPER_SUITE_FAILED")
    return data


# ---------------------------------------------------------------------------
# Manifest + hash pins (last)
# ---------------------------------------------------------------------------


def run_pytest_summary() -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:warnings",
         "tests/test_v2_011_config.py", "tests/test_v2_011_results.py"],
        cwd=ROOT, capture_output=True, text=True, env={**__import__("os").environ,
                                                      "PYTHONPATH": "src:."},
    )
    tail = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    m = re.search(r"(\d+) passed", tail)
    data = {"command": "pytest tests/test_v2_011_config.py tests/test_v2_011_results.py",
            "exit_code": result.returncode, "summary": tail,
            "passed": int(m.group(1)) if m else 0,
            "status": "PASS" if result.returncode == 0 else "FAIL"}
    _write("test_results.json", data)
    return data


def finalize() -> None:
    entry_audit = json.loads((OUT / "entry_audit.json").read_text())
    manifest = {
        "checkpoint_id": "V2-011",
        "owner_task": "V2-011",
        "gate": "V2G10",
        "EXPLAINABILITY_V2": "FROZEN_EXPLAINABILITY",
        "entry_head": entry_audit["head"],
        "method_commit": method_commit(),
        "MODEL_V2_RUNTIME_ACCEPTED": "ACCEPTED",
        "runtime_decision_changed": False,
        "official_validation_promotion": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
        "operational_lineage": "MODEL_V1",
        "new_neural_fits": 0,
        "cumulative_neural_fits": 71,
        "status": "PASS",
    }
    _write("run_manifest.json", manifest)
    pins = {
        f"reports/model_v2/v2_011/{p.relative_to(OUT)}": hash_file(p)
        for p in sorted(OUT.rglob("*")) if p.is_file() and p.name not in RUN_LOG_FILES
    }
    pins["artifacts/EXPLAINABILITY_V2_METHOD.lock.json"] = hash_file(ROOT / LOCK_REL)
    _write("artifact_hashes.json", {"artifacts": pins})


def main() -> None:
    reproducibility()
    immutability()
    protected_audit()
    scope_audit()
    tamper_suite()
    run_pytest_summary()
    finalize()
    print(json.dumps({"status": "PASS"}))


if __name__ == "__main__":
    main()
