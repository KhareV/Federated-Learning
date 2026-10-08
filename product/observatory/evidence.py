# ruff: noqa: E501
"""Read-only presentation of FROZEN scientific evidence (no inference, training, tuning or new statistics).

Everything returned here is read from committed artifacts after a SHA-256 check against the frozen
artifact-hash manifest. Curves are a descriptive recomputation from the frozen prediction tables
(allowed existing evidence) and are cross-checked against the frozen point metrics.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = "reports/model_v2/v2_fl_eval_001"
DATASETS = {"INTERNAL_TEST": "internal_test_statistics.json", "INCART": "incart_statistics.json"}
METRICS = ("AUPRC", "AUROC", "pooled_F1", "precision", "sensitivity", "specificity", "patient_macro_F1")
CURVE_POINT_LIMIT = 240
SCHEMA = "NHM_OBSERVATORY_EVIDENCE_V1"


class EvidenceError(ValueError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=1)
def _hash_manifest() -> dict[str, str]:
    raw = (ROOT / EVAL_DIR / "artifact_hashes.json").read_bytes()
    return dict(json.loads(raw)["artifacts"])


def _verified_bytes(relative: str) -> bytes:
    expected = _hash_manifest().get(relative)
    if expected is None:
        raise EvidenceError(f"EVIDENCE_NOT_IN_FROZEN_HASH_MANIFEST:{relative}")
    data = (ROOT / relative).read_bytes()
    if _sha(data) != expected:
        raise EvidenceError(f"EVIDENCE_HASH_MISMATCH:{relative}")
    return data


def _ci(entry: dict[str, Any]) -> dict[str, float | int]:
    return {"lower": entry["ci_lower_95"], "upper": entry["ci_upper_95"],
            "valid_replicates": entry["valid_replicates"], "invalid_replicates": entry["invalid_replicates"]}


@lru_cache(maxsize=2)
def _statistics(dataset: str) -> dict[str, Any]:
    if dataset not in DATASETS:
        raise EvidenceError("UNKNOWN_EVIDENCE_DATASET")
    relative = f"{EVAL_DIR}/{DATASETS[dataset]}"
    return json.loads(_verified_bytes(relative))


def fl_eval_index() -> dict[str, Any]:
    datasets: dict[str, Any] = {}
    for name in DATASETS:
        stats = _statistics(name)
        models = []
        for model_id, model in sorted(stats["models"].items()):
            point = model["point"]
            models.append({
                "model_id": model_id, "generation": model["generation"], "algorithm": model["algorithm"],
                "condition": model["condition"], "mu": model["mu"], "checkpoint_sha256": model["checkpoint_sha256"],
                "development_round": model["development_round"],
                "point": {key: point[key] for key in (*METRICS, "BCE", "accuracy", "TP", "FP", "TN", "FN",
                                                      "positives", "negatives", "contributing_patients")},
                "ci_95": {metric: _ci(model["bootstrap_95"][metric]) for metric in METRICS
                          if metric in model["bootstrap_95"]},
                "patients": [{"participant_group_id": p["participant_group_id"], "windows": p["windows"],
                              "positives": p["positives"], "negatives": p["negatives"],
                              "AUPRC": p.get("AUPRC"), "AUROC": p.get("AUROC"), "F1_at_0_5": p.get("F1_at_0_5")}
                             for p in model["patients"]],
            })
        comparisons = []
        for comparison_id, item in sorted(stats["comparisons"].items()):
            comparisons.append({
                "comparison_id": comparison_id, "family": item["family"], "a": item["A"], "b": item["B"],
                "delta": {metric: {"point": value["point_delta"], "lower": value["ci_lower_95"],
                                   "upper": value["ci_upper_95"]}
                          for metric, value in item["delta"].items() if "point_delta" in value},
            })
        bootstrap = stats["bootstrap"]
        datasets[name] = {
            "claim_label": stats["claim_label"], "clusters": stats["clusters"], "windows": stats["windows"],
            "models": models, "comparisons": comparisons,
            "bootstrap": {"replicates": bootstrap["B"], "seed": bootstrap["seed"], "rng": bootstrap["rng"],
                          "draws_sha256": bootstrap["draws_sha256"],
                          "multiplicity_adjustment": bootstrap["multiplicity_adjustment"],
                          "p_values": bootstrap["p_values"]},
            "source": {"path": f"{EVAL_DIR}/{DATASETS[name]}",
                       "sha256": _hash_manifest()[f"{EVAL_DIR}/{DATASETS[name]}"]},
        }
    return {"schema_version": SCHEMA, "classification": "FROZEN_RESEARCH_EVIDENCE", "datasets": datasets,
            "limitations": [
                "INTERNAL_TEST is held out from the V2 federated development lineage but is not project-globally unseen.",
                "INTERNAL_TEST has 6 contributing patient clusters; intervals are wide and unstable.",
                "INCART is a post-freeze external second look on a project-exposed dataset, not untouched validation.",
                "Confidence intervals are nominal 95% patient-cluster percentile intervals; no p-values or significance tests were computed.",
                "These results belong to the scientific FL experiments (AAMI_SVF_WINDOW_V1), not to the product engineering candidate."]}


def fl_eval_curves(dataset: str, model_id: str) -> dict[str, Any]:
    stats = _statistics(dataset)
    if model_id not in stats["models"]:
        raise EvidenceError("UNKNOWN_EVIDENCE_MODEL")
    relative = f"{EVAL_DIR}/predictions/{dataset}/{model_id}.csv.gz"
    text = gzip.decompress(_verified_bytes(relative)).decode()
    header, *rows = text.strip().splitlines()
    columns = header.split(",")
    label_i, prob_i = columns.index("label"), columns.index("raw_sigmoid_probability")
    labels = np.array([int(r.split(",")[label_i]) for r in rows])
    scores = np.array([float(r.split(",")[prob_i]) for r in rows])
    frozen = stats["models"][model_id]["point"]
    ap = float(average_precision_score(labels, scores))
    auc = float(roc_auc_score(labels, scores))
    matches = abs(ap - frozen["AUPRC"]) < 1e-9 and abs(auc - frozen["AUROC"]) < 1e-9
    precision, recall, _ = precision_recall_curve(labels, scores)
    fpr, tpr, _ = roc_curve(labels, scores)

    def thin(x: np.ndarray, y: np.ndarray) -> list[list[float]]:
        step = max(1, int(np.ceil(len(x) / CURVE_POINT_LIMIT)))
        keep = sorted(set(range(0, len(x), step)) | {len(x) - 1})
        return [[float(x[i]), float(y[i])] for i in keep]

    predicted = scores >= 0.5
    counts = {"TP": int(np.sum(predicted & (labels == 1))), "FP": int(np.sum(predicted & (labels == 0))),
              "TN": int(np.sum(~predicted & (labels == 0))), "FN": int(np.sum(~predicted & (labels == 1)))}
    return {
        "schema_version": SCHEMA, "classification": "DESCRIPTIVE_RECOMPUTATION_FROM_FROZEN_PREDICTIONS",
        "dataset": dataset, "model_id": model_id, "windows": len(labels),
        "recomputed_matches_frozen_point_metrics": bool(matches),
        "recomputed": {"AUPRC": ap, "AUROC": auc}, "frozen": {"AUPRC": frozen["AUPRC"], "AUROC": frozen["AUROC"]},
        "pr_curve": thin(recall, precision), "roc_curve": thin(fpr, tpr),
        "confusion_at_0_5": counts, "threshold_rule": "FL_EVAL_RAW_THRESHOLD_0P5_V1 (raw sigmoid >= 0.5, no calibration)",
        "displayed_points": {"pr": len(thin(recall, precision)), "roc": len(thin(fpr, tpr))},
        "method": "sklearn precision_recall_curve/roc_curve on the frozen prediction table; display points are thinned, metrics use all windows",
        "source": {"path": relative, "sha256": _hash_manifest()[relative]},
    }


def architecture() -> dict[str, Any]:
    import torch

    from models.model_v2_architectures import (
        TCN_CHANNELS,
        TCN_DILATIONS,
        TCN_KERNEL_SIZE,
        ModelV2TcnMean,
        analytic_tcn_receptive_field_samples,
        count_trainable_parameters,
    )

    model = ModelV2TcnMean().eval()
    shapes: dict[str, list[int]] = {}
    handles = []
    for name, module in model.named_modules():
        if name and name.count(".") <= 3 and not list(module.children()):
            handles.append(module.register_forward_hook(
                lambda _m, _i, out, key=name: shapes.__setitem__(key, list(out.shape))))
    with torch.no_grad():
        output = model(torch.zeros(1, 1, 2500))
    for handle in handles:
        handle.remove()
    layers = []
    for name, module in model.named_modules():
        if name in shapes:
            params = sum(p.numel() for p in module.parameters(recurse=False))
            layers.append({"name": name, "type": type(module).__name__, "parameters": params,
                           "output_shape": shapes[name]})
    return {
        "schema_version": SCHEMA, "classification": "DERIVED_FROM_ACTUAL_IMPLEMENTATION_ZERO_INPUT_SHAPE_TRACE",
        "architecture_id": "MODEL_V2_TCN_MEAN", "parameter_count": count_trainable_parameters(model),
        "input_shape": [1, 1, 2500], "output_shape": list(output.shape), "channels": TCN_CHANNELS,
        "kernel_size": TCN_KERNEL_SIZE, "dilations": list(TCN_DILATIONS), "pooling": "global temporal mean",
        "receptive_field_samples": analytic_tcn_receptive_field_samples(), "layers": layers,
        "notes": ["Shapes come from running an all-zero tensor through the real module; no weights are loaded and no inference is performed on data.",
                  "Layer outputs are not clinical explanations."],
        "source": {"path": "models/model_v2_architectures.py"},
    }


def calibration() -> dict[str, Any]:
    cal_raw = (ROOT / "artifacts/CAL_V2.json").read_bytes()
    cal = json.loads(cal_raw)
    rel_raw = (ROOT / "reports/model_v2/v2_009/reliability.json").read_bytes()
    rel = json.loads(rel_raw)
    keep = ("calibration_id", "calibration_domain", "temperature", "threshold", "threshold_comparator",
            "threshold_metric", "calibration_window_count", "calibration_patient_count", "positive_window_count",
            "negative_window_count", "raw_ece", "calibrated_ece", "raw_brier", "calibrated_brier", "raw_nll",
            "calibrated_nll", "threshold_calibration_f1", "threshold_confusion_counts", "reliability_method",
            "small_patient_sample_uncertainty", "model_id", "model_checkpoint_sha256", "target_id")
    return {
        "schema_version": SCHEMA, "classification": "FROZEN_RESEARCH_EVIDENCE",
        "label": "MIT-BIH SOURCE-DOMAIN CALIBRATION ONLY", "constants": {k: cal[k] for k in keep},
        "probability_semantics": cal["probability_semantics"],
        "reliability": {"method": rel["method"],
                        "raw": [{k: b[k] for k in ("lower", "upper", "count", "mean_probability",
                                                    "observed_positive_fraction")} for b in rel["raw"]],
                        "temperature_scaled": [{k: b[k] for k in ("lower", "upper", "count", "mean_probability",
                                                                   "observed_positive_fraction")}
                                               for b in rel["temperature_scaled"]]},
        "not_applicable_to": "The product federated engineering candidate: CAL_V2 is never applied to it.",
        "source": {"calibration_path": "artifacts/CAL_V2.json", "calibration_sha256": _sha(cal_raw),
                   "reliability_path": "reports/model_v2/v2_009/reliability.json", "reliability_sha256": _sha(rel_raw)},
    }


BOUNDARIES: tuple[dict[str, str], ...] = (
    {"id": "internal-test-six-groups", "title": "Six contributing INTERNAL_TEST patient groups",
     "statement": "The held-out INTERNAL_TEST evaluation has 6 contributing patient clusters; intervals are wide and patient-level metrics are not population estimates.",
     "path": f"{EVAL_DIR}/final_handoff.md"},
    {"id": "incart-exposed", "title": "INCART is a project-exposed second look",
     "statement": "INCART was evaluated after freeze on a dataset the project had already seen; it is not untouched external validation.",
     "path": f"{EVAL_DIR}/final_handoff.md"},
    {"id": "source-domain-calibration", "title": "Calibration is MIT-BIH source-domain only",
     "statement": "CAL_V2 was fitted on MIT-BIH calibration records; no cross-domain, wearable, personal or clinical calibration is established.",
     "path": "artifacts/CAL_V2.json"},
    {"id": "quality-flatline", "title": "Known quality-gate limitation",
     "statement": "QUALITY_V1 retains a known stuck-nonzero signal limitation; a clean quality state does not mean a healthy patient.",
     "path": "reports/model_v2/v2_013/final_handoff.md"},
    {"id": "synthetic-wearable", "title": "Virtual wearable only",
     "statement": "The product monitoring source is a simulated virtual wearable; no physical wearable validation exists.",
     "path": "reports/model_v2/v2_fl_005/claim_audit.json"},
    {"id": "synthetic-federation", "title": "Synthetic logical federation",
     "statement": "The eight product FL clients are synthetic logical clients on one demonstration machine, not hospitals, patients or physical devices.",
     "path": "reports/model_v2/v2_fl_005/cohort_manifest_run.json"},
    {"id": "no-personal-training", "title": "No personal physiology is trained on",
     "statement": "An authenticated user owns runs and sessions, but their physiology never feeds federation and no personal model exists.",
     "path": "reports/model_v2/v2_fl_005/claim_audit.json"},
    {"id": "candidate-efficacy", "title": "Candidate efficacy is not established",
     "statement": "The sandbox candidate is trained on synthetic event-window labels (WEARABLE_SIM_EVENT_WINDOW_V1), not AAMI_SVF_WINDOW_V1; V2-FL-005 prohibited efficacy metrics.",
     "path": "reports/model_v2/v2_fl_005/efficacy_metric_audit.json"},
    {"id": "no-deployment", "title": "No candidate deployment or promotion",
     "statement": "The candidate stays in the engineering sandbox; MODEL_V2_FINAL is never replaced automatically.",
     "path": "reports/model_v2/v2_fl_005/claim_audit.json"},
    {"id": "secagg-narrow", "title": "SecAgg is a narrow shadow claim",
     "statement": "The accepted claim is PROTECTED_AGGREGATION_INTERFACE_ONLY; authoritative product aggregation is plain. No differential privacy, anonymity or production security is claimed.",
     "path": "artifacts/SECAGG_METHOD_V2.lock.json"},
)
CHRONOLOGY: tuple[dict[str, str], ...] = (
    {"id": "v2-007", "title": "V2-007 model promotion gate",
     "decision": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
     "why": "The predeclared paired release-seed confidence interval crossed zero; this negative finding stays true.",
     "path": "reports/model_v2/v2_007/finalist_selection.json"},
    {"id": "v2-008", "title": "V2-008 final model freeze",
     "decision": "MODEL_V2_FINAL frozen (centrally trained)", "why": "Freeze identity, checkpoint byte-identity and configuration were verified before calibration.",
     "path": "reports/model_v2/v2_008/promotion_disposition.json"},
    {"id": "v2-009", "title": "V2-009 calibration",
     "decision": "CAL_V2 fitted (MIT-BIH source-domain)", "why": "Temperature scaling and threshold selection on the calibration partition only.",
     "path": "reports/model_v2/v2_009/temperature_fit.json"},
    {"id": "v2-010", "title": "V2-010 second look",
     "decision": "Post-freeze INTERNAL_TEST and INCART evidence", "why": "Descriptive, not used for selection; limitations remain visible.",
     "path": "reports/model_v2/v2_010/internal_comparison.json"},
    {"id": "system-release", "title": "Later software-system release",
     "decision": "SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED", "why": "A different question than model promotion: the software system, not the original promotion criterion.",
     "path": "artifacts/SYSTEM_V2_RELEASE_DECISION_V1.lock.json"},
    {"id": "fl-eval", "title": "V2-FL-EVAL-001 federated family evaluation",
     "decision": "Observational evidence; no promotion", "why": "Frozen 20-checkpoint family evaluated once; FedProx transfer was mixed, not generally superior.",
     "path": f"{EVAL_DIR}/final_handoff.md"},
    {"id": "fl-005", "title": "V2-FL-005 engineering simulation",
     "decision": "Engineering-only wearable simulation", "why": "Synthetic cohort and labels; efficacy metrics explicitly prohibited.",
     "path": "reports/model_v2/v2_fl_005/final_handoff.md"},
)


def _entries(items: tuple[dict[str, str], ...]) -> list[dict[str, Any]]:
    out = []
    for item in items:
        path = ROOT / item["path"]
        out.append({**item, "exists": path.is_file(), "sha256": _sha(path.read_bytes()) if path.is_file() else None})
    return out


def boundaries() -> dict[str, Any]:
    return {"schema_version": SCHEMA, "boundaries": _entries(BOUNDARIES), "chronology": _entries(CHRONOLOGY)}


def reproducibility() -> dict[str, Any]:
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_bytes())
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                                check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    import sys

    import torch
    return {
        "schema_version": SCHEMA, "git_commit": commit, "observatory": "NHM_RESEARCH_OBSERVATORY_V1_CANDIDATE",
        "predecessor_ui": "CAPSTONE_UI_V1_9", "released_model": cal["model_id"],
        "released_checkpoint_sha256": cal["model_checkpoint_sha256"], "calibration_id": cal["calibration_id"],
        "calibration_sha256": _sha((ROOT / "artifacts/CAL_V2.json").read_bytes()),
        "preprocessing_lock_sha256": cal["preproc_sha256"], "split_manifest_sha256": cal["split_sha256"],
        "window_manifest_sha256": cal["window_manifest_sha256"], "protocol_lock_sha256": cal["protocol_v3_lock_sha256"],
        "fl_eval_hash_manifest_sha256": _sha((ROOT / EVAL_DIR / "artifact_hashes.json").read_bytes()),
        "fl_eval_artifact_count": len(_hash_manifest()),
        "runtime": {"python": sys.version.split()[0], "torch": torch.__version__},
        "reference_runtime_recorded_by_calibration": cal["reference_runtime"],
        "evidence_paths": [item["path"] for item in (*BOUNDARIES, *CHRONOLOGY)],
        "note": "A listed report is evidence of a result, not proof that the result has been independently reproduced here.",
    }


XAI_DIR = "reports/model_v2/v2_011"
XAI_CASES = ("TP", "TN", "FP", "FN")


@lru_cache(maxsize=1)
def _xai_manifest() -> dict[str, Any]:
    hashes = json.loads((ROOT / XAI_DIR / "artifact_hashes.json").read_bytes())["artifacts"]
    relative = f"{XAI_DIR}/explainability_v2.json"
    data = (ROOT / relative).read_bytes()
    if hashes.get(relative) != _sha(data):
        raise EvidenceError(f"EVIDENCE_HASH_MISMATCH:{relative}")
    return json.loads(data)


def explainability_index() -> dict[str, Any]:
    manifest = _xai_manifest()
    keep = ("method_id", "attribution", "baseline", "integration", "steps", "target", "overlay_normalization",
            "claim_boundary", "model_id", "status", "case_selection", "completeness_rule")
    cases = [{k: case[k] for k in ("case_type", "record_id", "window_start_s", "window_end_s", "F_x", "F_baseline",
                                   "attribution_sum", "output_difference", "max_abs_attribution_index")}
             | {"completeness": case["completeness_diagnostic"]} for case in manifest["cases"]]
    return {"schema_version": SCHEMA, "classification": "FROZEN_RESEARCH_EVIDENCE",
            "method": {k: manifest[k] for k in keep}, "cases": cases,
            "limitations": ["Integrated Gradients highlights normalized input regions that contribute to the pre-sigmoid logit under a zero baseline.",
                            "It is an engineering model-contribution diagnostic, not a causal, physiological or clinical explanation.",
                            "Four cases were selected by a frozen rule (highest or lowest calibrated probability per outcome type); they are not representative samples."],
            "source": {"path": f"{XAI_DIR}/explainability_v2.json", "sha256": _hash_of(f"{XAI_DIR}/explainability_v2.json")}}


def _hash_of(relative: str) -> str:
    return _sha((ROOT / relative).read_bytes())


def _rows(path: Path, expected: str) -> list[list[str]]:
    raw = path.read_bytes()
    if _sha(raw) != expected:
        raise EvidenceError(f"EVIDENCE_HASH_MISMATCH:{path.name}")
    return [line.split(",") for line in raw.decode().strip().splitlines()[1:]]


def explainability_case(case_type: str) -> dict[str, Any]:
    if case_type not in XAI_CASES:
        raise EvidenceError("UNKNOWN_EVIDENCE_CASE")
    case = next(c for c in _xai_manifest()["cases"] if c["case_type"] == case_type)
    base = ROOT / XAI_DIR / "cases"
    attribution = _rows(base / f"{case_type}_attribution.csv", case["attribution_sha256"])
    raw = _rows(base / f"{case_type}_raw_ecg.csv", case["raw_sha256"])
    annotations = _rows(base / f"{case_type}_annotations.csv", case["annotations_sha256"])
    return {
        "schema_version": SCHEMA, "classification": "FROZEN_RESEARCH_EVIDENCE", "case_type": case_type,
        "record_id": case["record_id"], "window_start_s": case["window_start_s"], "window_end_s": case["window_end_s"],
        "model_input": [[float(r[1]), float(r[2]), float(r[3]), float(r[5])] for r in attribution],
        "raw_ecg": [[float(r[1]), float(r[2])] for r in raw],
        "annotations": [{"time_s": float(r[1]), "symbol": r[2], "aami_class": r[3], "position": r[4]} for r in annotations],
        "columns": ["model_time_s", "normalized_model_input", "signed_ig", "normalized_absolute_ig"],
        "overlay_normalization": "PER_WINDOW_ABSOLUTE_ATTRIBUTION_NORMALIZED_BY_WINDOW_MAX",
        "source": {"attribution_sha256": case["attribution_sha256"], "raw_sha256": case["raw_sha256"],
                   "annotations_sha256": case["annotations_sha256"]},
    }


def _yaml_scalars(relative: str, keys: tuple[str, ...]) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in (ROOT / relative).read_text().splitlines():
        stripped = line.strip()
        for key in keys:
            if stripped.startswith(f"{key}:") and key not in found:
                found[key] = stripped.split(":", 1)[1].strip()
    return found


def _role_blocks() -> dict[str, dict[str, str]]:
    blocks: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in (ROOT / "manifests/datasets/dataset_roles_v1.yaml").read_text().splitlines():
        if line and not line.startswith((" ", "#")) and line.endswith(":"):
            current = blocks.setdefault(line[:-1], {})
        elif current is not None and ":" in line and line.startswith("  ") and not line.startswith("   "):
            key, _, value = line.strip().partition(":")
            if value.strip() and value.strip() != ">":
                current[key] = value.strip()
    return blocks


def causality_demonstration(resampler_id: str) -> dict[str, Any]:
    """Deterministic demonstration on the REAL causal resampler with a synthetic test signal (not ECG data)."""
    from preprocessing.resample import StatefulRationalResampler, load_resampler_spec

    spec = load_resampler_spec(resampler_id)
    n = spec.input_rate_hz * 4
    t = np.arange(n) / spec.input_rate_hz
    base = np.sin(2 * np.pi * 3.0 * t)
    changed = base.copy()
    cut = n // 2
    changed[cut:] += 5.0        # alter only samples that arrive AFTER the cut
    first = StatefulRationalResampler(spec).process(base, 0).values
    second = StatefulRationalResampler(spec).process(changed, 0).values
    differ = np.flatnonzero(first != second)
    first_diff = int(differ[0]) if differ.size else None
    return {"synthetic_test_signal": "3 Hz sine, 4 s (not research data)", "altered_from_source_sample": cut,
            "output_samples": int(first.size), "first_output_index_that_changed": first_diff,
            "outputs_before_alteration_identical": bool(first_diff is None or np.array_equal(first[:first_diff], second[:first_diff])),
            "meaning": "Altering later input samples never changes earlier causal outputs."}


def dataset_preprocessing() -> dict[str, Any]:
    from preprocessing.resample import load_resampler_spec

    lock_raw = (ROOT / "manifests/preprocessing/PREPROC_V1.lock.json").read_bytes()
    lock = json.loads(lock_raw)
    roles = _role_blocks()
    entries = []
    for dataset, resampler_id, manifest in (("MITDB", "MITDB_360_TO_250_V1", "manifests/datasets/mitdb_v1.yaml"),
                                            ("INCART", "INCART_257_TO_250_V1", "manifests/datasets/incart_v1.yaml")):
        spec = load_resampler_spec(resampler_id)
        facts = _yaml_scalars(manifest, ("sampling_rate_hz", "lead_policy_id", "eligible_record_count", "provider"))
        role = roles.get(dataset, {})
        entries.append({
            "dataset": dataset, "native_rate_hz": spec.input_rate_hz, "target_rate_hz": spec.output_rate_hz,
            "resampler_id": resampler_id, "up": spec.up, "down": spec.down, "taps": spec.num_taps,
            "group_delay_seconds": spec.group_delay_seconds, "startup_transient_output_samples": spec.startup_transient_output_span,
            "coefficient_sha256": spec.coefficient_sha256, "lead_policy": facts.get("lead_policy_id"),
            "role": role.get("role"), "allowed_for_training": role.get("allowed_for_training"),
            "external_evaluation_only": role.get("external_evaluation_only"),
            "access_rule": "Availability never implies permission outside the locked role; INCART is evaluation-only and was already used for the post-freeze second look.",
            "causality": causality_demonstration(resampler_id)})
    contract = lock["semantic_contract"]
    return {"schema_version": SCHEMA, "classification": "FROZEN_METHOD_PLUS_DETERMINISTIC_DEMONSTRATION",
            "datasets": entries,
            "contract": {k: contract[k] for k in ("signal_interval", "annotation_interval", "ecg_rate_hz", "window_samples", "stride_samples", "normalization_id", "normalization_epsilon", "gap_policy_id", "quality_id", "windowing_id", "resampler_delay_us", "timestamp_backdating")},
            "annotation_time_mapping": lock["annotation_time_mapping"], "causal_iir_phase": lock["causal_iir_phase"],
            "label_contracts": [
                {"id": "AAMI_SVF_WINDOW_V1", "kind": "SCIENTIFIC_ECG_CLASSIFICATION", "rule": "At least five mapped eligible beats; positive = any mapped S/V/F beat; negative = only mapped N beats; Q or unmappable beats exclude the window."},
                {"id": "WEARABLE_SIM_EVENT_WINDOW_V1", "kind": "SYNTHETIC_ENGINEERING_EVENT", "rule": "Deterministic scheduled synthetic events; not the AAMI-SVF target and not a medical annotation."}],
            "raw_recordings": "NOT_PRESENT_IN_THIS_CHECKOUT: beat positions on the waveform are unavailable; no synthetic signal is ever shown as a MIT-BIH or INCART record.",
            "source": {"lock_path": "manifests/preprocessing/PREPROC_V1.lock.json", "lock_sha256": _sha(lock_raw)}}
