from pathlib import Path

from nhm.coverage import read_csv

ROOT = Path(__file__).resolve().parents[1]


def test_do_not_start_controls_cover_sequence_and_claim_boundaries() -> None:
    rows = read_csv(ROOT / "manifests/do_not_start_v1.csv")
    text = " ".join(" ".join(row.values()).casefold() for row in rows)
    for expected in (
        "real ml training",
        "fedavg",
        "fedprox",
        "secagg+",
        "quantization",
        "mcu inference",
        "dashboard cosmetics",
        "wearable data collection",
        "final report polishing",
        "extra model architectures",
        "extra datasets",
        "clinical claims",
    ):
        assert expected in text
    assert len(rows) == 12
    assert any(row["status"] == "PERMANENTLY_PROHIBITED" for row in rows)
