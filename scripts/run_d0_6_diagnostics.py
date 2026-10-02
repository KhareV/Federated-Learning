#!/usr/bin/env python3
"""C-V2-D0.6: execute the real diagnostic reconstruction. Reads only already-frozen evidence
(via scripts._d0_6_lib's gated loaders), computes every diagnostic defined in
configs/model_v2/d0_6_diagnostic_reconstruction_v1.yaml using scripts._d0_6_diagnostics' pure
primitives, and writes the full set of reports/model_v2/c_v2_d0_6/ outputs. No model fitting,
no threshold fitting on historical VALIDATION, no raw waveform access.
"""

from __future__ import annotations

import csv
import json

import numpy as np

import scripts._d0_6_diagnostics as diag
import scripts._d0_6_lib as lib

OUT_DIR = lib.ROOT / "reports/model_v2/c_v2_d0_6"
COMPOSITION_SLICES = ("S_DOMINANT", "V_DOMINANT", "F_CONTAINING", "S_V_TIE")


def _write_csv(name: str, rows: list[dict]) -> None:
    path = OUT_DIR / name
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(name: str, data: dict) -> None:
    (OUT_DIR / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------------------
# Patient / class composition tables (metadata only -- available for both strata)
# ---------------------------------------------------------------------------------------


def build_patient_composition(
    window_rows: list[dict], hr_source: lib.HrFeatureSource
) -> list[dict]:
    by_patient: dict[str, list[dict]] = {}
    for row in window_rows:
        by_patient.setdefault(row["participant_group_id"], []).append(row)

    out_rows: list[dict] = []
    for patient in sorted(by_patient):
        rows = by_patient[patient]
        positives = [r for r in rows if r["label"] == "1"]
        negatives = [r for r in rows if r["label"] == "0"]
        composition_counts = {slice_name: 0 for slice_name in COMPOSITION_SLICES}
        s_containing = v_containing = f_containing = 0
        for row in positives:
            if int(row["mapped_s_count"]) > 0:
                s_containing += 1
            if int(row["mapped_v_count"]) > 0:
                v_containing += 1
            if int(row["mapped_f_count"]) > 0:
                f_containing += 1
            comp = lib.composition_for_row(row)
            if comp in composition_counts:
                composition_counts[comp] += 1
        hr_values = [
            hr_source.by_example_id[r["example_id"]]
            for r in rows
            if r["example_id"] in hr_source.by_example_id
        ]
        missing_hr = len(rows) - len(hr_values)
        out_rows.append(
            {
                "participant_group_id": patient,
                "window_count": len(rows),
                "positive_count": len(positives),
                "negative_count": len(negatives),
                "prevalence": len(positives) / len(rows) if rows else None,
                "s_containing_positive_window_count": s_containing,
                "v_containing_positive_window_count": v_containing,
                "f_containing_positive_window_count": f_containing,
                "composition_S_DOMINANT": composition_counts["S_DOMINANT"],
                "composition_V_DOMINANT": composition_counts["V_DOMINANT"],
                "composition_F_CONTAINING": composition_counts["F_CONTAINING"],
                "composition_S_V_TIE": composition_counts["S_V_TIE"],
                "mean_hr": float(np.mean(hr_values)) if hr_values else None,
                "median_hr": float(np.median(hr_values)) if hr_values else None,
                "missing_hr_count": missing_hr,
                "record_count": len({r["record_id"] for r in rows}),
            }
        )
    return out_rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    train_window_rows = lib.load_window_manifest("TRAIN")
    validation_window_rows = lib.load_window_manifest("VALIDATION")
    train_hr = lib.load_hr_feature("TRAIN")
    validation_hr = lib.load_hr_feature("VALIDATION")

    _write_csv(
        "patient_composition_train_oof.csv",
        build_patient_composition(train_window_rows, train_hr),
    )
    _write_csv(
        "patient_composition_validation.csv",
        build_patient_composition(validation_window_rows, validation_hr),
    )

    model_v1_oof = lib.load_model_v1_train_oof()
    rf_all_oof = lib.load_rf_all_train_oof()

    window_by_id = {r["example_id"]: r for r in train_window_rows}

    def _arrays(rows: list[dict], prob_field: str) -> dict:
        labels = np.array([int(r["label"]) for r in rows], dtype=np.int64)
        probs = np.array([float(r[prob_field]) for r in rows], dtype=np.float64)
        groups = np.array([r["participant_group_id"] for r in rows], dtype=str)
        example_ids = [r["example_id"] for r in rows]
        return {"labels": labels, "probs": probs, "groups": groups, "example_ids": example_ids}

    model_v1_data = {seed: _arrays(rows, "raw_probability") for seed, rows in model_v1_oof.items()}
    rf_data = _arrays(rf_all_oof, "probability")

    # ---- diagnostic thresholds -----------------------------------------------------
    thresholds: dict = {"train_oof": {"MODEL_V1": {}}, "historical_validation": {}}
    for seed, data in model_v1_data.items():
        threshold = diag.diagnostic_threshold(data["labels"], data["probs"])
        predictions = (data["probs"] >= threshold).astype(int)
        from sklearn.metrics import f1_score

        thresholds["train_oof"]["MODEL_V1"][str(seed)] = {
            "threshold": threshold,
            "achieved_pooled_F1": float(f1_score(data["labels"], predictions, zero_division=0)),
        }
    rf_threshold = diag.diagnostic_threshold(rf_data["labels"], rf_data["probs"])
    from sklearn.metrics import f1_score as _f1

    thresholds["train_oof"]["RF_ALL"] = {
        "threshold": rf_threshold,
        "achieved_pooled_F1": float(
            _f1(rf_data["labels"], (rf_data["probs"] >= rf_threshold).astype(int), zero_division=0)
        ),
    }
    cal = lib.load_cal_v1_threshold()
    t014_rf = lib.load_t014_rf_threshold()
    thresholds["historical_validation"] = {
        "MODEL_V1": {"source": "CAL_V1", **cal, "fit_any_threshold": False},
        "RF": {
            "source": "configs/baseline_v1.yaml",
            **t014_rf,
            "fit_any_threshold": False,
            "threshold_dependent_metrics_produced": False,
            "reason": "per-window RF VALIDATION predictions are MISSING_FROZEN_SOURCE",
        },
    }
    _write_json("diagnostic_thresholds.json", thresholds)

    # ---- score distributions ---------------------------------------------------------
    score_rows: list[dict] = []
    for seed, data in model_v1_data.items():
        for label_class in (0, 1):
            mask = data["labels"] == label_class
            summary = diag.score_distribution_summary(data["probs"][mask])
            score_rows.append(
                {
                    "model": "MODEL_V1",
                    "population": "TRAIN_OOF",
                    "seed": seed,
                    "label_class": label_class,
                    "status": "AVAILABLE",
                    **summary,
                }
            )
    for label_class in (0, 1):
        mask = rf_data["labels"] == label_class
        summary = diag.score_distribution_summary(rf_data["probs"][mask])
        score_rows.append(
            {
                "model": "RF_ALL",
                "population": "TRAIN_OOF",
                "seed": None,
                "label_class": label_class,
                "status": "AVAILABLE",
                **summary,
            }
        )
    for model in ("MODEL_V1", "RF"):
        for label_class in (0, 1):
            score_rows.append(
                {
                    "model": model,
                    "population": "VALIDATION",
                    "seed": None,
                    "label_class": label_class,
                    "status": "MISSING_FROZEN_SOURCE",
                    "n": None,
                    "mean": None,
                    "std": None,
                    "p05": None,
                    "p25": None,
                    "median": None,
                    "p75": None,
                    "p95": None,
                    "min": None,
                    "max": None,
                }
            )
    _write_csv("score_distributions.csv", score_rows)

    # ---- class composition (train-oof) ------------------------------------------------
    def _slice_stats(data: dict, threshold: float, slice_name: str) -> dict:
        mask = np.array(
            [
                window_by_id[eid]["label"] == "1"
                and lib.composition_for_row(window_by_id[eid]) == slice_name
                for eid in data["example_ids"]
            ]
        )
        support = int(mask.sum())
        if support == 0:
            return {
                "support": 0,
                "participant_groups": 0,
                "mean_score": None,
                "median_score": None,
                "sensitivity": None,
                "FN_rate": None,
            }
        scores = data["probs"][mask]
        labels = data["labels"][mask]
        predictions = (scores >= threshold).astype(int)
        tp = int(((predictions == 1) & (labels == 1)).sum())
        fn = int(((predictions == 0) & (labels == 1)).sum())
        sensitivity = tp / support
        groups = {
            window_by_id[eid]["participant_group_id"]
            for eid, keep in zip(data["example_ids"], mask, strict=True)
            if keep
        }
        return {
            "support": support,
            "participant_groups": len(groups),
            "mean_score": float(np.mean(scores)),
            "median_score": float(np.median(scores)),
            "sensitivity": sensitivity,
            "FN_rate": fn / support,
        }

    class_rows: list[dict] = []
    for slice_name in COMPOSITION_SLICES:
        per_seed_stats: dict[int, dict] = {}
        for seed, data in model_v1_data.items():
            threshold = thresholds["train_oof"]["MODEL_V1"][str(seed)]["threshold"]
            stats = _slice_stats(data, threshold, slice_name)
            per_seed_stats[seed] = stats
            class_rows.append(
                {"model": "MODEL_V1", "seed": seed, "composition": slice_name, **stats}
            )

        seed_sens = [
            s["sensitivity"] for s in per_seed_stats.values() if s["sensitivity"] is not None
        ]
        any_stats = next(iter(per_seed_stats.values()))
        class_rows.append(
            {
                "model": "MODEL_V1",
                "seed": "SCALAR_SUMMARY_ACROSS_SEEDS",
                "composition": slice_name,
                "support": any_stats["support"],
                "participant_groups": any_stats["participant_groups"],
                "mean_score": None,
                "median_score": None,
                "sensitivity": float(np.mean(seed_sens)) if seed_sens else None,
                "FN_rate": (1 - float(np.mean(seed_sens))) if seed_sens else None,
            }
        )
        rf_stats = _slice_stats(rf_data, rf_threshold, slice_name)
        class_rows.append({"model": "RF_ALL", "seed": None, "composition": slice_name, **rf_stats})
    _write_csv("class_composition_train_oof.csv", class_rows)

    # ---- class composition (validation, metadata-only) --------------------------------
    val_class_rows: list[dict] = []
    for slice_name in COMPOSITION_SLICES:
        positives = [r for r in validation_window_rows if r["label"] == "1"]
        matching = [r for r in positives if lib.composition_for_row(r) == slice_name]
        groups = {r["participant_group_id"] for r in matching}
        val_class_rows.append(
            {
                "composition": slice_name,
                "support": len(matching),
                "participant_groups": len(groups),
                "mean_score": None,
                "median_score": None,
                "sensitivity": None,
                "FN_rate": None,
                "status": "MISSING_FROZEN_SOURCE_NO_PER_WINDOW_PREDICTIONS",
            }
        )
    _write_csv("class_composition_validation.csv", val_class_rows)

    # ---- threshold-region error mass ---------------------------------------------------
    region_rows: list[dict] = []
    for seed, data in model_v1_data.items():
        result = diag.threshold_region_counts(
            data["labels"],
            data["probs"],
            thresholds["train_oof"]["MODEL_V1"][str(seed)]["threshold"],
        )
        region_rows.append(
            {
                "model": "MODEL_V1",
                "population": "TRAIN_OOF",
                "seed": seed,
                "status": "AVAILABLE",
                **result,
            }
        )
    region_rows.append(
        {
            "model": "RF_ALL",
            "population": "TRAIN_OOF",
            "seed": None,
            "status": "AVAILABLE",
            **diag.threshold_region_counts(rf_data["labels"], rf_data["probs"], rf_threshold),
        }
    )
    for model in ("MODEL_V1", "RF"):
        region_rows.append(
            {
                "model": model,
                "population": "VALIDATION",
                "seed": None,
                "status": "MISSING_FROZEN_SOURCE",
                "threshold": None,
                "FP_near": None,
                "FP_total": None,
                "FP_near_fraction": None,
                "FN_near": None,
                "FN_total": None,
                "FN_near_fraction": None,
                "ALL_errors_near": None,
                "ALL_errors_total": None,
                "ALL_errors_near_fraction": None,
            }
        )
    _write_csv("threshold_region_errors.csv", region_rows)

    # ---- leave-one-patient-out AUPRC ----------------------------------------------------
    loo_rows: list[dict] = []
    for seed, data in model_v1_data.items():
        deltas = diag.leave_one_patient_out_auprc(data["labels"], data["probs"], data["groups"])
        full = diag.pooled_auprc(data["labels"], data["probs"])
        for patient, delta in deltas.items():
            loo_rows.append(
                {
                    "model": "MODEL_V1",
                    "seed": seed,
                    "participant_group_id": patient,
                    "full_AUPRC": full,
                    "contribution_delta": delta,
                }
            )
    rf_deltas = diag.leave_one_patient_out_auprc(
        rf_data["labels"], rf_data["probs"], rf_data["groups"]
    )
    rf_full = diag.pooled_auprc(rf_data["labels"], rf_data["probs"])
    for patient, delta in rf_deltas.items():
        loo_rows.append(
            {
                "model": "RF_ALL",
                "seed": None,
                "participant_group_id": patient,
                "full_AUPRC": rf_full,
                "contribution_delta": delta,
            }
        )
    _write_csv("patient_loo_auprc.csv", loo_rows)

    # ---- patient brier -------------------------------------------------------------------
    brier_rows: list[dict] = []
    for seed, data in model_v1_data.items():
        briers = diag.patient_brier(data["labels"], data["probs"], data["groups"])
        for patient, value in briers.items():
            brier_rows.append(
                {
                    "model": "MODEL_V1",
                    "seed": seed,
                    "participant_group_id": patient,
                    "brier": value,
                    "status": "AVAILABLE",
                }
            )
    rf_briers = diag.patient_brier(rf_data["labels"], rf_data["probs"], rf_data["groups"])
    for patient, value in rf_briers.items():
        brier_rows.append(
            {
                "model": "RF_ALL",
                "seed": None,
                "participant_group_id": patient,
                "brier": value,
                "status": "AVAILABLE",
            }
        )
    validation_patients = sorted({r["participant_group_id"] for r in validation_window_rows})
    for model in ("MODEL_V1", "RF"):
        for patient in validation_patients:
            brier_rows.append(
                {
                    "model": model,
                    "seed": None,
                    "participant_group_id": patient,
                    "brier": None,
                    "status": "MISSING_FROZEN_SOURCE",
                }
            )
    _write_csv("patient_brier.csv", brier_rows)

    print("C-V2-D0.6: core diagnostic tables written")
    return {
        "model_v1_data": model_v1_data,
        "rf_data": rf_data,
        "thresholds": thresholds,
        "loo_rows": loo_rows,
        "region_rows": region_rows,
        "class_rows": class_rows,
    }


if __name__ == "__main__":
    main()
