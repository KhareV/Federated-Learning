from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_t031_is_posthoc_noncausal_and_hardware_deferred() -> None:
    text = "\n".join(
        (ROOT / path).read_text()
        for path in (
            "evaluation/explain.py",
            "evaluation/error_analysis.py",
            "scripts/prepare_t031_protocol.py",
        )
    )
    assert "AdamW" not in text
    assert "fit_temperature" not in text
    assert "WEARABLE_V1" not in text
