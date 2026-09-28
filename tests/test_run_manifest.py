from pathlib import Path

from nhm.run_manifest import create_run_manifest, validate_run_manifest

ROOT = Path(__file__).resolve().parents[1]


def test_minimal_t001_manifest_validates() -> None:
    manifest = create_run_manifest(
        ROOT,
        run_id="test-t001",
        phase_id="T001",
        task_id="T001",
        config_path=ROOT / "configs/base.yaml",
        dependency_snapshot_path=None,
        notes="Offline deterministic contract test.",
    )
    validate_run_manifest(manifest, ROOT / "contracts/run_manifest_v1.schema.json")

