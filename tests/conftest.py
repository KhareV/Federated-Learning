"""CLEAN_CLONE_GATING_V1 (V2-014): a brand-new clone deliberately has NO raw third-party
datasets, NO gitignored processed window caches and NO untracked candidate checkpoints (never
committed, never copied in). Tests that need those untracked inputs are skipped with an explicit
reason ONLY when the input is absent; when the inputs are present (a developer checkout that
acquired them via the repository's own scripts) every test runs unchanged. The gating never
force-passes a test and never hides a failure of an available input. The skip list is reported by
the V2-014 evidence as a distinct category (DATA_GATED_SKIPPED), excluded from the clean SOFTWARE
claim."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

RAW_MITDB = "data/raw/mitdb/1.0.0/*.dat"
RAW_INCART = "data/raw/incartdb/1.0.0/*.dat"
RAW_NSTDB = "data/raw/nstdb/1.0.0/*.dat"
RAW_BIDMC = "data/raw/bidmc/1.0.0/bidmc_data.mat"
PROCESSED = "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1"
V1_CANDIDATES = "checkpoints/candidates/MODEL_V1/MODEL_V1_seed_*_best.pt"
V2_007_CANDIDATES = "checkpoints/model_v2/v2_007_official_validation/*"
DEV_VENV = ".venv-t032/bin/python"

GATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tests/test_bidmc_context_alignment.py::test_source_clock_contract", (RAW_BIDMC,)),
    ("tests/test_bidmc_context_results.py::"
     "test_frozen_context_result_verifies_and_has_no_disease_metrics", (RAW_BIDMC,)),
    ("tests/test_c032_norm_runtime.py::test_runtime_equivalence_against_t029_internal_population",
     (PROCESSED,)),
    ("tests/test_external_incart_protocol.py::test_t007_source_and_lead_contract_closes",
     (RAW_INCART,)),
    ("tests/test_model_v2_final_inner_split_manifest.py::"
     "test_deterministic_regeneration_byte_identical", (RAW_MITDB,)),
    ("tests/test_model_v2_partition_guard.py::test_train_waveform_access_succeeds", (PROCESSED,)),
    ("tests/test_model_v2_partition_guard.py::test_ledger_is_append_only_across_multiple_accesses",
     (PROCESSED,)),
    ("tests/test_nstdb_noise_protocol.py::test_official_source_allowlist_hashes_and_mlii",
     (RAW_NSTDB,)),
    ("tests/test_real_window_leakage.py::test_real_cache_paths_are_partition_local_and_fresh",
     (PROCESSED, RAW_MITDB)),
    ("tests/test_real_window_leakage.py::test_selected_real_record_rebuild_is_deterministic",
     (PROCESSED, RAW_MITDB)),
    ("tests/test_split_determinism.py::test_split_builder_regenerates_byte_identical_output",
     (RAW_MITDB,)),
    ("tests/test_v2_007_config.py::test_v1_reference_checkpoint_hash_exact", (V1_CANDIDATES,)),
    ("tests/test_v2_008_results.py::test_checkpoint_byte_identical_to_source_and_sha_exact",
     (V2_007_CANDIDATES,)),
    ("tests/test_v2_010_config.py::test_nstdb_v1_freeze_pass_without_model_inference",
     (DEV_VENV,)),
    ("tests/test_v2_011_config.py::test_noise_protocol_audit_matches_frozen_c031", (RAW_NSTDB,)),
    ("tests/test_v2_011_results.py::test_verifier_passes_on_canonical_artifacts", (RAW_NSTDB,)),
)


def _missing(patterns: tuple[str, ...]) -> list[str]:
    return [p for p in patterns if not any(ROOT.glob(p))]


def pytest_collection_modifyitems(config, items) -> None:
    for item in items:
        for prefix, patterns in GATES:
            if item.nodeid.startswith(prefix):
                missing = _missing(patterns)
                if missing:
                    item.add_marker(pytest.mark.skip(
                        reason=f"CLEAN_CLONE_DATA_GATED: untracked input absent: {missing}"))
