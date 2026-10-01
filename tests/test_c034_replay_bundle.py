"""C034-UI-E2E: eligibility audit, frontend-bundle determinism/identity, and the T002
historical-evidence audit (Section 28/32/33)."""

from __future__ import annotations

import json
import subprocess
from itertools import pairwise
from pathlib import Path

from nhm.hashing import hash_file
from scripts.audit_replay_eligibility_c034 import audit as eligibility_audit
from scripts.build_frontend_replay_bundle_c034 import build as build_bundle

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def test_eligibility_audit_passes_with_no_conflicts_and_never_inspects_target_class() -> None:
    result = eligibility_audit()
    assert result["status"] == "PASS"
    assert result["conflicts"] == []
    assert result["windows_checked"] == 12
    assert result["target_class_inspected_for_reselection"] is False


def test_frontend_bundle_regeneration_is_byte_identical() -> None:
    first = json.dumps(build_bundle(), sort_keys=True)
    second = json.dumps(build_bundle(), sort_keys=True)
    assert first == second


def test_frontend_bundle_matches_the_tracked_static_asset_sha() -> None:
    manifest = json.loads(
        (ROOT / "reports/c034_ui_e2e/frontend_replay_bundle.json").read_text(encoding="utf-8")
    )
    tracked_path = FRONTEND / "static/replay/PUBLIC_ECG_REPLAY_V1.json"
    assert hash_file(tracked_path) == manifest["sha256"]


def test_frontend_bundle_has_twelve_ordered_events_5s_apart_2500_samples_no_truth() -> None:
    bundle = build_bundle()
    events = sorted(bundle["events"], key=lambda e: e["sequence_index"])
    assert [e["sequence_index"] for e in events] == list(range(12))
    timestamps = [e["timestamp_us"] for e in events]
    for earlier, later in pairwise(timestamps):
        assert later - earlier == 5_000_000
    assert all(len(e["ecg"]["samples"]) == 2500 for e in events)
    assert bundle["labels_included"] is False
    assert bundle["prediction_outcome_included"] is False
    assert bundle["simulation_truth_included"] is False


def test_t002_historical_evidence_audit_recorded_no_unexplained_change() -> None:
    audit = json.loads(
        (ROOT / "reports/c034_ui_e2e/t002_historical_evidence_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["status"] == "PASS"
    assert audit["changed"] is False
    assert audit["historical_t002_evidence_rewritten"] is False

    # Re-verify directly rather than trusting the recorded JSON alone.
    diff = subprocess.run(
        [
            "git",
            "diff",
            "--stat",
            audit["compared_from_sha"],
            audit["compared_to_sha"],
            "--",
            *audit["files_checked"],
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert diff.stdout.strip() == ""


def test_t034_historical_evidence_logs_were_restored_not_overwritten() -> None:
    """C034 regenerated reports/t034/public_replay_responses.jsonl and
    sim_replay_responses.jsonl while re-running the canonical replay for its own digest check;
    both were restored to their exact original committed bytes afterwards (only latency,
    which is excluded from the semantic digest, had differed)."""
    diff = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "reports/t034/public_replay_responses.jsonl",
            "reports/t034/sim_replay_responses.jsonl",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert diff.stdout.strip() == ""
