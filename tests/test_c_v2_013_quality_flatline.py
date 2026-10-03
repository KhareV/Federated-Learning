"""C-V2-013-QUALITY-FLATLINE-AUDIT: QUALITY_V1 flatline contract, the filtered-representation
property that makes a constant NONZERO source undetectable, the exact-zero flatline path through
the streaming runtime and API, F06 consistency and the stream empty-chunk guard."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import simulation.flatline_scenario_c_v2_013 as scen
import simulation.stream_runtime_v2013 as sr
from api.app_v2 import create_research_app
from api.runtime_v2 import ResearchRuntimeV2
from nhm.hashing import hash_file
from preprocessing.ecg import ECGPreprocessingPipeline
from preprocessing.freeze import verify_preproc_freeze
from preprocessing.quality import FLATLINE_RELATIVE_EPSILON, evaluate_ecg_quality
from simulation import profile_v2013 as prof

ROOT = Path(__file__).resolve().parents[1]
KW = {"session_id": "T-FLAT", "model_id": "MODEL_V2_FINAL", "replay_id": "T"}


def _reasons(signal: np.ndarray) -> list[str]:
    return [r.value for r in evaluate_ecg_quality(signal).reasons]


def test_f06_verifies_and_quality_files_match_pins() -> None:
    assert verify_preproc_freeze(ROOT)["status"] == "PASS"
    pins = json.loads((ROOT / "manifests/preprocessing/PREPROC_V1.lock.json").read_text())[
        "artifact_sha256"]
    for relative in ("configs/quality_v1.yaml", "preprocessing/quality.py"):
        assert hash_file(ROOT / relative) == pins[relative]
    assert FLATLINE_RELATIVE_EPSILON == 1e-12


@pytest.mark.parametrize("value", [0.0, 0.37, -1.9, 1e-9, 1e3, 1e9])
def test_exact_constants_are_unusable_flatline(value: float) -> None:
    result = evaluate_ecg_quality(np.full(2500, value))
    assert result.state.value == "UNUSABLE" and "FLATLINE" in _reasons(np.full(2500, value))


def test_near_flat_below_and_above_the_frozen_criterion() -> None:
    t = np.arange(2500) / 250.0
    wiggle = np.sign(np.sin(t * 9))
    assert "FLATLINE" in _reasons(5.0 * (1 + 0.5e-12 * wiggle))
    assert "FLATLINE" not in _reasons(3.0 * (1 + 1e-10 * wiggle))
    assert evaluate_ecg_quality(np.sin(2 * np.pi * 1.2 * t)).state.value == "VALID"


def test_constant_nonzero_source_is_not_flat_after_the_frozen_pipeline() -> None:
    """Documents the frozen-pipeline property: the 360->250 resampler leaves a persistent ripple
    on a constant nonzero source, so the FILTERED window is not flat (std/rms ~ 1)."""
    pipe = ECGPreprocessingPipeline(360, "MITDB_360_TO_250_V1")
    values, out = np.full(360 * 40, 0.12), []
    for s in range(0, values.size, 360):
        res = pipe.process(values[s:s + 360], np.arange(s, s + 360, dtype=np.int64),
                           source_timestamps_us=np.arange(s, s + 360, dtype=np.int64)
                           * 1_000_000 // 360 if s == 0 else None)
        out.extend(c.filtered_values for c in res.chunks)
    window = np.concatenate(out)[-2500:]
    assert float(np.std(window) / np.sqrt(np.mean(window**2))) > 0.5
    assert "FLATLINE" not in _reasons(window)


def test_exact_zero_source_from_stream_start_flags_every_complete_flat_window() -> None:
    events = sr.run_stream(scen.iter_flatline_records(scen.FULL_FLATLINE_PROFILE), **KW)
    flat = [e for e in events if e["timestamp_us"] <= 40_000_000]
    assert len(flat) == 6
    for event in flat:
        assert event["ecg_quality"] == "UNUSABLE"
        assert "FLATLINE" in event["diagnostics"]["quality_reasons"]
    assert all(e["ecg_quality"] == "VALID" for e in events if e["timestamp_us"] > 50_000_000)


def test_flatline_window_through_api_returns_422_without_inference() -> None:
    events = sr.run_stream(scen.iter_flatline_records(scen.EXCERPT_FLATLINE_PROFILE), **KW)
    flat = next(e for e in events if "FLATLINE" in e["diagnostics"]["quality_reasons"])
    calls = {"infer": 0}

    class Spy(ResearchRuntimeV2):
        def infer(self, ecg_samples):  # type: ignore[no-untyped-def]
            calls["infer"] += 1
            return super().infer(ecg_samples)

    client = TestClient(create_research_app(runtime=Spy(ROOT, verify="manifest")))
    body = {"contract_version": "API_SCHEMA_V1", "session_id": "S-FLAT",
            "timestamp_us": flat["timestamp_us"], "ecg": flat["ecg"],
            "ecg_quality": flat["ecg_quality"], "ppg_context": flat["ppg_context"],
            "model_id": "MODEL_V2_FINAL"}
    response = client.post("/v1/infer-window", json=body)
    assert response.status_code == 422 and calls["infer"] == 0
    assert response.json()["error_type"] == "UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW"


@pytest.mark.parametrize("size", [1, 97, 360, 1000])
def test_stream_is_invariant_to_chunk_size_including_tail_chunks(
        size: int, monkeypatch: pytest.MonkeyPatch) -> None:
    reference = sr.run_stream(scen.iter_flatline_records(scen.EXCERPT_FLATLINE_PROFILE), **KW)
    monkeypatch.setattr(sr, "CHUNK_RECORDS", size)
    assert sr.run_stream(scen.iter_flatline_records(scen.EXCERPT_FLATLINE_PROFILE), **KW
                         ) == reference


def test_original_v2_013_replay_bundle_is_reproduced_byte_for_byte() -> None:
    """The empty-chunk guard must not change any V2-013 result."""
    bundle = json.loads((ROOT / "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V1.json"
                         ).read_text())["events"]
    keys = tuple(bundle[0])
    events = sr.run_stream(prof.iter_observed_records(prof.FULL_PROFILE),
                           session_id=prof.FULL_PROFILE.session_id, model_id="MODEL_V2_FINAL",
                           replay_id="WEARABLE_SIM_V2_REPLAY_V1")
    assert [{k: e[k] for k in keys} for e in events] == bundle


def test_flatline_bundle_is_deterministic_and_manifest_consistent() -> None:
    manifest = json.loads((ROOT / "tests/fixtures/e2e/"
                           "WEARABLE_SIM_V2_REPLAY_V2_FLATLINE.manifest.json").read_text())
    path = ROOT / "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V2_FLATLINE.json"
    assert hash_file(path) == manifest["bundle_sha256"]
    assert manifest["flatline_reason_window_count"] == 6
    events = json.loads(path.read_text())["events"]
    digest = hashlib.sha256(json.dumps(events, sort_keys=True).encode()).hexdigest()
    assert digest == manifest["events_semantic_sha256"]


def test_production_path_does_not_import_flatline_scenario() -> None:
    import ast

    for relative in ("api/runtime_v2.py", "api/app_v2.py", "simulation/stream_runtime_v2013.py"):
        names = {n.module for n in ast.walk(ast.parse((ROOT / relative).read_text()))
                 if isinstance(n, ast.ImportFrom) and n.module}
        assert "simulation.flatline_scenario_c_v2_013" not in names


def test_isolation_verifier_scope_flags_modified_deleted_renamed_but_not_added(
        tmp_path: Path) -> None:
    """The V2-013 isolation check uses `git diff --diff-filter=MDRT` over the V1 pathspec. It must
    still catch any modification of an existing V1 file, while ignoring only new additive files."""
    import subprocess

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True,
                              check=True).stdout

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "fusion").mkdir()
    (tmp_path / "fusion/engine.py").write_text("a = 1\n")
    (tmp_path / "fusion/old.py").write_text("b = 1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "entry")
    entry = git("rev-parse", "HEAD").strip()
    (tmp_path / "fusion/additive_binding.py").write_text("c = 1\n")       # added: ignored
    (tmp_path / "fusion/engine.py").write_text("a = 2\n")                  # modified: flagged
    (tmp_path / "fusion/old.py").unlink()                                  # deleted: flagged
    git("add", "-A")
    flagged = set(git("diff", "--name-only", "--cached", "--diff-filter=MDRT", entry, "--",
                      "fusion").split())
    assert flagged == {"fusion/engine.py", "fusion/old.py"}
