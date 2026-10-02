#!/usr/bin/env python3
"""V2-004 D1: apply the frozen hard-disqualification rules, bootstrap qualification, and
one-standard-error advancement rule to the D1 result, producing d1_decision.json. This is the
ONLY code path permitted to decide D1 advancement -- no manual candidate selection.
"""

from __future__ import annotations

import json

import scripts._v2_004_lib as lib

OUT_DIR = lib.ROOT / "reports/model_v2/v2_004"
RUNS_DIR = OUT_DIR / "runs"

SIMPLICITY_ORDER = {
    "MODEL_V2_CAPCTRL": 0,
    "MODEL_V2_TCN_MEAN": 1,
    "MODEL_V2_TCN_MEANMAX": 2,
}


def _load_json(name: str) -> dict:
    return json.loads((OUT_DIR / name).read_text(encoding="utf-8"))


def _load_fit_summaries(architecture_id: str) -> list[dict]:
    summaries = []
    for fold in lib.OUTER_FOLDS:
        exp_id = lib.experiment_id("D1", architecture_id, fold, lib.D1_SEED)
        summaries.append(
            json.loads((RUNS_DIR / exp_id / "fit_summary.json").read_text(encoding="utf-8"))
        )
    return summaries


def _load_ledger_roles_seen() -> set[str]:
    path = OUT_DIR / "cv_role_access_ledger.jsonl"
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as handle:
        return {json.loads(line)["role"] for line in handle if line.strip()}


def hard_disqualify(architecture_id: str, oof_metrics: dict, closure: dict) -> dict:
    reasons: list[str] = []
    fit_summaries = _load_fit_summaries(architecture_id)

    expected_params = lib.EXPECTED_PARAMETER_COUNTS[architecture_id]
    if expected_params > lib.PARAMETER_COUNT_HARD_CAP:
        reasons.append(f"parameter_count {expected_params} > 120000")
    for summary in fit_summaries:
        if summary["parameter_count"] != expected_params:
            reasons.append(
                f"fold {summary['outer_fold']} parameter_count "
                f"{summary['parameter_count']} != expected {expected_params}"
            )
        if summary.get("non_finite_detected"):
            reasons.append(f"fold {summary['outer_fold']} non_finite_detected=true")

    arch_metrics = oof_metrics["per_architecture"].get(architecture_id)
    if arch_metrics is None:
        reasons.append("no OOF metrics available for architecture (closure or load failure)")
    else:
        auroc_guardrail = 0.5769905535518993
        if arch_metrics["pooled_OOF_AUROC"] < auroc_guardrail:
            reasons.append(
                f"pooled_OOF_AUROC {arch_metrics['pooled_OOF_AUROC']:.6f} < "
                f"V1 three-seed mean AUROC {auroc_guardrail:.6f}"
            )

    if not closure[architecture_id]["closure_exact"]:
        reasons.append("OOF closure failed")

    roles_seen = _load_ledger_roles_seen()
    if not roles_seen <= {"OPTIMISE", "INNER_VALIDATION", "OUTER_TEST"}:
        reasons.append(f"role/partition leakage: roles_seen={sorted(roles_seen)}")

    return {
        "architecture_id": architecture_id,
        "disqualified": len(reasons) > 0,
        "reasons": reasons,
    }


def main() -> None:
    oof_metrics = _load_json("d1_oof_metrics.json")
    closure = _load_json("oof_closure_audit.json")["per_architecture"]
    bootstrap_summary = _load_json("d1_candidate_vs_v1_bootstrap_summary.json")
    causal_summary = _load_json("d1_causal_hypothesis_summary.json")

    disqualification = {
        architecture_id: hard_disqualify(architecture_id, oof_metrics, closure)
        for architecture_id in lib.ARCHITECTURE_IDS
    }

    point_metrics = {
        architecture_id: {
            "pooled_OOF_AUPRC": oof_metrics["per_architecture"][architecture_id][
                "pooled_OOF_AUPRC"
            ],
            "pooled_OOF_AUROC": oof_metrics["per_architecture"][architecture_id][
                "pooled_OOF_AUROC"
            ],
        }
        for architecture_id in lib.ARCHITECTURE_IDS
        if architecture_id in oof_metrics["per_architecture"]
    }

    bootstrap_qualified = {
        architecture_id: bootstrap_summary["per_architecture"][architecture_id][
            "bootstrap_qualified"
        ]
        for architecture_id in lib.ARCHITECTURE_IDS
    }

    qualified = [
        architecture_id
        for architecture_id in lib.ARCHITECTURE_IDS
        if not disqualification[architecture_id]["disqualified"]
        and bootstrap_qualified[architecture_id]
    ]

    raw_ranking = sorted(
        point_metrics.keys(),
        key=lambda a: (-point_metrics[a]["pooled_OOF_AUPRC"], lib.EXPECTED_PARAMETER_COUNTS[a], a),
    )

    one_se = {
        "raw_best": None,
        "raw_best_point_AUPRC": None,
        "se_raw_best": None,
        "one_se_cutoff": None,
        "near_best_set": [],
        "preferred_architecture": None,
        "d2_advancement_list": [],
    }

    if qualified:
        qualified_ranking = [a for a in raw_ranking if a in qualified]
        raw_best = qualified_ranking[0]
        se_raw_best = bootstrap_summary["per_architecture"][raw_best][
            "candidate_bootstrap_sd_AUPRC"
        ]
        if se_raw_best is None:
            raise RuntimeError(f"no valid bootstrap SD for raw-best candidate {raw_best}")
        cutoff = point_metrics[raw_best]["pooled_OOF_AUPRC"] - se_raw_best
        near_best = [a for a in qualified if point_metrics[a]["pooled_OOF_AUPRC"] >= cutoff]
        preferred = sorted(near_best, key=lambda a: (SIMPLICITY_ORDER[a], a))[0]

        advancement = [preferred]
        remaining = [a for a in qualified_ranking if a != preferred]
        if remaining:
            advancement.append(remaining[0])
        advancement = advancement[:2]

        one_se.update(
            {
                "raw_best": raw_best,
                "raw_best_point_AUPRC": point_metrics[raw_best]["pooled_OOF_AUPRC"],
                "se_raw_best": se_raw_best,
                "one_se_cutoff": cutoff,
                "near_best_set": near_best,
                "preferred_architecture": preferred,
                "d2_advancement_list": advancement,
            }
        )

    decision = {
        "stage": "D1",
        "point_metrics": point_metrics,
        "disqualification": disqualification,
        "paired_delta_vs_v1": bootstrap_summary["per_architecture"],
        "bootstrap_qualified": bootstrap_qualified,
        "raw_ranking": raw_ranking,
        "qualified": qualified,
        "one_se_rule": one_se,
        "causal_hypotheses": causal_summary["hypotheses"],
        "fit_count": 15,
        "scope_audit": {
            "roles_seen": sorted(_load_ledger_roles_seen()),
            "roles_match_known_set": _load_ledger_roles_seen()
            <= {"OPTIMISE", "INNER_VALIDATION", "OUTER_TEST"},
        },
        "d2_required": len(one_se["d2_advancement_list"]) > 0,
        "v2_004_outcome": ("D1_ZERO_QUALIFIERS" if not qualified else None),
    }

    (OUT_DIR / "d1_decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(decision["one_se_rule"], indent=2))
    print("qualified:", qualified)


if __name__ == "__main__":
    main()
