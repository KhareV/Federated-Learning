# ruff: noqa: E501
"""Read-only integrity checks used by the pre-push audit (evaluation reconciliation, lane separation). Nothing here trains, tunes or re-evaluates a model:
metrics are recomputed from the committed prediction table purely to reconcile them with the committed results."""

from __future__ import annotations

import csv
import json
import re
import subprocess
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from final_showcase import LANE_LABEL, evaluate, research

ROOT = research.ROOT
METHOD_COMMIT = "6d79274c0ca4f159d210c69411a68238be3d2112"
RESULT_COMMIT = "1c09b65"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def evaluation_integrity() -> dict[str, Any]:
    results = json.loads((ROOT / research.SYNTH).read_text())
    proto = json.loads((ROOT / evaluate.PROTOCOL).read_text())
    # method frozen before prediction: protocol bytes at the method commit == now; the prediction table first appears in a LATER commit
    first_pred = git("log", "--diff-filter=A", "--format=%H", "--", "reports/final_showcase/synth_fl_eval/holdout_predictions.csv").splitlines()[-1]
    ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", METHOD_COMMIT, first_pred], cwd=ROOT).returncode == 0
    at_method = subprocess.run(["git", "cat-file", "-e", f"{METHOD_COMMIT}:reports/final_showcase/synth_fl_eval/holdout_predictions.csv"], cwd=ROOT, capture_output=True).returncode != 0
    evaluate.verify_method_freeze(METHOD_COMMIT)
    frozen = json.loads((ROOT / "reports/model_v2/v2_fl_005/federation_run.json").read_text())["state_progression"]
    rows = list(csv.DictReader((ROOT / "reports/final_showcase/synth_fl_eval/holdout_predictions.csv").open()))
    labels = np.array([int(r["label"]) for r in rows])
    out: dict[str, Any] = {"method_commit_is_ancestor_of_first_prediction_commit": ancestry, "predictions_absent_at_method_commit": at_method, "first_prediction_commit": first_pred,
                           "protocol_sha256": evaluate.sha256_file(ROOT / evaluate.PROTOCOL), "manifest_sha256_matches_protocol": proto["holdout"]["manifest_sha256"] == evaluate.sha256_file(ROOT / evaluate.MANIFEST),
                           "state_digests_equal_frozen_progression": [results["state_digests"][k] for k in evaluate.STATE_KEYS] == [frozen[str(i)]["sha256"] for i in range(4)],
                           "separation": results["separation"], "holdout_windows": len(rows), "states": {}}
    for key in evaluate.STATE_KEYS:
        z = np.array([float(r[f"logit_{key}"]) for r in rows])
        p = 1 / (1 + np.exp(-z))
        pred = (p >= 0.5).astype(int)
        tp, fp = int(((labels == 1) & (pred == 1)).sum()), int(((labels == 0) & (pred == 1)).sum())
        tn, fn = int(((labels == 0) & (pred == 0)).sum()), int(((labels == 1) & (pred == 0)).sum())
        stored = results["results"][key]["pooled"]
        per = results["results"][key]["per_participant"]
        out["states"][key] = {
            "confusion_recomputed_equals_stored": [tp, fp, tn, fn] == [stored["TP"], stored["FP"], stored["TN"], stored["FN"]],
            "row_sums_reconcile": tp + fn == stored["positives"] and tn + fp == stored["negatives"] and tp + fp + tn + fn == stored["windows"] == len(rows),
            "per_participant_confusion_sums_to_pooled": [sum(v[m] for v in per.values()) for m in ("TP", "FP", "TN", "FN")] == [tp, fp, tn, fn],
            "auprc_auroc_recomputed_equal_stored": abs(average_precision_score(labels, p) - stored["AUPRC"]) < 1e-9 and abs(roc_auc_score(labels, p) - stored["AUROC"]) < 1e-9,
            "accuracy_recomputed_equals_stored": abs((tp + tn) / len(rows) - stored["accuracy"]) < 1e-12,
            "predicted_positive_fraction": float(pred.mean()), "precision_is_null_when_no_predicted_positive": (stored["precision"] is None) == (tp + fp == 0),
        }
    r3 = out["states"]["round_3_candidate"]
    out["round_3_all_positive_preserved"] = r3["predicted_positive_fraction"] == 1.0 and results["results"]["round_3_candidate"]["pooled"]["TN"] == 0 and results["results"]["round_3_candidate"]["pooled"]["specificity"] == 0.0
    out["rounds_0_to_2_predict_no_positive"] = all(out["states"][k]["predicted_positive_fraction"] == 0.0 for k in ("round_0", "round_1", "round_2"))
    out["no_threshold_tuning_or_calibration"] = proto["decision_threshold"] == {"rule": "positive iff raw sigmoid(logit) >= 0.5", "predeclared": True, "tuned": False, "calibrated": False}
    return out


