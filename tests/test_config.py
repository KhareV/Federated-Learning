from pathlib import Path

from nhm.config import load_yaml, validate_base_config

ROOT = Path(__file__).resolve().parents[1]


def test_base_config_loads_with_locked_versions() -> None:
    config = load_yaml(ROOT / "configs/base.yaml")
    validate_base_config(config)

    assert config["project"]["spec_version"] == "2.2"
    assert config["project"]["current_phase"] == "T027"
    assert config["versions"]["target"] == "AAMI_SVF_WINDOW_V1"
    assert config["versions"]["label_map"] == "AAMI_SVF_MAP_V1"
