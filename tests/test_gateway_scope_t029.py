from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_scope_has_no_training_fusion_api_or_hardware() -> None:
    text = "\n".join(
        (ROOT / path).read_text()
        for path in ("deployment/export.py", "deployment/runtime.py", "deployment/benchmark.py")
    )
    forbidden = ("AdamW", "BCEWithLogitsLoss", "FastAPI", "ESP32", "FedProx", "SecAgg")
    assert all(token not in text for token in forbidden)


def test_int8_is_optional_and_not_attempted() -> None:
    config = (ROOT / "configs/gateway_artifact_v1.yaml").read_text()
    assert "INT8_STATUS: OPTIONAL_NOT_ATTEMPTED" in config
    assert "CPU" in config or "cpu" in config


def test_no_public_api_or_dashboard_files_created_by_t029() -> None:
    assert not (ROOT / "api/gateway_t029.py").exists()
    assert not (ROOT / "dashboard/t029").exists()