def lane_separation() -> dict[str, Any]:
    manifest = json.loads((ROOT / "reports/final_showcase/publication/export_manifest.json").read_text())
    report: dict[str, Any] = {"figures": {}, "tables": {}}
    for fid, files in manifest["figures"].items():
        prov = json.loads((ROOT / files["provenance"]["path"]).read_text())
        svg = (ROOT / files["svg"]["path"]).read_text()
        synthetic_source = any("synth_fl_eval" in s for s in prov["sources"])
        report["figures"][fid] = {"lane": prov["lane"], "uses_synthetic_source": synthetic_source, "svg_carries_synthetic_label": LANE_LABEL in svg,
                                  "mixes_synthetic_with_scientific_sources": synthetic_source and any("model_v2" in s for s in prov["sources"]),
                                  "historical_reference_marked": ("historical" in svg.lower()) if prov["lane"] == "B+H" else None, "footer_not_clinical": "not a clinical claim" in svg}
    for tid, files in manifest["tables"].items():
        t = json.loads((ROOT / files["json"]["path"]).read_text())
        synthetic_source = any("synth_fl_eval" in s for s in t["sources"])
        report["tables"][tid] = {"lane": t["lane"], "uses_synthetic_source": synthetic_source, "label_in_caption": LANE_LABEL in t["caption"], "mixes": synthetic_source and any("model_v2" in s for s in t["sources"])}
    text = (ROOT / "docs/final_showcase/manuscript_material.md").read_text()
    sections = {m.group(1): m.group(2) for m in re.finditer(r"\*\*([^*]+):\*\*(.*?)(?=\n\n\*\*|\n\n## )", text, re.S)}
    results = json.loads((ROOT / research.SYNTH).read_text())["results"]
    synth_numbers = {f"{results[k]['pooled'][m]:.4f}" for k in results for m in ("AUPRC", "AUROC") if results[k]["pooled"][m] is not None}
    synth_paragraphs = [para for para in text.split("\n\n") if any(n in para for n in synth_numbers) and "Controlled heterogeneity" not in para]
    abstract = next(para for para in text.split("\n\n") if "We study" in para)
    report["manuscript"] = {"synthetic_paragraphs_with_numbers": len(synth_paragraphs), "every_such_paragraph_has_exact_label": bool(synth_paragraphs) and all(LANE_LABEL in para for para in synth_paragraphs), "abstract_synthetic_sentence_labelled": LANE_LABEL in abstract,
                            "centralized_comparison_declares_point_only": "no paired interval" in text.lower() and "superiority" in text.lower(),
                            "superiority_only_negated": all(re.search(r"\b(no|not|none|never)\b", line.lower()) for line in text.splitlines() if "superior" in line.lower()),
                            "boundary_statement_present": "never pooled with lane B" in text, "reference_required_markers": text.count("REFERENCE_REQUIRED"), "section_headings": list(sections)[:6]}
    return report
