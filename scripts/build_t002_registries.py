#!/usr/bin/env python3
"""Build deterministic T002 traceability registries from audited source decisions."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "manifests"
SPEC = "NHM_ML_Revised_Locked_Specification_v2.2.docx"
PLAN = "NHM_Solo_Implementation_Execution_Plan_v1.0.docx"
PLAN_SHA256 = "f260a93e973161a1461497fbb4ae0194bc72f20fc47c1689e57ec6c0cd6f2696"


def write_csv(filename: str, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path = MANIFESTS / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


TASK_FIELDS = [
    "task_id",
    "phase_family",
    "task_name",
    "prerequisites",
    "gate_impact",
    "status",
    "implemented_at_commit",
    "evidence_path",
    "source_document",
    "source_locator",
    "source_sha256",
    "source_prerequisites",
    "source_gate_impact",
    "notes",
]


def task(
    task_id: str,
    family: str,
    name: str,
    prerequisites: str,
    gates: str,
    *,
    status: str = "NOT_STARTED",
    commit: str = "",
    evidence: str = "",
    source_prerequisites: str = "",
    source_gate_impact: str = "",
    notes: str = "",
) -> dict[str, str]:
    return {
        "task_id": task_id,
        "phase_family": family,
        "task_name": name,
        "prerequisites": prerequisites,
        "gate_impact": gates,
        "status": status,
        "implemented_at_commit": commit,
        "evidence_path": evidence,
        "source_document": PLAN,
        "source_locator": f"Section 22 — Primary Implementation Task Packets / {task_id}",
        "source_sha256": PLAN_SHA256,
        "source_prerequisites": source_prerequisites,
        "source_gate_impact": source_gate_impact,
        "notes": notes,
    }


TASK_PREREQUISITES = {
    "T001": "",
    "T002": "T001",
    "T003": "T001;T002;G0",
    "T004": "T001;T003",
    "T005": "T003",
    "T006": "T003;G0",
    "T007": "T003;G0",
    "T008": "T006;T007",
    "T009": "T008;G4",
    "T010": "T009",
    "T011": "T006;T010",
    "T012": "T010;T011",
    "T013": "T008;T009;T011;T012",
    "T014": "T013;G6",
    "T015": "T014;G7",
    "T016": "T015",
    "T017": "T016;G8",
    "T018": "T017",
    "T019": "T018;G10",
    "T020": "T008;T018;G10",
    "T021": "T007;T012;T013",
    "T022": "T013;T021",
    "T023": "T017;T021;T022",
    "T024": "T003",
    "T025": "T009;T016;T024",
    "T026": "T025;G11",
    "T027": "T026",
    "T028": "T025;G11",
    "T029": "T016;G8",
    "T030": "T004;T013;T029",
    "T031": "T016;T018;G10",
    "T032": "T003;T017;T029",
    "T033": "T022;T032;G18",
    "T034": "T030;T032;T033",
    "T035": "T034",
    "T036": "T035;G20;G21",
}


def canonical_tasks() -> list[dict[str, str]]:
    snapshot = json.loads((MANIFESTS / "task_packets_v1.json").read_text(encoding="utf-8"))
    if snapshot["source_document"] != PLAN or snapshot["source_sha256"] != PLAN_SHA256:
        raise RuntimeError("canonical task snapshot is not bound to the execution authority")
    tasks = []
    for packet in snapshot["packets"]:
        task_id = packet["task_id"]
        gates = packet["gate_freeze_impact"].replace("-", ";")
        gates = gates.replace("post;G10", "G10").replace("G11 prep", "G11")
        status = {
            "T001": "PASS",
            "T002": "PASS",
            "T003": "PASS",
            "T004": "BLOCKED",
            "T005": "PASS",
            "T006": "PASS",
            "T007": "PASS",
            "T008": "PASS",
            "T009": "PASS",
            "T010": "PASS",
            "T011": "PASS",
            "T012": "PASS",
            "T013": "PASS",
        }.get(task_id, "NOT_STARTED")
        commit = {
            "T001": "0069fdf4c75609bf02b3a8bc34d8889f1702c5c9",
            "T002": "83f0136052cd5136705f2dfc9347f15f2d9c425e",
            "T003": "1f35bc044474900b5a54d5a17d51727e5a1a2388",
            "T004": "0312d6f6c529676d036f83693a9a58c19f33ef08",
            "T005": "c3f7d85e71ceeeafa2bc31ff902a61913a51b2cf",
            "T006": "645de3328d990c38ca60055c6a79d8833bfe95c7",
            "T007": "5786a7fa302b995d2f69a4f5e07df621cd3dddde",
            "T008": "27bcdc3986b6351cfde334060b521a1ff5eeac9d",
            "T009": "ce8375304d6e8a82dfc105c0d2d555782d330e85",
            "T010": "df22ee334a873a1489bc944b0c39bf5dcbeed4a7",
            "T011": "11a824f2aa1f2d1598cb26db798cc5d9185925c1",
            "T012": "9fd6a1350a70eaf762fcdc6d47528531950c59b3",
            "T013": "",
        }.get(task_id, "")
        evidence = {
            "T001": "reports/t001/closure_verification.json",
            "T002": "reports/t002/source_reconciliation.json",
            "T003": "reports/t003/contract_validation.json",
            "T004": "reports/t004/hardware_deferral.json",
            "T005": "reports/t005/smoke_report.json",
            "T006": "reports/t006/mitdb_validation.json",
            "T007": "reports/data/validation_report.json",
            "T008": "reports/labels/label_audit.json",
            "T009": "reports/t009/split_generation.json",
            "T010": "reports/splits/split_audit.json",
            "T011": "reports/preprocessing/resampler_causality.json",
            "T012": "reports/t012/preproc_component_status.json",
            "T013": "reports/preprocessing/causality_tests.json",
        }.get(task_id, "")
        notes = TASK_NOTES_OVERRIDE.get(
            task_id,
            (
                "Canonical execution-plan packet; normalized prerequisite IDs follow "
                "Sections 4-5 where the packet uses a cross-reference."
            ),
        )
        tasks.append(
            task(
                task_id,
                packet["phase"],
                packet["task_name"],
                TASK_PREREQUISITES[task_id],
                gates,
                status=status,
                commit=commit,
                evidence=evidence,
                source_prerequisites=packet["prerequisites"],
                source_gate_impact=packet["gate_freeze_impact"],
                notes=notes,
            )
        )
    return tasks


TASK_NOTES_OVERRIDE = {
    "T004": (
        "Canonical execution-plan packet; normalized prerequisite IDs follow Sections 4-5 "
        "where the packet uses a cross-reference. BLOCKED_HARDWARE: physical ESP32/AD8232/"
        "MAX30102 hardware is unavailable for bench testing; recovery per the execution plan "
        "is continue software with fixtures, block wearable evidence. See "
        "docs/HARDWARE_DEFERRED_EXECUTION_PLAN.md and reports/t004/hardware_deferral.json."
    ),
    "T005": (
        "Canonical execution-plan packet; normalized prerequisite IDs follow Sections 4-5 "
        "where the packet uses a cross-reference. Software-only vertical slice evidence "
        "(WEARABLE_SIM_SMOKE -> MOCK_INFERENCE_V0 -> FIXTURE_STATE_POLICY_V0); T004 remains "
        "BLOCKED_HARDWARE and G1/G16 are unaffected by this task."
    ),
    "T006": (
        "Canonical execution-plan packet; normalized prerequisite IDs follow Sections 4-5 "
        "where the packet uses a cross-reference. Real PhysioNet MIT-BIH v1.0.0 acquired and "
        "hash-verified (48/48 records); exact-MLII channel policy applied from WFDB headers "
        "only (46 eligible, 102/104 excluded for no exact MLII channel). No patient split, "
        "no AAMI mapping, no preprocessing; G2/G3 closed jointly with T007."
    ),
    "T007": (
        "Canonical execution-plan packet; normalized prerequisite IDs follow Sections 4-5 "
        "where the packet uses a cross-reference. Real PhysioNet INCART/NSTDB/BIDMC v1.0.0 "
        "acquired and hash-verified (75/15/53 records); exact-Lead-II policy (INCART, 75/75 "
        "eligible), source-defined role classification (NSTDB: 12 stress-ECG/3 pure-noise), "
        "and exact-channel availability audit (BIDMC: PLETH/II/HR/PULSE/SpO2) applied from "
        "WFDB headers only. Dataset roles locked (INCART=external-eval-only, "
        "NSTDB=robustness-only, BIDMC=multimodal-engineering-only; MITDB remains the only "
        "training-eligible dataset). No split, no AAMI mapping, no preprocessing, no "
        "external evaluation, no robustness experiment, no model training. G2/G3 now PASS "
        "jointly with T006; G1/G4 remain open."
    ),
    "T008": (
        "Canonical execution-plan packet; normalized prerequisite IDs follow Sections 4-5 "
        "where the packet uses a cross-reference. Single shared, pure, dataset-independent "
        "AAMI_SVF_MAP_V1 beat-symbol mapper (datasets/labels.py) plus the AAMI_SVF_WINDOW_V1 "
        "window-target decision rule, frozen in manifests/labels/AAMI_SVF_MAP_V1.yaml (freeze "
        "F04). Full MIT-BIH/INCART annotation symbol census from real T006/T007 raw data with "
        "explicit SOURCE vs CORE_CHANNEL_ELIGIBLE scope separation; raw-count conservation and "
        "single-classification-per-symbol verified. MIT-BIH's real '!' and INCART's real 'B'/"
        "'n' beat symbols are outside the frozen allowlist and are UNMAPPABLE, not coerced. "
        "INCART's seven documented pre-signal annotations (T007 finding) are preserved and "
        "re-reported (post-signal count 0). No window-building, no patient split, no "
        "preprocessing, no model training. G4 now PASS; G1 remains open."
    ),
    "T009": (
        "Canonical execution-plan packet; normalized prerequisite IDs follow Sections 4-5 "
        "where the packet uses a cross-reference. Deterministic MITDB_SPLIT_V1 patient-group "
        "partition (datasets/grouping.py) from the frozen T006 exact-MLII eligible pool (46 "
        "records, 102/104 excluded) and the frozen AAMI_SVF_MAP_V1 mapper (T008/F04). Records "
        "201/202 grouped before allocation (45 eligible patient groups). Stratified on "
        "has_svf_event (42 positive / 3 negative) via one predeclared exact-integer "
        "minimum-squared-deviation allocation, one fixed seed (20260927), Hamilton/largest- "
        "remainder partition apportionment, and SHA-256 stable ordering; zero patient "
        "overlap, zero unassigned groups, byte-identical regeneration verified. Partition "
        "quotas: TRAIN=27, VALIDATION=7, CALIBRATION=4, INTERNAL_TEST=7 patient groups. No "
        "window-building, no preprocessing, no model training, no external evaluation. "
        "split_status=DRAFT_VALIDATED, freeze_status=NOT_FROZEN: G5/F05 remain open -- T010 "
        "owns the independent leakage audit and freeze."
    ),
    "T010": (
        "Canonical execution-plan packet; normalized prerequisite IDs follow Sections 4-5 "
        "where the packet uses a cross-reference. Independent audit of the T009 candidate "
        "MITDB_SPLIT_V1 (evaluation/leakage_audit.py) -- every G5 invariant recomputed from "
        "T006 eligibility, the frozen AAMI_SVF_MAP_V1 mapper, and T009's grouping/split "
        "manifests, never trusted from T009's own report; candidate split byte-identical "
        "before and after the audit. Zero patient overlap, complete group assignment, "
        "201/202 co-grouped and co-partitioned, strata independently recomputed from real "
        "raw annotations (0 mismatches), upstream hashes verified, deterministic "
        "reconstruction matches the committed manifest exactly. Partition-role/fit-scope/"
        "INCART-external-role contracts implemented and adversarially tested; a synthetic "
        "window-manifest leakage harness implemented and validated (real windows remain "
        "absent, deferred to T013). Freeze lock manifests/splits/MITDB_SPLIT_V1.lock.json "
        "created and self-verified; tamper-detection matrix passes. No window-building, no "
        "preprocessing, no model training, no external evaluation. G5 now PASS, F05 now "
        "FROZEN; G6/F06 remain open (causal resampling/filtering/gaps/real windows are not "
        "yet implemented)."
    ),
    "T011": (
        "Canonical execution-plan packet; normalized prerequisite IDs follow Sections 4-5 "
        "where the packet uses a cross-reference. Stateful causal rational/polyphase FIR "
        "resampler (preprocessing/resample.py, PREPROC_V1_RESAMPLER_V1) for MITDB (360->250 "
        "Hz, up=25/down=36, 721 taps) and INCART (257->250 Hz, up=250/down=257, 5141 taps); "
        "FIR_KAISER_POLYPHASE_V1 design (beta=5.0) fixed from rate/math requirements only, "
        "never tuned on data. Bounded-memory streaming implementation matches a slow direct "
        "causal reference and is invariant to future-appended input and to arbitrary "
        "chunking, both to machine-epsilon tolerance; output timestamps sit on an exact "
        "4000us/250Hz grid with no backward group-delay compensation (10 output samples/"
        "40ms delay recorded explicitly as metadata for both conversions). Coefficients "
        "committed and hash-verified; regeneration is bit-identical. No "
        "resample/resample_poly/filtfilt/sosfiltfilt in the production module (statically "
        "audited). F05 split freeze verified unchanged before and after (byte-identical "
        "MITDB_SPLIT_V1.csv). No GAP_POLICY_V1, no physiological bandpass filtering, no real "
        "windows, no normalization, no model training. G6 remains open -- T012/T013 still "
        "required."
    ),
    "T012": (
        "Canonical execution-plan packet; normalized prerequisite IDs follow Sections 4-5 "
        "where the packet uses a cross-reference. Causal 4th-order Butterworth SOS bandpass "
        "filters (preprocessing/filters.py + preprocessing/ecg.py + preprocessing/ppg.py): "
        "ECG PREPROC_V1_ECG_FILTER_V1 (0.5-40Hz, fs=250Hz) and PPG PREPROC_V1_PPG_FILTER_V1 "
        "(0.5-8Hz, fs=100Hz), both stable-pole SOS, committed/hash-verified, matching a "
        "one-shot sosfilt reference and invariant to future-appended input and to arbitrary "
        "chunking to exact float64 tolerance; independent red/IR PPG channel state. "
        "GAP_POLICY_V1 (preprocessing/gaps.py): exact integer 100ms short/long "
        "classification, causal last-valid-value ZOH short-gap fill (provably independent "
        "of the post-gap sample), no-fill long-gap segment break with resampler/filter "
        "reset and UNUSABLE-spanning provenance for T013. Integration pipeline "
        "(preprocessing/ecg.py::ECGPreprocessingPipeline) enforces the locked order source "
        "-> GAP_POLICY_V1 -> validated T011 resampler -> ECG filter; feeds the resampler "
        "segment-local indices after a reset (a latent T011 nonzero-origin readiness defect "
        "was found and avoided at the integration layer, not by editing T011's validated "
        "resample.py) while preserving true global source indices as separate provenance. "
        "No resample/resample_poly/filtfilt/sosfiltfilt in production code. F05 split "
        "freeze and T011 resampler behavior/coefficients verified unchanged. No real "
        "windows, quality classification, normalization, or model code. G6 remains open, "
        "F06 remains NOT_FROZEN -- T013 still required."
    ),
}

TASKS = canonical_tasks()


REQ_FIELDS = [
    "requirement_id",
    "parent_requirement_id",
    "requirement_type",
    "short_name",
    "requirement_text",
    "source_document",
    "source_version",
    "source_section",
    "source_page_or_locator",
    "mandatory",
    "implementation_tasks",
    "planned_files_or_modules",
    "validation_method",
    "acceptance_criterion",
    "gate_ids",
    "evidence_artifacts",
    "freeze_stage",
    "change_class",
    "claim_boundary",
    "status",
    "notes",
]


def req(
    requirement_id: str,
    requirement_type: str,
    short_name: str,
    requirement_text: str,
    section: str,
    tasks: str,
    files: str,
    validation: str,
    acceptance: str,
    gates: str,
    evidence: str,
    freeze: str,
    change: str,
    *,
    parent: str = "",
    claim: str = "",
    status: str = "PLANNED",
    notes: str = "",
    source: str = SPEC,
    version: str = "2.2",
    locator: str = "",
    mandatory: str = "TRUE",
) -> dict[str, str]:
    return {
        "requirement_id": requirement_id,
        "parent_requirement_id": parent,
        "requirement_type": requirement_type,
        "short_name": short_name,
        "requirement_text": requirement_text,
        "source_document": source,
        "source_version": version,
        "source_section": section,
        "source_page_or_locator": locator or section,
        "mandatory": mandatory,
        "implementation_tasks": tasks,
        "planned_files_or_modules": files,
        "validation_method": validation,
        "acceptance_criterion": acceptance,
        "gate_ids": gates,
        "evidence_artifacts": evidence,
        "freeze_stage": freeze,
        "change_class": change,
        "claim_boundary": claim,
        "status": status,
        "notes": notes,
    }


REQUIREMENTS = [
    req("R01", "SCIENTIFIC_TARGET", "AAMI SVF target and map", "Use AAMI_SVF_WINDOW_V1 with the identical explicit AAMI_SVF_MAP_V1 allowlist for MIT-BIH and INCART.", "Sections 9.1-9.2", "T003;T007", "contracts/LABEL_SCHEMA_V1.md;datasets/labels.py", "Mapper unit tests cover every allowlisted, paced, unknown, unmapped, and non-beat symbol.", "Both datasets use the same frozen pure mapper and no unlisted beat is coerced.", "G4", "reports/labels/label_audit.json", "LABEL_MAPPING", "C"),
    req("R02", "SCIENTIFIC_TARGET", "Window and cadence", "Prediction uses a 10-second ECG window with 5-second stride and right-edge timestamp.", "Sections 8 and 9.4", "T003;T010", "contracts/window_v1.schema.json;preprocessing/windows.py", "Synthetic boundary and future-sample tests.", "Exact 2500-sample windows at 250 Hz occur every 5 seconds with no sample after t.", "G6", "reports/preprocessing/window_tests.json", "PREPROCESSING", "C"),
    req("R03", "DATASET_POLICY", "Locked ECG channels", "Use MIT-BIH channel named exactly MLII and INCART channel named exactly II.", "Section 6.2", "T005;T006;T020", "configs/datasets/*.yaml;datasets/channel_policy.py", "Header-name selection and missing-channel exclusion tests.", "Only locked named leads are used and exclusions precede split/evaluation.", "G3;G10", "manifests/datasets/channel_exclusions.csv", "DATASET_VERSIONS", "C"),
    req("R04", "SPLIT_POLICY", "Patient-disjoint split", "Split patients before windows; group MIT-BIH records 201 and 202; keep patients indivisible across partitions.", "Section 11.1", "T008", "manifests/splits/MITDB_SPLIT_V1.csv;datasets/splits.py", "Participant-set disjointness and 201/202 grouping assertions.", "Zero patient overlap and records 201/202 share a group.", "G5", "reports/splits/split_audit.json", "PATIENT_SPLIT", "C"),
    req("R05", "PREPROCESSING", "Causal preprocessing", "All deployment transforms, including filtering and stateful rational/polyphase resampling, use current/past data only.", "Sections 2.4 and 8", "T009;T010", "preprocessing/ecg.py;preprocessing/resample.py", "Future-append, impulse-causality, and chunk-equivalence tests.", "Earlier outputs are invariant to arbitrary appended futures and chunking matches continuous streaming.", "G6", "reports/preprocessing/causality_tests.json", "PREPROCESSING", "C"),
    req("R06", "PREPROCESSING", "Causal gap policy", "Gaps <=100 ms use last-value causal ZOH plus gap mask; gaps >100 ms are unfilled and break/reset state.", "Section 8.2", "T009;T010", "preprocessing/gaps.py;configs/GAP_POLICY_V1.yaml", "Short/long synthetic gap tests with alternative futures.", "Short fills exactly equal last pre-gap sample; long-gap spanning windows are UNUSABLE and state resets.", "G6", "reports/preprocessing/gap_tests.json", "PREPROCESSING", "C"),
    req("R07", "MODEL", "Training-only majority baseline", "Choose and freeze the majority class from training prevalence only, then evaluate unchanged everywhere.", "Sections 1.1 and 12", "T011", "models/baselines.py;configs/baseline_v1.yaml", "Fixture with held-out prevalence reversal.", "Prediction class remains determined solely by training labels.", "G7", "reports/baselines/baseline_report.json", "BASELINE_CONFIGURATION", "C"),
    req("R08", "MODEL", "MODEL_V1 contract", "Implement the locked 1D CNN architecture and training contract with train-only class weighting and fixed seeds.", "Sections 13.1-13.2", "T012", "models/ecg_cnn.py;configs/model_v1.yaml;training/centralized.py", "Shape, deterministic test-vector, seed, config, and checkpoint-hash tests.", "Frozen MODEL_V1 reproduces logits within tolerance and retains its SHA-256/config.", "G8", "checkpoints/MODEL_V1.manifest.json", "MODEL_V1", "C"),
    req("R09", "CALIBRATION", "Dedicated calibration", "Fit temperature and F1 threshold only on the dedicated calibration partition after MODEL_V1 lock.", "Section 24", "T017", "evaluation/calibration.py;configs/calibration_v1.yaml", "Partition provenance assertion and calibration regression tests.", "Calibration artifact names patient count/domain and threshold is frozen before test/external use.", "G10", "reports/calibration/calibration.json", "CALIBRATION", "C"),
    req("R10", "STATISTICS", "Patient-cluster bootstrap", "Use 2,000 patient-cluster bootstrap resamples for internal/external CIs; prohibit window-level CIs.", "Sections 23.2-23.3", "T018;T020", "evaluation/bootstrap.py;evaluation/metrics.py", "Known clustered fixture and paired-resample tests.", "Pooled metrics are recomputed using all windows of sampled patients and patient-macro F1 is computed per patient.", "G10", "reports/evaluation/bootstrap_audit.json", "INTERNAL_TEST", "C"),
    req("R11", "EXPERIMENT", "NSTDB robustness", "Evaluate frozen MODEL_V1 under controlled MIT-BIH NSTDB noise without claiming universal robustness.", "Sections 6 and 16; Appendix A E05", "T019", "evaluation/noise.py;experiments/E05.yaml", "Frozen checkpoint/config provenance and SNR/noise-regime checks.", "Noise degradation report is reproducible and limited to tested regimes.", "G10", "reports/noise_robustness/report.json", "INTERNAL_TEST", "C"),
    req("R12", "EXPERIMENT", "INCART external evaluation", "Run one locked INCART Lead II evaluation with frozen preprocessing, map, model, calibration, and threshold before adaptation.", "Sections 6.2 and 16; Appendix A E06", "T020", "evaluation/external.py;experiments/E06.yaml", "Checkpoint/map/channel hashes and no-adaptation audit.", "External evaluation occurs once under frozen inputs with patient-cluster CIs.", "G10", "reports/external_incart/report.json", "EXTERNAL_EVALUATION", "C"),
    req("R13", "MULTIMODAL", "Context not learned arrhythmia fusion", "PPG, SpO2, and HR support deterministic quality/context and never form a learned AAMI-SVF classifier in core scope.", "Sections 14-15", "T013;T014;T016", "preprocessing/ppg.py;fusion/context.py", "Architecture and claim audit; missing-context/state tests.", "Primary model input remains ECG only and multimodal reports make no predictive-gain claim.", "G9", "reports/bidmc_multimodal_engineering/report.json", "MULTIMODAL_CONTEXT", "C", claim="No learned multimodal arrhythmia prediction."),
    req("R14", "ALERTING", "ALERT_POLICY_V1", "Open after two consecutive VALID above-threshold windows; close after two VALID below; enforce 30-second cooldown.", "Section 15.1", "T015", "fusion/alert_policy.py;configs/ALERT_POLICY_V1.yaml", "Scripted transition sequences including DEGRADED and UNUSABLE.", "Exact K=2/M=2/cooldown=30 s transitions and episode counting reproduce.", "G9", "reports/fusion/alert_policy_tests.json", "ALERT_POLICY", "C"),
    req("R15", "EXPERIMENT", "Quality-aware comparison", "Compare identical ECG-only and quality-aware monitors under frozen deterministic degradations.", "Section 15.2; Appendix A E08", "T016", "evaluation/context_alerts.py;experiments/E08.yaml", "Paired clean/degraded deterministic replay with frozen seeds.", "Report excess episodes/hour, chattering, recheck, suppression, and reference-state preservation without sensitivity claims.", "G9", "reports/quality_aware_alert_robustness/report.json", "MULTIMODAL_CONTEXT", "C"),
    req("R16", "FEDERATED", "Eight simulated whole-patient sites", "Construct eight controlled sites from whole training patients only; never call them hospitals or institutions.", "Section 17.1", "T022", "federated/partitioning.py;manifests/clients/", "Client disjointness, partition-role, and patient-count audit.", "Each patient belongs to exactly one simulated training site; held-out patients are absent.", "G11;G12", "reports/federated/client_audit.json", "FEDERATED_CONFIGURATION", "C", claim="Synthetic research partitions, not real institutions."),
    req("R17", "FEDERATED", "Locked FedAvg", "Run the same MODEL_V1 with eight clients, 50 rounds, one local epoch, all clients/round, and sample-count weighted deltas.", "Section 17.2", "T022;T023", "federated/fedavg.py;configs/fedavg_v1.yaml", "Two-client analytical aggregation and round-log tests.", "Toy aggregate matches analytical mean and the IID run uses the locked budget.", "G11", "reports/federated/fl_iid/report.json", "FEDERATED_CONFIGURATION", "C"),
    req("R18", "FEDERATED", "Controlled non-IID conditions", "Evaluate IID, label, quantity, feature/noise, and combined conditions with whole-patient integrity and matched budgets.", "Section 18", "T024", "federated/partitioning.py;experiments/E10-E12.yaml", "Manifest invariants and config-difference audit.", "Only declared heterogeneity changes; patient pool/model/budgets remain matched.", "G12", "reports/federated/non_iid_report.json", "FEDERATED_CONFIGURATION", "C"),
    req("R19", "FEDERATED", "Matched FedProx", "FedProx changes only the local proximal objective; tune declared mu candidates on federated validation then freeze.", "Section 19", "T025", "federated/fedprox.py;configs/fedprox_v1.yaml", "mu=0 equivalence and matched-config tests.", "mu=0 matches FedAvg objective and final comparisons differ only by proximal objective.", "G13", "reports/federated/fedprox_report.json", "FEDERATED_CONFIGURATION", "C"),
    req("R20", "PRIVACY", "Narrow SecAgg+ claim", "Demonstrate configured Flower SecAgg+ server visibility and overhead only after FedAvg correctness.", "Section 20", "T026", "privacy/secagg.py;configs/secagg_v1.yaml", "Instrumented aggregate correctness, dropout, and server-visible-object audit.", "Server aggregation interface lacks individual clear updates; report avoids complete-privacy claims.", "G14", "reports/privacy_secagg/report.json", "PRIVACY_CONFIGURATION", "C", claim="Aggregation-visibility claim only; not complete privacy."),
    req("R21", "DEPLOYMENT", "Gateway deployment", "CPU inference on the local gateway is mandatory; ESP32 remains acquisition/timestamp device unless separately benchmarked.", "Section 21", "T027", "deployment/export.py;deployment/benchmark.py", "At least 1,000 warmed windows for size/RAM/p50/p95/throughput and prediction-delta tests.", "A deployable gateway artifact has measured resources and accuracy delta.", "G15", "reports/edge_benchmark/report.json", "DEPLOYMENT_ARTIFACT", "C"),
    req("R22", "WEARABLE", "WEARABLE_V1 domain validation", "Use real synchronized wearable sessions for engineering/domain validation only, without disease ground truth claims.", "Section 22", "T028;T031", "datasets/wearable.py;deployment/replay.py", "Canonical-contract, timing, quality, latency, and replay tests.", "At least one consent-compliant session passes the same path; no sensitivity/specificity is reported.", "G16;G21", "reports/wearable_validation/report.json", "WEARABLE_DATASET", "C", claim="Domain validation only, not clinical validation."),
    req("R23", "MODEL", "Integrated Gradients V1", "Use IG on pre-sigmoid logit with zero normalized-input baseline, 64 Gauss-Legendre steps, signed export, and normalized absolute overlay.", "Section 25", "T021", "evaluation/explainability.py;configs/explainability_v1.yaml", "Completeness delta, eval-mode, parameters, and fixed-case-selection tests.", "TP/TN/FP/FN cases follow predeclared selection and retain raw ECG/annotations.", "G17", "reports/explainability/case_report.json", "MODEL_V1", "C"),
    req("R24", "API", "Versioned safe API", "Expose /v1/infer-window with model/preprocess/contract/alert/calibration IDs, typed errors, and research-only probability semantics.", "Section 27", "T003;T029", "contracts/api_v1.schema.json;api/", "Schema/status/version-field contract tests.", "Valid/invalid/unusable inputs produce specified responses and no diagnosis string.", "G18", "api/openapi.json;reports/api/schema_tests.json", "API_CONTRACT", "B", claim="Probability for project target, not disease risk."),
    req("R25", "DASHBOARD", "Safe dashboard states", "Render the five specified monitoring/system states and research-only metadata without diagnostic wording.", "Section 28", "T030", "frontend/src/;contracts/dashboard_states_v1.json", "All-state UI mapping and prohibited-wording tests.", "State labels exactly follow the contract and show quality/version/calibration domain.", "G19", "reports/dashboard/state_tests.json", "DASHBOARD_CONTRACT", "B"),
    req("R26", "REPRODUCIBILITY", "Run identity and hashes", "Use locked environments, versioned configs/manifests, SHA-256 artifact identities, seeds, and common run manifests.", "Sections 30-31", "T001;T002;T032;T033;T036", "src/nhm/reproducibility.py;experiments/registry.csv;release/", "Clean-environment smoke, hash verification, and manifest schema tests.", "Every retained result traces to commit/config/data/split/model/seed and hashes verify.", "G20;G22", "reports/reproducibility/clean_run.json", "RELEASE_PACKAGE", "B"),
    req("R27", "GATE", "Blocking gates", "Treat G0-G22 as blocking checkpoints with artifacts, pass/fail criteria, recovery, and downstream blocks.", "Section 37", "T002;T035;T036", "manifests/gate_registry_v1.csv;scripts/audit_coverage_t002.py", "Registry completeness and release gate audit.", "Exactly G0-G22 exist; no gate is silently skipped or pre-passed.", "G0;G22", "release/gate_status.json", "RELEASE_PACKAGE", "C"),
    req("R28", "DEFINITION_OF_DONE", "Definition of Done and release evidence", "Satisfy every Section 44 clause and retain the Appendix B evidence package before final release.", "Section 44; Appendix B", "T033;T034;T035;T036", "manifests/evidence_registry_v1.csv;release/release_manifest.json", "Evidence existence/hash/claim audit.", "All mandatory evidence exists or an explicit approved fallback removes its claim.", "G22", "release/release_manifest.json", "RELEASE_PACKAGE", "C"),
]

# Extension convention: decimal children retain the R01-R28 parent; CB01-CB06 are
# explicit cross-cutting claim boundaries requested by the T002 authority.
REQUIREMENTS.extend(
    [
        req("R01.1", "LABEL_POLICY", "Target eligibility", "Positive windows contain at least one mapped S/V/F and no Q/unknown; negatives contain only mapped N; paced/unmapped/Q, fewer than five mapped beats, and UNUSABLE training windows are excluded.", "Section 9.1", "T007;T010", "datasets/labels.py;contracts/LABEL_SCHEMA_V1.md", "Boundary fixtures for positive, negative, every exclusion, and annotation interval edges.", "Every fixture receives the exact eligible label or exclusion reason.", "G4;G6", "reports/labels/window_target_tests.json", "LABEL_MAPPING", "C", parent="R01"),
        req("R01.2", "CLAIM_BOUNDARY", "Descriptive output", "Model probability describes the observed project window target; it is neither a beat-classifier output nor disease/arrhythmia probability and is not a future forecast.", "Sections 9.3-9.4", "T007;T029;T030;T034", "contracts/LABEL_SCHEMA_V1.md;contracts/api_v1.schema.json", "API/UI/report prohibited-claim audit.", "All exposed text identifies an observed-window research target and right-edge timestamp.", "G4;G18;G19;G22", "reports/claims/output_semantics.json", "RELEASE_PACKAGE", "C", parent="R01", claim="No diagnosis or future-risk interpretation."),
        req("R03.1", "DATASET_POLICY", "No channel fallback", "Exclude records missing the locked channel before split/evaluation; never select a fallback lead based on performance.", "Section 6.2", "T006;T020", "datasets/channel_policy.py;manifests/datasets/", "Missing-channel fixtures and manifest timing audit.", "Every exclusion is logged before downstream work and no alternate lead enters core results.", "G3;G10", "manifests/datasets/channel_exclusions.csv", "DATASET_VERSIONS", "C", parent="R03"),
        req("R04.1", "LEAKAGE_INVARIANT", "Partition role discipline", "Train fits weights/scalers; validation selects; calibration calibrates/thresholds; internal and external tests never tune.", "Section 11.1", "T008;T011;T012;T017;T018;T020", "manifests/splits/;training/;evaluation/", "Configuration-provenance and partition-access audit.", "No held-out partition influences training, selection, preprocessing, calibration, or threshold.", "G5;G10", "reports/splits/partition_role_audit.json", "PATIENT_SPLIT", "C", parent="R04"),
        req("R04.2", "STATISTICS", "Patient is statistical unit", "Show eligible patient counts beside window counts for every split/site; overlapping windows never imply independent n.", "Section 11.1", "T008;T018;T020;T022", "evaluation/reporting.py;manifests/splits/;manifests/clients/", "Report-schema assertion for patient and window counts.", "Every evaluation/client report exposes patient counts and does not treat windows as independent sample size.", "G5;G10;G12", "reports/evaluation/sample_size_audit.json", "INTERNAL_TEST", "C", parent="R04"),
        req("R05.1", "PREPROCESSING", "Train-fit normalization and features", "Per-window CNN normalization uses only that window; feature scalers fit on training only; no whole-record or full-dataset fitting.", "Section 8", "T010;T011", "preprocessing/normalize.py;features/ecg.py", "Fit-scope and future-append tests.", "Held-out/future modifications cannot change fitted transforms used for earlier/training-derived outputs.", "G6;G7", "reports/preprocessing/fit_scope_tests.json", "PREPROCESSING", "C", parent="R05"),
        req("R06.1", "DATA_CONTRACT", "Explicit missingness", "Represent missingness with null, validity/quality, and gap_mask fields; UNUSABLE suppresses physiological alerts and returns RECHECK_SENSOR.", "Sections 5.2, 8.1, and 40 item 17", "T003;T009;T010;T015;T029", "contracts/sample_schema_v1.json;preprocessing/quality.py", "Schema and end-to-end gap/state fixtures.", "Missingness is never silently imputed and runtime behavior follows quality state.", "G1;G6;G9;G18", "reports/contracts/missingness_tests.json", "HARDWARE_DATA_CONTRACT", "B", parent="R06"),
        req("R08.1", "MODEL", "Training and seed policy", "Use AdamW and locked hyperparameters; primary seed 20260927 and robustness seeds 20260928/20260929 cannot become selection hyperparameters.", "Section 13.2", "T012", "configs/model_v1.yaml;training/centralized.py", "Config equality and experiment-registry provenance tests.", "Release checkpoint uses predeclared selection and all seed results are reported without seed cherry-picking.", "G8", "reports/model/model_selection.json", "MODEL_V1", "C", parent="R08"),
        req("R09.1", "CLAIM_BOUNDARY", "Source-domain calibration only", "Expose calibration_domain=MIT-BIH-v1.0.0, calibration patient count, and uncertainty; never imply INCART/wearable/clinical calibration.", "Section 24", "T017;T029;T030;T034", "contracts/api_v1.schema.json;frontend/src/", "API/UI/report claim and required-field tests.", "Every calibrated probability carries source domain, patient count, and calibration ID.", "G10;G18;G19;G22", "reports/calibration/claim_audit.json", "CALIBRATION", "C", parent="R09", claim="MIT-BIH source-domain calibration only."),
        req("R10.1", "STATISTICS", "Pooled and paired metric rules", "Within each patient-cluster bootstrap replicate recompute pooled AUPRC/AUROC/F1/sensitivity/specificity; pair model comparisons on identical sampled patient IDs and do not average per-patient AUPRC.", "Section 23.3", "T018;T020;T025", "evaluation/bootstrap.py;evaluation/comparison.py", "Known clustered fixtures and identical-resample assertions.", "Metrics and paired differences reproduce the specified clustered computation with zero_division=0 for patient F1.", "G10;G13", "reports/evaluation/statistics_tests.json", "INTERNAL_TEST", "C", parent="R10"),
        req("R13.1", "DATASET_POLICY", "BIDMC engineering role", "Use BIDMC only for synchronization, processing, rate agreement, missingness, quality, and failure behavior; document critical-care mismatch.", "Sections 6 and 14.1", "T013;T014", "datasets/bidmc.py;reports/bidmc_multimodal_engineering/", "Dataset-role and report-claim audit.", "No BIDMC result is presented as supervised AAMI-SVF predictive evidence.", "G9", "reports/bidmc_multimodal_engineering/report.json", "MULTIMODAL_CONTEXT", "C", parent="R13"),
        req("R14.1", "ALERTING", "Quality-aware episode behavior", "DEGRADED may show POSSIBLE_PATTERN but cannot open; UNUSABLE clears confirmation and pauses counting; context absence preserves valid ECG result.", "Sections 15-15.1", "T014;T015", "fusion/context.py;fusion/alert_policy.py", "Exhaustive scripted transition table.", "All specified quality/context combinations produce the exact monitoring state and counter behavior.", "G9", "reports/fusion/state_table_tests.json", "ALERT_POLICY", "C", parent="R14"),
        req("R15.1", "STATISTICS", "Episode metric definitions", "Count open transitions per usable hour, excess alerts against aligned reference, state transitions excluding start/stop, recheck rate, and suppression rate exactly as defined.", "Section 15.1", "T015;T016", "evaluation/context_alerts.py", "Hand-computed sequence fixtures.", "Computed episode metrics exactly match reference sequences and overlapping positive windows count once.", "G9", "reports/quality_aware_alert_robustness/metric_tests.json", "MULTIMODAL_CONTEXT", "C", parent="R15"),
        req("R16.1", "CLAIM_BOUNDARY", "Federated sample-size disclosure", "Report patients per site and describe the eight-site design as a protocol/heterogeneity simulation, not institutional deployment.", "Section 17.1", "T022;T023;T024;T025;T034", "evaluation/federated_reporting.py;docs/", "Terminology and report-schema audit.", "All FL outputs show patient counts and contain no hospital/institution claims.", "G11;G12;G13;G22", "reports/federated/claim_audit.json", "FEDERATED_CONFIGURATION", "C", parent="R16", claim="Synthetic sites only."),
        req("R17.1", "FEDERATED", "Federated evaluation discipline", "Use frozen validation for development and test only after FL configuration freeze; store complete round logs and best-validation checkpoint.", "Section 17.2", "T023;T024;T025", "federated/server.py;experiments/", "Partition-access and round-log completeness audit.", "No test feedback alters FL configuration and every round/config/checkpoint is traceable.", "G11;G12;G13", "reports/federated/round_audit.json", "FEDERATED_CONFIGURATION", "C", parent="R17"),
        req("R18.1", "LEAKAGE_INVARIANT", "Noise skew training only", "Feature/noise skew applies fixed NSTDB regimes to whole client training streams while primary validation/test remain clean.", "Section 18", "T024", "federated/partitioning.py;configs/non_iid_v1.yaml", "Config and provenance assertions.", "Noise is confined to declared training clients and held-out primary data hashes remain unchanged.", "G12", "reports/federated/non_iid_audit.json", "FEDERATED_CONFIGURATION", "C", parent="R18"),
        req("R20.1", "CLAIM_BOUNDARY", "Privacy threat model", "SecAgg+ does not establish anonymity, final-model attack resistance, access control, transport security, or realistic institutional-scale security; DP is extension-only.", "Sections 20.1-20.2", "T026;T034", "privacy/THREAT_MODEL.md;reports/privacy_secagg/", "Report/README/API prohibited-claim audit.", "Only the implemented server update-visibility and measured-overhead claim remains.", "G14;G22", "reports/privacy_secagg/claim_audit.json", "PRIVACY_CONFIGURATION", "C", parent="R20", claim="No broad privacy claim."),
        req("R21.1", "DEPLOYMENT", "MCU claim requires separate evidence", "Any ESP32 inference claim requires exact-board conversion, memory, operator-support, and latency evidence and is not mandatory.", "Section 21", "T027;T034", "deployment/mcu_optional/;docs/limitations.md", "Release-claim audit conditioned on MCU artifact presence.", "Without a separate benchmark the release claims gateway inference only.", "G15;G22", "reports/edge_benchmark/claim_audit.json", "DEPLOYMENT_ARTIFACT", "C", parent="R21"),
        req("R22.1", "WEARABLE", "Wearable ethics and protocol", "Use consenting adults under applicable institution/supervisor process, do not induce pathology, and record activity/placement ground truth only.", "Section 22", "T028;T034", "docs/wearable_protocol.md;manifests/wearable/", "Consent/process checklist and manifest-field audit without storing private consent data in Git.", "Collection starts only after approval and sessions contain permitted states/provenance.", "G16;G22", "reports/wearable_validation/ethics_check.json", "WEARABLE_DATASET", "C", parent="R22"),
        req("R23.1", "CLAIM_BOUNDARY", "Explainability diagnostic only", "IG is an engineering diagnostic, not causal clinical explanation; case selection is predeclared rather than visually selected.", "Section 25", "T021;T034", "evaluation/explainability.py;docs/limitations.md", "Case-selection provenance and report-language audit.", "Saved explanations include convergence metadata, raw signal/annotations, and no causal claim.", "G17;G22", "reports/explainability/claim_audit.json", "MODEL_V1", "C", parent="R23"),
        req("R24.1", "API", "API error and shared-stream logic", "Return 400 for schema errors, 422 for unusable/incomplete windows, 500 only for server failure; WebSocket wraps the same schema and inference logic.", "Section 27.2", "T029", "api/;contracts/api_v1.schema.json", "Valid/invalid/unusable/server-failure and REST/WebSocket equivalence tests.", "Status codes and version fields are exact with no alternate streaming inference path.", "G18", "reports/api/contract_tests.json", "API_CONTRACT", "B", parent="R24"),
        req("R25.1", "DASHBOARD", "Persistent dashboard panels", "Show live waveforms, quality, episode state, technical metadata, and a clearly research-only probability/history panel with calibration_domain and alert_policy_id.", "Section 28", "T030", "frontend/src/", "Component/state snapshot and accessibility tests.", "All persistent panels and required identifiers render for every API state.", "G19", "reports/dashboard/panel_tests.json", "DASHBOARD_CONTRACT", "B", parent="R25"),
        req("R26.1", "DATASET_POLICY", "Versioned immutable data builds", "Record exact source URL/version/hash/license/download date; keep raw immutable; standardize separately; build windows only after patient split.", "Sections 7 and 30", "T005;T006;T008;T010;T032", "datasets/;manifests/datasets/;scripts/build_datasets.py", "Manifest schema, checksum, raw immutability, and build-order tests.", "A clean scripted build reproduces versioned manifests/caches without cross-partition windows.", "G2;G3;G5;G20", "reports/data/build_audit.json", "DATASET_VERSIONS", "C", parent="R26"),
        req("R26.2", "REPRODUCIBILITY", "Experiment identity", "Use NHM-{date}-{track}-{NNN}; record hypothesis, data/split/config/checkpoint, metric, status, seed, owner, and allowed conclusion.", "Section 31", "T002;T033", "manifests/experiment_registry_v1.csv;experiments/", "Registry schema, ID pattern, referential-integrity, and hash tests.", "Every core experiment is predeclared and traces to frozen dependencies and evidence.", "G20;G22", "reports/experiments/registry_audit.json", "RELEASE_PACKAGE", "B", parent="R26"),
        req("R27.1", "GATE", "Fallback does not hide failure", "Fallback cuts breadth before rigor; skipped/failed privacy or other claims are explicitly removed, never silently marked passed.", "Sections 39 and 44.1", "T034;T035;T036", "release/gate_status.json;docs/limitations.md", "Gate/fallback/claim consistency audit.", "Every non-PASS mandatory gate has an approved fallback and corresponding claim removal.", "G22", "release/fallback_audit.json", "RELEASE_PACKAGE", "C", parent="R27"),
        req("HW01", "DATA_CONTRACT", "Observed hardware semantics verification", "Resolve sample semantics, timestamp origin, rates, ADC characteristics, units/scaling, identity, packet integrity, synchronization, BPM and SpO2 provenance; all remain VERIFICATION_REQUIRED until measured.", "Sections 4-5 and 43.1", "T003;T004", "contracts/HARDWARE_DATA_CONTRACT_V1.md;firmware evidence", "Bench measurements, firmware/backend inspection, schema fixtures, timing/jitter and packet tests.", "G1 cannot pass until each required field has evidence or an explicit unavailable status/versioned limitation.", "G1", "reports/hardware/contract_verification.json", "HARDWARE_DATA_CONTRACT", "B", notes="Preserves OBSERVED_MONGODB_SCHEMA_V0 without assigning units or physiological meaning."),
        req("DC01", "DATA_CONTRACT", "Canonical session and waveform schemas", "Version participant/session/device/firmware/config/timestamp/sample/raw/derived/quality/provenance/missingness fields under HARDWARE_DATA_CONTRACT_V1.", "Sections 5.1-5.3", "T003;T004", "contracts/session_manifest_v1.schema.json;contracts/sample_schema_v1.json", "JSON Schema fixtures and backward-incompatible-change tests.", "All required fields/types/clock meanings are explicit and observed MongoDB V0 is not silently treated as canonical.", "G1", "reports/contracts/schema_tests.json", "HARDWARE_DATA_CONTRACT", "B"),
        req("DS01", "DATASET_POLICY", "Dataset role separation", "MIT-BIH is core, INCART external, NSTDB noise, BIDMC engineering, WEARABLE_V1 domain validation; PTB-XL is removed from executable v2.2 scope.", "Sections 6-6.1", "T002;T005;T006;T013;T019;T020;T028;T034", "manifests/datasets/;docs/claims.md", "Dataset-role registry and report-input audit.", "No result crosses its dataset's allowed conclusion and PTB-XL is absent from core execution configs.", "G2;G3;G22", "reports/data/dataset_role_audit.json", "DATASET_VERSIONS", "C"),
        req("SQ01", "DATA_CONTRACT", "Quality states", "Use VALID/DEGRADED/UNUSABLE; tune engineering thresholds on training/noise-development resources only; held-out tests cannot tune.", "Section 8.1", "T003;T010;T014", "contracts/quality_states_v1.json;configs/QUALITY_V1.yaml", "Hard-failure, threshold-provenance, and runtime-action tests.", "UNUSABLE suppresses physiological alert; DEGRADED lowers trust; thresholds have non-clinical provenance.", "G6;G9", "reports/quality/quality_tests.json", "PREPROCESSING", "C"),
        req("TEST01", "REPRODUCIBILITY", "Mandatory test matrix", "Implement all data, timing, windows, synchronization, causal preprocessing/resampling, quality, label, split, model, FL, privacy, API, episode, dashboard, reproducibility, and e2e tests.", "Section 29", "T004;T006;T007;T008;T009;T010;T012;T014;T015;T022;T025;T026;T029;T030;T031;T032", "tests/", "Full offline/unit/integration/leakage/e2e suite plus component gate reports.", "Every mandatory matrix row passes or blocks its named gate.", "G1;G3;G4;G5;G6;G8;G9;G11;G13;G14;G18;G19;G20;G21", "reports/test_report.json", "RELEASE_PACKAGE", "B"),
        req("REL01", "RELEASE", "Final evidence checklist", "Retain every Section 41 and Appendix B contract, manifest, audit, model, evaluation, FL, privacy, deployment, wearable, API/dashboard, test, reproduction, limitation, and viva artifact.", "Section 41; Appendix B", "T033;T034;T035;T036", "manifests/evidence_registry_v1.csv;release/release_manifest.json", "Existence, status, SHA-256, gate, and requirement linkage audit.", "Release manifest has every mandatory artifact/hash/gate/limitation and no fabricated future hash.", "G22", "release/release_manifest.json", "RELEASE_PACKAGE", "C"),
        req("CB01", "CLAIM_BOUNDARY", "Research prototype only", "The system is a research prototype, not diagnostic, clinical decision support, treatment advice, safety evidence, or clinical readiness.", "Document Control; Sections 2.3 and 9.3", "T001;T002;T024;T029;T030;T034;T036", "README.md;api/;frontend/;docs/claims.md", "Repository/API/UI/report prohibited-claim scan and human review.", "No committed or generated user-facing artifact makes a prohibited clinical claim.", "G0;G18;G19;G22", "reports/claims/clinical_boundary.json", "RELEASE_PACKAGE", "C", claim="Research-only; not diagnostic or clinical decision support."),
        req("CB02", "CLAIM_BOUNDARY", "Wearable engineering domain only", "Wearable validation lacks disease ground truth and cannot support clinical sensitivity/specificity or calibration claims.", "Sections 6 and 22", "T028;T034;T036", "reports/wearable_validation/;docs/claims.md", "Wearable report metric/wording audit.", "Only quality/timing/latency/output-distribution/domain compatibility conclusions appear.", "G16;G22", "reports/claims/wearable_boundary.json", "WEARABLE_DATASET", "C", claim="No wearable clinical validation claim."),
        req("CB03", "CLAIM_BOUNDARY", "Simulated FL sites", "Federated clients are synthetic research partitions and are never represented as real hospitals, clinics, institutions, or deployed populations.", "Section 17.1", "T022;T023;T024;T025;T026;T034;T036", "federated/;reports/federated/;docs/claims.md", "Terminology scan across code, schemas, logs, figures, API, and reports.", "All site labels and claims explicitly say simulated research partitions.", "G11;G12;G13;G14;G22", "reports/claims/fl_boundary.json", "FEDERATED_CONFIGURATION", "C", claim="No real-institution FL claim."),
        req("CB04", "CLAIM_BOUNDARY", "Scoped secure aggregation", "SecAgg+ supports only the implemented server aggregation-visibility claim, not complete privacy, anonymity, or all-attack protection.", "Sections 20.1-20.2", "T026;T034;T036", "privacy/THREAT_MODEL.md;reports/privacy_secagg/", "Privacy-claim checklist and server-object instrumentation.", "Every privacy statement is bounded by configured simulation evidence and limitations.", "G14;G22", "reports/claims/privacy_boundary.json", "PRIVACY_CONFIGURATION", "C", claim="No broad privacy claim."),
        req("CB05", "CLAIM_BOUNDARY", "No learned multimodal arrhythmia", "PPG/SpO2/HR provide deterministic quality/context, synchronization, and operational robustness—not learned arrhythmia prediction.", "Sections 14-15.2", "T013;T014;T015;T016;T034;T036", "fusion/;reports/quality_aware_alert_robustness/", "Model-input/schema and report-claim audit.", "No PPG/SpO2/HR feature enters the learned AAMI-SVF classifier and no predictive-gain claim is made.", "G9;G22", "reports/claims/multimodal_boundary.json", "MULTIMODAL_CONTEXT", "C", claim="Deterministic context only."),
        req("CB06", "CLAIM_BOUNDARY", "Source calibration boundary", "Calibration is MIT-BIH source-domain under small-patient uncertainty and is not wearable-domain or clinical calibration.", "Section 24", "T017;T029;T030;T034;T036", "reports/calibration/;api/;frontend/", "Required metadata and prohibited-claim tests.", "Calibration domain, patient count, and ID accompany probability everywhere.", "G10;G18;G19;G22", "reports/claims/calibration_boundary.json", "CALIBRATION", "C", claim="No wearable/clinical calibration claim."),
    ]
)

# Semantic ownership reconciled against the execution plan's Section 3 coverage matrix,
# Section 22 task packets, and v2.2. R01-R28 are checked against the source-extracted map.
REQUIREMENT_TASK_OWNERS = {
    "R01": "T008;T013",
    "R02": "T013",
    "R03": "T006;T007",
    "R04": "T009;T010",
    "R05": "T011;T012",
    "R06": "T012",
    "R07": "T014",
    "R08": "T015;T016",
    "R09": "T017",
    "R10": "T018",
    "R11": "T019",
    "R12": "T020",
    "R13": "T021;T022",
    "R14": "T022",
    "R15": "T023",
    "R16": "T025",
    "R17": "T025",
    "R18": "T026",
    "R19": "T027",
    "R20": "T028",
    "R21": "T029",
    "R22": "T004;T030",
    "R23": "T031",
    "R24": "T032",
    "R25": "T033",
    "R26": "T001;T002;T035;T036",
    "R27": ";".join(f"T{number:03d}" for number in range(1, 37)),
    "R28": "T036",
    "R01.1": "T008;T013",
    "R01.2": "T008;T013;T032;T033;T036",
    "R03.1": "T006;T007;T020",
    "R04.1": "T009;T010;T014;T015;T017;T018;T020",
    "R04.2": "T009;T010;T018;T020;T025",
    "R05.1": "T012;T013;T014;T015",
    "R06.1": "T003;T012;T013;T022;T032",
    "R08.1": "T015;T016",
    "R09.1": "T017;T032;T033;T036",
    "R10.1": "T018;T020;T027",
    "R13.1": "T007;T021",
    "R14.1": "T013;T021;T022",
    "R15.1": "T022;T023",
    "R16.1": "T025;T026;T027;T028;T036",
    "R17.1": "T025;T026;T027",
    "R18.1": "T026",
    "R20.1": "T028;T036",
    "R21.1": "T029;T036",
    "R22.1": "T004;T030;T036",
    "R23.1": "T031;T036",
    "R24.1": "T032",
    "R25.1": "T033",
    "R26.1": "T006;T007;T009;T013;T035",
    "R26.2": "T002;T035;T036",
    "R27.1": "T035;T036",
    "HW01": "T003;T004",
    "DC01": "T003;T004",
    "DS01": "T002;T006;T007;T019;T020;T021;T030;T036",
    "SQ01": "T003;T012;T013;T021;T022",
    "TEST01": "T004;T006;T007;T008;T009;T010;T011;T012;T013;T014;T015;T016;T018;T021;T022;T024;T025;T027;T028;T029;T030;T031;T032;T033;T034;T035",
    "REL01": "T035;T036",
    "CB01": "T001;T002;T023;T025;T028;T032;T033;T036",
    "CB02": "T030;T034;T036",
    "CB03": "T025;T026;T027;T028;T036",
    "CB04": "T028;T036",
    "CB05": "T021;T022;T023;T036",
    "CB06": "T017;T032;T033;T036",
    "R28.1": "T035;T036",
    "R28.2": "T003;T006;T007;T008;T009;T016;T017;T025;T029;T032;T036",
    "R28.3": "T035",
    "R28.4": "T018;T019;T020",
    "R28.5": "T013;T021;T022;T023",
    "R28.6": "T024;T025;T026;T027",
    "R28.7": "T028;T036",
    "R28.8": "T029;T034",
    "R28.9": "T030;T034",
    "R28.10": "T032;T033;T034",
    "R28.11": "T035;T036",
    "R28.12": "T036",
    "R10.2": "T018;T019;T020;T027",
    "R23.2": "T031",
    "R26.3": "T006;T009;T025;T030;T035;T036",
    "OOS01": "T002;T036",
    "OOS02": "T002;T023;T036",
    "OOS03": "T002;T028;T036",
    "OOS04": "T002;T029;T036",
}

for index, (text, tasks, gates, evidence) in enumerate(
    [
        ("G0-G22 are PASS or explicitly downgraded under documented fallback; no gate is silently skipped.", "T035;T036", "G22", "release/gate_status.json"),
        ("Dataset, split, client, preprocessing, model, calibration, API, and release artifacts have immutable IDs/hashes.", "T005;T008;T022;T032;T033;T036", "G20;G22", "release/release_manifest.json"),
        ("A clean environment runs tests and the CPU smoke pipeline from documented commands.", "T032", "G20", "reports/reproducibility/clean_run.json"),
        ("MODEL_V1 has internal, noise, and external evaluation with patient-level uncertainty.", "T018;T019;T020", "G10", "reports/evaluation/model_v1_evidence.json"),
        ("PPG/SpO2/HR, synchronization, quality, episode, and quality-aware comparison pass without learned multimodal claims.", "T013;T014;T015;T016", "G9", "reports/quality_aware_alert_robustness/report.json"),
        ("FedAvg, non-IID, and matched FedProx are reproducible with whole-patient client integrity.", "T022;T023;T024;T025", "G11;G12;G13", "reports/federated/final_summary.json"),
        ("SecAgg+ passes correctness or its implemented-privacy claim is explicitly removed under emergency fallback.", "T026;T034;T036", "G14;G22", "reports/privacy_secagg/report.json"),
        ("Gateway size, memory, and latency are measured; any ESP32 inference claim has separate exact-board evidence.", "T027;T034", "G15", "reports/edge_benchmark/report.json"),
        ("At least one real synchronized wearable session passes the canonical path and replay/live demo.", "T028;T031", "G16;G21", "reports/wearable_validation/report.json"),
        ("API/dashboard wording is research-only and exposes quality/model/calibration/policy versions.", "T029;T030;T034", "G18;G19", "reports/application/claim_audit.json"),
        ("Final repository contains evidence checklist, experiment registry, limitations, and viva defense map.", "T033;T034;T036", "G22", "release/release_manifest.json"),
        ("The team distinguishes system scope/non-scope, source facts, engineering decisions, experiments, and remaining risks.", "T034;T036", "G22", "docs/viva_defense_map.md"),
    ],
    start=1,
):
    REQUIREMENTS.append(
        req(
            f"R28.{index}",
            "DEFINITION_OF_DONE",
            f"Definition of Done clause {index}",
            text,
            f"Section 44 item {index}",
            tasks,
            "release/;reports/;docs/",
            "Release evidence and gate consistency audit.",
            text,
            gates,
            evidence,
            "RELEASE_PACKAGE",
            "C",
            parent="R28",
        )
    )

# Added by the manual section-by-section audit after the first structural pass.
REQUIREMENTS.extend(
    [
        req("R10.2", "STATISTICS", "Locked metric set", "Use AUPRC as primary threshold-independent metric and report AUROC, F1, sensitivity, specificity, precision, confusion matrix, alert episodes/hour, and patient-macro F1 as applicable.", "Section 23.1", "T018;T019;T020;T025", "evaluation/metrics.py;evaluation/reporting.py", "Known-score fixtures, threshold provenance, and report-schema tests.", "Each experiment reports its predeclared metrics with the frozen threshold and correct statistical unit.", "G10;G13", "reports/evaluation/metric_tests.json", "INTERNAL_TEST", "C", parent="R10", notes="Added during the manual second audit; metric coverage was implicit in the first draft."),
        req("R23.2", "EXPERIMENT", "Required error-analysis slices", "Analyze patient, S/V/F composition, quality, noise/SNR, training-defined HR bins, dataset, threshold region, and wearable output/quality-only slices without identity disclosure.", "Section 26", "T021", "evaluation/error_analysis.py;reports/error_analysis/", "Slice-definition, identity-redaction, and training-bin provenance tests.", "All specified slices are reported; wearable slice contains no labeled-accuracy claim.", "G17;G22", "reports/error_analysis/report.json", "MODEL_V1", "C", parent="R23", notes="Added during the manual second audit."),
        req("R26.3", "REPRODUCIBILITY", "Clean builds and private-data policy", "Public builds are scripted from URLs/checksums; private wearable raw data is never committed; split/client manifests have no manual spreadsheet edits; documented one-command test/build/train/FL/evaluate surfaces exist.", "Section 30 items 3-6", "T005;T008;T022;T028;T032;T036", "scripts/;Makefile;.gitignore;manifests/", "Clean checkout command tests, Git tracked-file scan, and generated-manifest provenance audit.", "A clean CPU environment reproduces smoke/evidence without MongoDB, private data, or undocumented manual steps.", "G20;G22", "reports/reproducibility/clean_run.json", "RELEASE_PACKAGE", "B", parent="R26", notes="Added during the manual second audit."),
        req("OOS01", "DATASET_POLICY", "PTB-XL excluded", "PTB-XL is removed from executable v2.2 core scope and cannot become a core dependency without a versioned Class C revision.", "Sections 1.1 and 6.1", "T002;T034", "manifests/requirements_v22.csv;docs/claims.md", "Core config/input scan.", "No core experiment or gate consumes PTB-XL.", "G0;G22", "reports/claims/dataset_scope.json", "SOURCE_AUTHORITY", "C", status="OUT_OF_SCOPE_BY_SPEC", mandatory="FALSE", claim="PTB-XL not in executable core scope.", notes="Existing local files are preserved but not consumed."),
        req("OOS02", "MULTIMODAL", "Learned multimodal classifier excluded", "A learned ECG+PPG+SpO2/HR AAMI-SVF classifier is out of scope because compatible supervised labels do not exist.", "Sections 1.1 and 14-15", "T002;T034", "manifests/requirements_v22.csv;docs/claims.md", "Model-input and experiment-registry scan.", "No planned or released learned primary classifier consumes context modalities.", "G9;G22", "reports/claims/multimodal_boundary.json", "SOURCE_AUTHORITY", "C", status="OUT_OF_SCOPE_BY_SPEC", mandatory="FALSE", claim="No learned multimodal arrhythmia fusion."),
        req("OOS03", "PRIVACY", "Differential privacy extension only", "Differential privacy is outside Level-1 mandatory scope and may be added only as a separately versioned extension after core gates.", "Section 20.2", "T002;T034", "manifests/requirements_v22.csv;docs/claims.md", "Privacy configuration and claim scan.", "No mandatory gate or core conclusion depends on DP.", "G14;G22", "reports/claims/privacy_boundary.json", "SOURCE_AUTHORITY", "C", status="OUT_OF_SCOPE_BY_SPEC", mandatory="FALSE", claim="No unimplemented DP claim."),
        req("OOS04", "DEPLOYMENT", "Mandatory MCU inference excluded", "ESP32 inference is not required; it may be claimed only after separately versioned exact-board evidence.", "Section 21", "T002;T027;T034", "manifests/requirements_v22.csv;deployment/mcu_optional/", "Deployment registry and release-claim scan.", "Mandatory deployment remains gateway and no MCU claim exists without separate benchmark.", "G15;G22", "reports/edge_benchmark/claim_audit.json", "SOURCE_AUTHORITY", "C", status="OUT_OF_SCOPE_BY_SPEC", mandatory="FALSE", claim="No mandatory ESP32 inference claim."),
    ]
)

if set(REQUIREMENT_TASK_OWNERS) != {row["requirement_id"] for row in REQUIREMENTS}:
    raise RuntimeError("semantic task-owner map must cover every requirement row exactly")
for requirement in REQUIREMENTS:
    requirement["implementation_tasks"] = REQUIREMENT_TASK_OWNERS[requirement["requirement_id"]]

GATE_FIELDS = [
    "gate_id", "gate_name", "purpose", "prerequisite_tasks", "required_requirements",
    "required_tests", "required_artifacts", "pass_criteria", "fail_criteria",
    "recovery_action", "blocks_tasks", "status", "evidence_path",
]


def gate(
    gate_id: str,
    name: str,
    purpose: str,
    tasks: str,
    requirements: str,
    tests: str,
    artifacts: str,
    passed: str,
    failed: str,
    recovery: str,
    blocks: str,
    *,
    status: str = "NOT_STARTED",
    evidence: str = "",
) -> dict[str, str]:
    return dict(
        zip(
            GATE_FIELDS,
            [gate_id, name, purpose, tasks, requirements, tests, artifacts, passed, failed,
             recovery, blocks, status, evidence],
            strict=True,
        )
    )


GATES = [
    gate("G0", "Scope Freeze", "Freeze task, research questions, authority, and claim boundary.", "T001;T002", "R26;R27;CB01", "T001 closure and T002 registry audits", "reports/t001/closure_verification.json;manifests/requirements_v22.csv", "Task and claim boundary explicit; closure evidence PASS.", "Authority/scope ambiguity or closure not PASS.", "Stop downstream implementation and repair source/coverage evidence.", "T003;T004;T005;T006;T007;T008;T009;T010;T011;T012;T013;T014;T015;T016;T017;T018;T019;T020;T021;T022;T023;T024;T025;T026;T027;T028;T029;T030;T031;T032;T033;T034;T035;T036", status="PASS", evidence="reports/t001/closure_verification.json"),
    gate("G1", "Hardware/Data Contract", "Freeze canonical hardware/data semantics and firmware schema.", "T003;T004", "HW01;DC01;R06.1", "Schema fixtures; bench timing/ADC/packet verification", "contracts/HARDWARE_DATA_CONTRACT_V1.md;reports/hardware/contract_verification.json", "All required fields, types, clocks, provenance, and verified/unknown semantics defined.", "Sensor semantics remain unknown without explicit evidence/status.", "Bench hardware and inspect firmware/backend; version the contract.", "T005;T013;T028", evidence="reports/hardware/contract_verification.json"),
    gate("G2", "Dataset Acquisition", "Verify exact public dataset versions and immutable provenance.", "T005", "R26.1;DS01", "Checksum/license/parse smoke tests", "manifests/datasets/", "Exact declared versions download/parse with hashes and licenses.", "Missing, corrupt, or mis-versioned source.", "Redownload or repair manifest; do not proceed on uncertain source.", "T006", status="PASS", evidence="reports/data/acquisition_audit.json"),
    gate("G3", "Dataset Validation", "Validate records, annotations, identifiers, and locked channel policy.", "T006", "R03;R03.1;R26.1;DS01", "Record/schema/channel/duplicate/symbol-census tests", "reports/data/validation_report.json;manifests/datasets/channel_exclusions.csv", "All expected fields and annotation/channel checks pass or documented version exception is approved.", "Unexpected fields/counts or untracked exclusions.", "Block labels/splits; repair validation or source version.", "T007;T008", status="PASS", evidence="reports/data/validation_report.json"),
    gate("G4", "Label Freeze", "Freeze AAMI_SVF_WINDOW_V1 and shared AAMI_SVF_MAP_V1.", "T007", "R01;R01.1;R01.2", "Complete allowlist/unknown/paced/non-beat/window eligibility tests", "contracts/LABEL_SCHEMA_V1.md;reports/labels/label_audit.json", "Symbol mapping and target tests pass for both source datasets.", "Any ambiguous, inconsistent, or silently coerced target symbol.", "Revise/version mapping before any training and regenerate dependent artifacts.", "T008;T009;T010;T011;T012", status="PASS", evidence="reports/labels/label_audit.json"),
    gate("G5", "Split/Leakage Audit", "Freeze patient partitions before windows/models.", "T008", "R04;R04.1;R04.2", "Disjoint participants; 201/202 grouping; post-split window build audit", "manifests/splits/MITDB_SPLIT_V1.csv;reports/splits/split_audit.json", "Zero patient overlap; 201/202 grouped; patient counts reported.", "Any leakage, role violation, or result-driven regeneration.", "Regenerate before training and invalidate all dependent runs.", "T009;T010;T011;T012;T022", status="PASS", evidence="reports/splits/split_audit.json"),
    gate("G6", "Preprocessing Pass", "Prove causal preprocessing, resampling, gaps, windows, and quality.", "T009;T010", "R02;R05;R05.1;R06;R06.1;SQ01", "Future-append; impulse; chunk equivalence; gap; window; hard-quality tests", "reports/preprocessing/causality_tests.json;reports/preprocessing/gap_tests.json", "All future-append and chunk-equivalence tests pass; gap/window/quality contracts exact.", "Any future dependence, state mismatch, or gap/window contract defect.", "Replace/version the transform and invalidate caches/downstream runs.", "T011;T012", status="PASS", evidence="reports/preprocessing/causality_tests.json"),
    gate("G7", "Baseline Pass", "Establish pipeline sanity with locked trivial/classical baselines.", "T011", "R07", "Training-only majority and feature fit-scope tests", "reports/baselines/baseline_report.json", "Pipeline produces reproducible metrics and majority predictor is train-derived.", "Pipeline failure, leakage, or held-out prevalence selection.", "Debug data/features/model without using test outcomes.", "T012", evidence="reports/baselines/baseline_report.json"),
    gate("G8", "ECG Model Lock", "Freeze reproducible MODEL_V1 architecture/checkpoint/config.", "T012", "R08;R08.1", "Shape; fixed-vector logits; seed/config/checkpoint determinism", "checkpoints/MODEL_V1.manifest.json", "Validation acceptance and test-vector reproduction pass; checkpoint hash stored.", "Unstable model, interface drift, or unreproducible logits.", "Simplify/tune only on train/validation, then version and re-gate.", "T016;T017;T022;T027", evidence="checkpoints/MODEL_V1.manifest.json"),
    gate("G9", "Multimodal Context Pass", "Validate deterministic context, episode policy, and controlled quality-aware comparison.", "T013;T014;T015;T016", "R13;R13.1;R14;R14.1;R15;R15.1;CB05", "Synchronization; quality; state table; episode; deterministic perturbation tests", "reports/bidmc_multimodal_engineering/report.json;reports/quality_aware_alert_robustness/report.json", "Sync/quality/episode tests pass and controlled comparison reproduces without learned-fusion claim.", "False multimodal claim, undefined episode counting, or nondeterministic comparison.", "Fix context/episode experiment; never invent predictive labels.", "T030;T033", evidence="reports/quality_aware_alert_robustness/report.json"),
    gate("G10", "Central Eval Freeze", "Freeze calibration, internal, noise, and external evidence without post-test tuning.", "T017;T018;T019;T020", "R09;R09.1;R10;R10.1;R11;R12;CB06", "Calibration provenance; clustered statistics; checkpoint/threshold/no-adaptation audits", "reports/calibration/calibration.json;reports/internal_test/report.json;reports/noise_robustness/report.json;reports/external_incart/report.json", "Checkpoint/threshold locked and evaluations use declared patient-level uncertainty.", "Any post-test tuning, window CI, lead/map drift, or external adaptation.", "Version bump and new untouched-test policy; never overwrite prior evidence.", "T021;T033", evidence="reports/internal_test/report.json"),
    gate("G11", "FedAvg Pass", "Validate analytical aggregation and frozen IID FedAvg baseline.", "T022;T023", "R16;R16.1;R17;R17.1;CB03", "Toy weighted mean; client disjointness; round/config audit", "reports/federated/fl_iid/report.json", "Toy equivalence and stable locked-budget IID run pass.", "Aggregation/serialization/patient-contamination defect.", "Block FL extensions; repair toy and client-manifest logic first.", "T024;T025;T026", evidence="reports/federated/fl_iid/report.json"),
    gate("G12", "Non-IID Pass", "Validate controlled heterogeneity with patient integrity and matched budgets.", "T024", "R18;R18.1;R16.1", "Client manifest and config-difference audit", "reports/federated/non_iid_report.json", "Patient integrity and declared matched-budget construction pass.", "Confounded clients, cross-site patients, or hidden budget changes.", "Rebuild/version manifests and rerun affected experiments.", "T025", evidence="reports/federated/non_iid_report.json"),
    gate("G13", "FedProx Pass", "Freeze a matched FedAvg/FedProx comparison.", "T025", "R19;R10.1", "mu=0 equivalence; config-match; paired statistic tests", "reports/federated/fedprox_report.json", "Only local objective differs and all comparison settings remain matched.", "Unmatched setting, failed mu=0 equivalence, or test-driven tuning.", "Repair objective/config, retune only on federated validation, rerun.", "T033", evidence="reports/federated/fedprox_report.json"),
    gate("G14", "Privacy Pass", "Validate scoped SecAgg+ correctness, visibility, and overhead.", "T026", "R20;R20.1;CB04", "Aggregate correctness; dropout; server-visible objects; claim audit", "reports/privacy_secagg/report.json", "Individual clear update is absent at server aggregation interface and limitations are explicit.", "Privacy claim unsupported or aggregate incorrect.", "Fix reference workflow or remove implemented-privacy claim under fallback.", "T033;T034", evidence="reports/privacy_secagg/report.json"),
    gate("G15", "Edge Benchmark", "Measure mandatory gateway feasibility.", "T027", "R21;R21.1", "Prediction equivalence and >=1000-window resource benchmark", "reports/edge_benchmark/report.json", "Model size, parameters, peak RAM, p50/p95 latency, and throughput measured.", "No deployable gateway artifact or unexplained prediction delta.", "Retain research model on gateway Python; omit unsupported optimization.", "T028;T029;T031", evidence="reports/edge_benchmark/report.json"),
    gate("G16", "Wearable Validation", "Prove same canonical path accepts real synchronized hardware data.", "T028", "R22;R22.1;CB02", "Contract, clock/sync, quality, dropout, latency, and replay tests", "reports/wearable_validation/report.json", "Same contract/pipeline accepts consent-compliant wearable session with domain-only claims.", "Hidden separate pipeline, unverified semantics, or clinical efficacy claim.", "Fix integration/contract or reduce claim; do not fabricate labels.", "T031;T033", evidence="reports/wearable_validation/report.json"),
    gate("G17", "Explainability", "Validate EXPLAINABILITY_V1 diagnostics.", "T021", "R23;R23.1", "Method parameter, case-selection, and completeness-delta tests", "reports/explainability/case_report.json", "Zero baseline, 64-step Gauss-Legendre, signed/absolute outputs, convergence and predeclared cases saved.", "Method/parameter drift, attractive-case selection, or causal clinical wording.", "Fix implementation or omit unstable method from core UI.", "T034", evidence="reports/explainability/case_report.json"),
    gate("G18", "API Pass", "Freeze versioned research-only runtime schema.", "T029", "R24;R24.1;CB01;CB06", "Schema, status code, version fields, REST/WebSocket equivalence", "api/openapi.json;reports/api/contract_tests.json", "Versioned outputs/errors and research semantics pass.", "Schema drift, missing IDs, diagnosis string, or alternate stream logic.", "Fix before dashboard integration.", "T030;T031", evidence="reports/api/contract_tests.json"),
    gate("G19", "Dashboard Pass", "Validate state mapping and safe wording.", "T030", "R25;R25.1;CB01;CB06", "All-state mapping, required panels/metadata, prohibited-wording tests", "reports/dashboard/state_tests.json", "UI state wording exactly matches contract and exposes versions/domain.", "Diagnostic wording or state/schema mismatch.", "Block release; fix strings/state consumption.", "T031;T035", evidence="reports/dashboard/state_tests.json"),
    gate("G20", "Reproducibility", "Prove clean supported-runtime recreation and artifact identity.", "T032;T033", "R26;R26.1;R26.2;TEST01", "Clean environment, lock, command, manifest, seed, and hash verification", "reports/reproducibility/clean_run.json", "Smoke run reproduces artifact IDs/metrics within declared tolerance without manual dependency.", "Missing lock/config/seed/hash or manual reconstruction.", "Lock environment and regenerate evidence through scripts.", "T035;T036", evidence="reports/reproducibility/clean_run.json"),
    gate("G21", "Final Integration", "Validate recorded stream through dashboard and evidence logs.", "T031;T033;T034", "R22;R24;R25;R28.9;R28.10", "Recorded wearable replay end-to-end and log/version assertions", "reports/integration/e2e_replay.json", "Recorded stream -> quality -> inference -> fusion -> API -> dashboard works continuously with logs.", "Integration failure, hidden manual step, or unsafe state.", "Use documented fallback level and repair the failing boundary.", "T035;T036", evidence="reports/integration/e2e_replay.json"),
    gate("G22", "Final Release", "Freeze complete reproducible evidence package and defensible claims.", "T035;T036", "R27;R27.1;R28;REL01;CB01;CB02;CB03;CB04;CB05;CB06", "Release manifest existence/hash/gate/limitation/claim audit", "release/release_manifest.json", "All mandatory artifacts present and hashed; gate/fallback/limitations consistent.", "Missing evidence, silent gate skip, or unsupported claim.", "Do not submit as complete; regenerate evidence or invoke explicit fallback.", "", evidence="release/release_manifest.json"),
]

GATE_TASK_OWNERS = {
    "G0": "T001;T002",
    "G1": "T003;T004",
    "G2": "T006;T007",
    "G3": "T006;T007",
    "G4": "T008",
    "G5": "T009;T010",
    "G6": "T010;T011;T012;T013",
    "G7": "T014",
    "G8": "T015;T016",
    "G9": "T021;T022;T023",
    "G10": "T017;T018",
    "G11": "T024;T025",
    "G12": "T026",
    "G13": "T027",
    "G14": "T028",
    "G15": "T029",
    "G16": "T030",
    "G17": "T031",
    "G18": "T032",
    "G19": "T033",
    "G20": "T035",
    "G21": "T034",
    "G22": "T036",
}
GATE_BLOCKS = {
    "G0": ";".join(f"T{number:03d}" for number in range(3, 37)),
    "G1": "T030",
    "G2": "T008",
    "G3": "T008",
    "G4": "T009;T013;T014;T015",
    "G5": "T010;T011;T012;T013;T014;T015;T025",
    "G6": "T014;T015;T021;T023;T030",
    "G7": "T015",
    "G8": "T016;T017;T018;T019;T020;T025;T029;T031",
    "G9": "T033;T034;T036",
    "G10": "T019;T020;T031;T036",
    "G11": "T026;T027;T028",
    "G12": "T027",
    "G13": "T036",
    "G14": "T036",
    "G15": "T030;T034",
    "G16": "T034",
    "G17": "T036",
    "G18": "T033;T034",
    "G19": "T034",
    "G20": "T036",
    "G21": "T036",
    "G22": "",
}
for gate_row in GATES:
    gate_row["prerequisite_tasks"] = GATE_TASK_OWNERS[gate_row["gate_id"]]
    gate_row["blocks_tasks"] = GATE_BLOCKS[gate_row["gate_id"]]

FREEZE_FIELDS = [
    "freeze_id", "artifact_or_decision", "version_id", "current_status", "freeze_gate",
    "change_class_required", "invalidated_tasks_if_changed",
    "invalidated_experiments_if_changed", "evidence_to_regenerate", "notes",
]


def freeze(fid: str, artifact: str, version: str, gate_id: str, invalid_tasks: str,
           experiments: str, evidence: str, notes: str, status: str = "NOT_FROZEN") -> dict[str, str]:
    return dict(zip(FREEZE_FIELDS, [fid, artifact, version, status, gate_id, "C", invalid_tasks,
                                   experiments, evidence, notes], strict=True))


FREEZES = [
    freeze("F01", "source authority", "SPEC_V2.2/PLAN_V1.0", "G0", "T002-T036", "E01-E16", "all downstream evidence", "v2.2 and canonical execution-plan source hashes recorded; master prompt is planning input only.", "FROZEN"),
    freeze("F02", "hardware/data contract", "HARDWARE_DATA_CONTRACT_V1", "G1", "T005;T013;T028;T029;T031", "E07;E08;E16", "contract and wearable/integration reports", "Observed MongoDB V0 remains unverified until T004."),
    freeze("F03", "dataset versions/manifests", "DATASETS_V1", "G3", "T007-T026", "E01-E14", "data/model/evaluation/federated evidence", "PTB-XL excluded from core scope."),
    freeze("F04", "label mapping", "AAMI_SVF_MAP_V1", "G4", "T008-T026", "E01-E14", "labels/models/evaluations/federated evidence", "Mapping change requires a new explicit version.", "FROZEN"),
    freeze("F05", "patient split", "MITDB_SPLIT_V1", "G5", "T009-T026", "E01-E14", "split/model/evaluation/federated evidence", "Patients and 201/202 grouping immutable after freeze.", "FROZEN"),
    freeze("F06", "preprocessing", "PREPROC_V1/GAP_POLICY_V1", "G6", "T011-T031", "E01-E16", "all derived caches/models/evaluations/deployment", "Any scientific transform change is Class C and invalidates dependent caches, models, evaluations, and deployment artifacts.", "FROZEN"),
    freeze("F07", "baseline configuration", "BASELINE_V1", "G7", "T012;T033", "E01", "baseline report", "Majority remains training-only."),
    freeze("F08", "MODEL_V1", "MODEL_V1", "G8", "T016-T031", "E02-E16", "calibration/evaluation/FL/deployment/context evidence", "Checkpoint/config/test vector hash required."),
    freeze("F09", "calibration", "CAL_V1", "G10", "T018-T031", "E03-E16", "thresholded/evaluation/API/dashboard evidence", "MIT-BIH source-domain only."),
    freeze("F10", "internal test", "INTERNAL_TEST_V1", "G10", "T019-T036", "E04-E16", "internal and comparison evidence", "No post-test tuning."),
    freeze("F11", "external evaluation", "INCART_EXT_V1", "G10", "T033-T036", "E06", "external report", "One locked run before adaptation."),
    freeze("F12", "federated configuration", "FL_CONFIG_V1", "G12", "T025;T026;T033", "E09-E14", "federated/privacy reports", "Patient pool and matched budgets fixed."),
    freeze("F13", "privacy configuration", "SECAGG_CONFIG_V1", "G14", "T033-T036", "E14", "privacy report and claims", "Class B only for interface-only revision; scientific/threat-model claim change is C."),
    freeze("F14", "deployment artifact", "GATEWAY_ARTIFACT_V1", "G15", "T028-T031;T035;T036", "E15;E16", "edge/wearable/API/e2e evidence", "MCU remains optional separate artifact."),
    freeze("F15", "release package", "RELEASE_V1", "G22", "", "E01-E16", "complete release evidence", "No future artifact is frozen during T002."),
]

FREEZE_INVALIDATED_TASKS = {
    "F01": "T002-T036",
    "F02": "T005;T030;T032;T034",
    "F03": "T008-T031;T034-T036",
    "F04": "T009-T031;T034-T036",
    "F05": "T010-T031;T034-T036",
    "F06": "T014-T035",
    "F07": "T015;T016;T035;T036",
    "F08": "T017-T034;T036",
    "F09": "T018-T034;T036",
    "F10": "T019-T036",
    "F11": "T031;T035;T036",
    "F12": "T027;T028;T035;T036",
    "F13": "T035;T036",
    "F14": "T030;T032-T036",
    "F15": "",
}
for freeze_row in FREEZES:
    freeze_row["invalidated_tasks_if_changed"] = FREEZE_INVALIDATED_TASKS[
        freeze_row["freeze_id"]
    ]

DO_NOT_START_FIELDS = ["work_item", "blocked_until", "required_gate", "reason", "allowed_fixture_work", "status"]
DO_NOT_START = [
    ("Real ML training", "Target, split, and preprocessing are frozen", "G4;G5;G6", "Prevents target drift, patient leakage, and causal defects from contaminating models.", "Toy shapes and fixed synthetic training fixtures", "BLOCKED"),
    ("FedAvg conclusions", "MODEL_V1 is frozen and analytical aggregation passes", "G8;G11", "FL conclusions require the same trusted centralized architecture.", "Toy analytical aggregation and serialization", "BLOCKED"),
    ("FedProx", "FedAvg correctness and non-IID manifests pass", "G11;G12", "Otherwise algorithm effects are uninterpretable.", "mu=0 objective unit fixture", "BLOCKED"),
    ("SecAgg+", "Plain aggregation correctness passes", "G11", "Privacy wrapping cannot mask aggregation bugs.", "Threat-model documentation and reference-interface fixtures", "BLOCKED"),
    ("Quantization", "MODEL_V1 is frozen and gateway workload is characterized", "G8;G15", "Optimization before behavior/resources are known risks invalid comparisons.", "Export harness against toy model", "BLOCKED"),
    ("MCU inference optimization", "Mandatory gateway behavior is measured", "G15", "ESP32 inference is optional and needs exact-board evidence.", "Operator inventory and memory-budget template", "BLOCKED"),
    ("Dashboard cosmetics", "Runtime state and API contracts stabilize", "G18", "Visual polish must not drive or hide state semantics.", "Contract fixtures and accessible low-fidelity state views", "BLOCKED"),
    ("Large wearable data collection", "Canonical ingest/synchronization and ethics path are verified", "G1;G16", "Avoid collecting unusable, untraceable, or unauthorized data.", "Sanitized/synthetic replay fixtures and minimal bench dry run", "BLOCKED"),
    ("Final report polishing", "Evidence and final integration stabilize", "G20;G21", "Prevents manually reconstructed or stale numerical claims.", "Report skeleton and evidence links", "BLOCKED"),
    ("Extra model architectures", "A predeclared research question and change-control approval exist", "G8", "Avoid performance-driven model shopping and scope growth.", "None beyond MODEL_V1 test doubles", "BLOCKED"),
    ("Extra datasets outside v2.2", "Versioned scientific revision approves a defined role", "G0", "Dataset-role drift changes evidence and scope; PTB-XL is removed.", "No core execution; retain pre-existing local files without use", "BLOCKED"),
    ("Clinical claims", "Never permitted by v2.2", "G0;G22", "Diagnostic, decision-support, treatment, and clinical-readiness claims are prohibited because the project lacks clinical validation and is research-only.", "Research-target and engineering wording only", "PERMANENTLY_PROHIBITED"),
]

EXPERIMENT_FIELDS = [
    "experiment_id", "research_question", "implementing_task", "prerequisite_gates",
    "frozen_dependencies", "planned_inputs", "planned_metrics", "planned_statistical_method",
    "planned_evidence", "allowed_conclusion", "prohibited_conclusion", "status",
]


def experiment(eid: str, question: str, task_id: str, gates: str, frozen: str, inputs: str,
               metrics: str, statistics: str, evidence: str, allowed: str,
               prohibited: str) -> dict[str, str]:
    return dict(zip(EXPERIMENT_FIELDS, [eid, question, task_id, gates, frozen, inputs, metrics,
                                       statistics, evidence, allowed, prohibited, "PLANNED"], strict=True))


EXPERIMENTS = [
    experiment("E01", "Pipeline sanity", "T011", "G4;G5;G6", "AAMI_SVF_MAP_V1;MITDB_SPLIT_V1;PREPROC_V1", "MIT-BIH train features; majority/logistic regression", "AUPRC;F1", "Training-derived predictor; patient-aware reporting", "reports/baselines/baseline_report.json", "Establish baseline only.", "Clinical performance or test-driven class choice."),
    experiment("E02", "Neural gain", "T012", "G7", "MITDB_SPLIT_V1;PREPROC_V1", "MIT-BIH ECG; MODEL_V1 candidates", "Validation AUPRC", "Predeclared seeds; validation selection only", "reports/model/model_selection.json", "Compare declared model families and freeze MODEL_V1.", "Test-set tuning or seed cherry-picking."),
    experiment("E03", "Calibration", "T017", "G8", "MODEL_V1;MITDB_SPLIT_V1", "Dedicated MIT-BIH calibration logits", "Brier score;reliability;F1 threshold", "Temperature scaling and threshold on calibration patients only", "reports/calibration/calibration.json", "Calibrate project-target probability in MIT-BIH source domain.", "Clinical, INCART, or wearable-domain calibration."),
    experiment("E04", "Internal generalization", "T018", "G8", "MODEL_V1;CAL_V1;PREPROC_V1", "MIT-BIH internal test ECG", "AUPRC;F1;patient-macro F1;95% CI", "2,000 patient-cluster bootstrap replicates", "reports/internal_test/report.json", "Patient-disjoint internal project-target performance.", "Population/diagnostic performance or further tuning."),
    experiment("E05", "Noise robustness", "T019", "G10", "MODEL_V1;CAL_V1", "NSTDB/noise-mixed ECG", "AUPRC degradation", "Frozen noise/SNR regimes; patient-aware comparison where applicable", "reports/noise_robustness/report.json", "Sensitivity to tested controlled noise only.", "Universal real-world robustness."),
    experiment("E06", "External generalization", "T020", "G10", "MODEL_V1;CAL_V1;AAMI_SVF_MAP_V1;INCART Lead II", "INCART standard Lead II ECG", "AUPRC;F1;patient-macro F1;95% CI", "2,000 patient-cluster bootstrap; one locked evaluation", "reports/external_incart/report.json", "Cross-dataset performance under frozen policy.", "Wearable equivalence, 12-lead diagnosis, or adapted external performance."),
    experiment("E07", "Multimodal engineering", "T013", "G1", "HARDWARE_DATA_CONTRACT_V1;PPG_PREPROC_V1", "BIDMC ECG/PPG/numerics", "Alignment;rate error;missingness/quality", "Deterministic engineering comparisons", "reports/bidmc_multimodal_engineering/report.json", "Engineering compatibility and rate/sync behavior.", "AAMI-SVF predictive gain or clinical certification."),
    experiment("E08", "Quality-aware alert robustness", "T016", "G8", "MODEL_V1;CAL_V1;ALERT_POLICY_V1;QUALITY_V1", "BIDMC and WEARABLE_V1 aligned clean/degraded streams", "Excess episodes/hour;chattering;recheck;suppression", "Paired deterministic clean/degraded scenarios with frozen perturbation seeds", "reports/quality_aware_alert_robustness/report.json", "Context changes operational alert robustness.", "AAMI-SVF sensitivity/specificity or learned fusion benefit."),
    experiment("E09", "FedAvg IID", "T023", "G8;G11", "MODEL_V1;CLIENTS_IID_V1;FL_CONFIG_V1", "MIT-BIH whole-patient training clients", "Global/mean/worst-client AUPRC;communication", "Locked round budget and full round logs", "reports/federated/fl_iid/report.json", "Federated baseline in simulated IID partitions.", "Real-hospital deployment or privacy guarantee."),
    experiment("E10", "Label skew", "T024", "G11", "MODEL_V1;CLIENTS_LABEL_V1;FL_CONFIG_V1", "Same training patient pool", "Global/mean/worst-client AUPRC", "Matched-budget condition comparison", "reports/federated/fl_label_skew.json", "Sensitivity to controlled label heterogeneity.", "Institutional generalization."),
    experiment("E11", "Quantity skew", "T024", "G11", "MODEL_V1;CLIENTS_QUANTITY_V1;FL_CONFIG_V1", "Same training patient pool", "Global/mean/worst-client AUPRC", "Matched-budget condition comparison", "reports/federated/fl_quantity.json", "Sensitivity to client-size imbalance.", "Institutional generalization."),
    experiment("E12", "Feature/noise skew", "T024", "G11", "MODEL_V1;CLIENTS_FEATURE_V1;FL_CONFIG_V1", "Training clients with frozen NSTDB regimes", "Global/mean/worst-client AUPRC", "Matched-budget condition comparison; clean held-out primary data", "reports/federated/fl_feature.json", "Sensitivity to declared feature/noise skew.", "Universal domain robustness."),
    experiment("E13", "FedProx comparison", "T025", "G12", "Frozen clients;FL_CONFIG_V1;selected mu", "Same client conditions as FedAvg", "Paired global/client differences;rounds-to-best;bytes", "Matched seeds/configs and paired patient-cluster differences", "reports/federated/fedprox_report.json", "Algorithm effect under matched conditions.", "FedProx superiority if CI/result does not support it."),
    experiment("E14", "Secure aggregation overhead", "T026", "G11", "FedAvg config;SECAGG_CONFIG_V1", "Chosen simulated client condition", "Runtime;bytes;completion;server-visible objects", "Aggregate equivalence and instrumented protocol audit", "reports/privacy_secagg/report.json", "Configured protocol correctness, overhead, and narrow visibility behavior.", "Complete privacy or realistic institutional security."),
    experiment("E15", "Gateway deployment", "T027", "G8", "MODEL_V1;PREPROC_V1;GATEWAY_ARTIFACT_V1", "MIT-BIH test replay", "Size;parameters;RAM;p50/p95 latency;throughput;accuracy delta", ">=1,000 warmed windows and paired prediction comparison", "reports/edge_benchmark/report.json", "Gateway feasibility.", "ESP32 feasibility without separate benchmark."),
    experiment("E16", "Wearable domain", "T028", "G1;G15", "HARDWARE_DATA_CONTRACT_V1;locked pipeline", "WEARABLE_V1 all sensors", "Quality;dropout;timing;HR agreement;latency;output distributions", "Descriptive engineering/domain analysis", "reports/wearable_validation/report.json", "Domain compatibility and engineering behavior.", "Disease/AAMI-SVF sensitivity or clinical calibration."),
]

EXPERIMENT_TASK_OWNERS = {
    "E01": "T014",
    "E02": "T015",
    "E03": "T017",
    "E04": "T018",
    "E05": "T019",
    "E06": "T020",
    "E07": "T021",
    "E08": "T023",
    "E09": "T025",
    "E10": "T026",
    "E11": "T026",
    "E12": "T026",
    "E13": "T027",
    "E14": "T028",
    "E15": "T029",
    "E16": "T030",
}
for experiment_row in EXPERIMENTS:
    experiment_row["implementing_task"] = EXPERIMENT_TASK_OWNERS[
        experiment_row["experiment_id"]
    ]

EVIDENCE_FIELDS = [
    "evidence_id", "requirement_ids", "task_ids", "gate_ids", "expected_path",
    "artifact_type", "generated_by", "status", "sha256", "notes",
]


def evidence(eid: str, reqs: str, tasks: str, gates: str, path: str, artifact_type: str,
             generated_by: str, status: str = "PLANNED", sha256: str = "",
             notes: str = "") -> dict[str, str]:
    return dict(zip(EVIDENCE_FIELDS, [eid, reqs, tasks, gates, path, artifact_type,
                                     generated_by, status, sha256, notes], strict=True))


EVIDENCE = [
    evidence("EV001", "R26;R27;CB01", "T001", "G0", "reports/t001/closure_verification.json", "JSON", "scripts/generate_t001_closure.py", "GENERATED", "b76049f299a5e6d3a2a53a52967638302584d2181a738bf8b3fe77c101f6dfe0", "T001/G0 entry evidence."),
    evidence("EV002", "R26;R27;R28;REL01", "T002", "G0", "reports/t002/coverage_audit.json", "JSON", "scripts/audit_coverage_t002.py", "GENERATED", notes="Hash retained in reports/t002/artifact_hashes.json."),
    evidence("EV003", "R26;R28;REL01", "T002", "G0", "reports/t002/source_hashes.json", "JSON", "scripts/generate_t002_evidence.py", "GENERATED", notes="Binds registries to exact source files."),
    evidence("EV004", "R27;R28", "T002", "G0", "reports/t002/coverage_summary.md", "MARKDOWN", "scripts/generate_t002_evidence.py", "GENERATED", notes="Manual second-audit and orphan classification summary."),
    evidence("EV005", "HW01;DC01;R06.1", "T003;T004", "G1", "reports/hardware/contract_verification.json", "JSON", "T004 hardware verification", notes="No hardware semantics inferred in T002."),
    evidence("EV006", "R26.1;DS01", "T005;T006", "G2;G3", "reports/data/validation_report.json", "JSON", "dataset build/validation commands"),
    evidence("EV007", "R01;R01.1", "T007", "G4", "reports/labels/label_audit.json", "JSON", "label mapping tests"),
    evidence("EV008", "R04;R04.1;R04.2", "T008", "G5", "reports/splits/split_audit.json", "JSON", "split audit command"),
    evidence("EV009", "R02;R05;R05.1;R06;SQ01", "T009;T010", "G6", "reports/preprocessing/causality_tests.json", "JSON", "preprocessing test suite", "GENERATED"),
    evidence("EV010", "R07", "T011", "G7", "reports/baselines/baseline_report.json", "JSON", "baseline experiment E01"),
    evidence("EV011", "R08;R08.1", "T012", "G8", "checkpoints/MODEL_V1.manifest.json", "JSON", "centralized training E02"),
    evidence("EV012", "R13;R13.1", "T013;T014", "G9", "reports/bidmc_multimodal_engineering/report.json", "JSON", "experiment E07"),
    evidence("EV013", "R14;R14.1;R15;R15.1;CB05", "T015;T016", "G9", "reports/quality_aware_alert_robustness/report.json", "JSON", "experiment E08"),
    evidence("EV014", "R09;R09.1;CB06", "T017", "G10", "reports/calibration/calibration.json", "JSON", "experiment E03"),
    evidence("EV015", "R10;R10.1", "T018", "G10", "reports/internal_test/report.json", "JSON", "experiment E04"),
    evidence("EV016", "R11", "T019", "G10", "reports/noise_robustness/report.json", "JSON", "experiment E05"),
    evidence("EV017", "R12", "T020", "G10", "reports/external_incart/report.json", "JSON", "experiment E06"),
    evidence("EV018", "R23;R23.1", "T021", "G17", "reports/explainability/case_report.json", "JSON", "EXPLAINABILITY_V1"),
    evidence("EV019", "R16;R16.1;R17;CB03", "T022;T023", "G11", "reports/federated/fl_iid/report.json", "JSON", "experiment E09"),
    evidence("EV020", "R18;R18.1", "T024", "G12", "reports/federated/non_iid_report.json", "JSON", "experiments E10-E12"),
    evidence("EV021", "R19;R10.1", "T025", "G13", "reports/federated/fedprox_report.json", "JSON", "experiment E13"),
    evidence("EV022", "R20;R20.1;CB04", "T026", "G14", "reports/privacy_secagg/report.json", "JSON", "experiment E14"),
    evidence("EV023", "R21;R21.1", "T027", "G15", "reports/edge_benchmark/report.json", "JSON", "experiment E15"),
    evidence("EV024", "R22;R22.1;CB02", "T028", "G16", "reports/wearable_validation/report.json", "JSON", "experiment E16"),
    evidence("EV025", "R24;R24.1;CB01;CB06", "T029", "G18", "reports/api/contract_tests.json", "JSON", "API contract tests"),
    evidence("EV026", "R25;R25.1;CB01", "T030", "G19", "reports/dashboard/state_tests.json", "JSON", "dashboard state tests"),
    evidence("EV027", "R22;R24;R25;R28.9;R28.10", "T031", "G21", "reports/integration/e2e_replay.json", "JSON", "end-to-end replay"),
    evidence("EV028", "R26;R26.1;TEST01", "T032", "G20", "reports/reproducibility/clean_run.json", "JSON", "clean-environment gate"),
    evidence("EV029", "R28;REL01;CB01;CB02;CB03;CB04;CB05;CB06", "T033;T034;T035;T036", "G22", "release/release_manifest.json", "JSON", "release evidence generator"),
    evidence("EV030", "R26;R27", "T002", "G0", "reports/t002/task_registry_reconciliation.csv", "CSV", "scripts/reconcile_t002_sources.py", "GENERATED", notes="Preserves field-level differences between provisional and canonical task registries."),
    evidence("EV031", "R26;R27", "T002", "G0", "reports/t002/source_reconciliation.json", "JSON", "scripts/generate_t002_evidence.py", "GENERATED", notes="Records final source roles and zero remaining semantic errors."),
]

EVIDENCE_TASK_OWNERS = {
    "EV001": "T001",
    "EV002": "T002",
    "EV003": "T002",
    "EV004": "T002",
    "EV005": "T003;T004",
    "EV006": "T006;T007",
    "EV007": "T008",
    "EV008": "T009;T010",
    "EV009": "T010;T011;T012;T013",
    "EV010": "T014",
    "EV011": "T015;T016",
    "EV012": "T021",
    "EV013": "T022;T023",
    "EV014": "T017",
    "EV015": "T018",
    "EV016": "T019",
    "EV017": "T020",
    "EV018": "T031",
    "EV019": "T024;T025",
    "EV020": "T026",
    "EV021": "T027",
    "EV022": "T028",
    "EV023": "T029",
    "EV024": "T030",
    "EV025": "T032",
    "EV026": "T033",
    "EV027": "T034",
    "EV028": "T035",
    "EV029": "T036",
    "EV030": "T002",
    "EV031": "T002",
}
for evidence_row in EVIDENCE:
    evidence_row["task_ids"] = EVIDENCE_TASK_OWNERS[evidence_row["evidence_id"]]
    evidence_path = ROOT / evidence_row["expected_path"]
    if evidence_row["status"] == "GENERATED" and evidence_path.exists():
        evidence_row["sha256"] = hash_file(evidence_path)


def main() -> None:
    write_csv("task_registry_v1.csv", TASK_FIELDS, TASKS)
    write_csv("requirements_v22.csv", REQ_FIELDS, REQUIREMENTS)
    write_csv("gate_registry_v1.csv", GATE_FIELDS, GATES)
    write_csv("freeze_registry_v1.csv", FREEZE_FIELDS, FREEZES)
    write_csv(
        "do_not_start_v1.csv",
        DO_NOT_START_FIELDS,
        [dict(zip(DO_NOT_START_FIELDS, row, strict=True)) for row in DO_NOT_START],
    )
    write_csv("experiment_registry_v1.csv", EXPERIMENT_FIELDS, EXPERIMENTS)
    write_csv("evidence_registry_v1.csv", EVIDENCE_FIELDS, EVIDENCE)
    print(
        f"T002 registries: tasks={len(TASKS)} requirements={len(REQUIREMENTS)} "
        f"gates={len(GATES)} freezes={len(FREEZES)} controls={len(DO_NOT_START)} "
        f"experiments={len(EXPERIMENTS)} evidence={len(EVIDENCE)}"
    )


if __name__ == "__main__":
    main()
