"""Enforce the locked dataset-role boundaries (T007 Section 23).

Availability of INCART/NSTDB/BIDMC in the repository must never imply permission to
train/tune/evaluate on them outside their locked role.
"""

import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLES_PATH = ROOT / "manifests/datasets/dataset_roles_v1.yaml"

# Modules that must never be imported by a raw dataset loader -- their presence would
# indicate premature training/evaluation/tuning use of a role-restricted dataset.
FORBIDDEN_IMPORT_PREFIXES = ("models", "training", "evaluation", "federated", "deployment")


def _roles() -> dict:
    return yaml.safe_load(ROLES_PATH.read_text(encoding="utf-8"))


def test_registry_declares_all_four_datasets() -> None:
    roles = _roles()
    assert set(roles) == {"MITDB", "INCART", "NSTDB", "BIDMC"}


def test_incart_is_locked_external_evaluation_only() -> None:
    incart = _roles()["INCART"]
    assert incart["role"] == "LOCKED_EXTERNAL_ECG_EVALUATION"
    assert incart["external_evaluation_only"] is True
    assert incart["allowed_for_training"] is False
    assert incart["allowed_for_model_selection"] is False
    assert incart["allowed_for_threshold_selection"] is False
    assert incart["allowed_for_calibration"] is False
    assert "T020" in incart["owning_tasks"]


def test_nstdb_is_robustness_only() -> None:
    nstdb = _roles()["NSTDB"]
    assert nstdb["role"] == "NOISE_ROBUSTNESS"
    assert nstdb["robustness_only"] is True
    assert nstdb["allowed_for_training"] is False
    assert nstdb["allowed_for_model_selection"] is False
    assert "T019" in nstdb["owning_tasks"]


def test_bidmc_is_multimodal_engineering_only() -> None:
    bidmc = _roles()["BIDMC"]
    assert bidmc["role"] == "MULTIMODAL_ENGINEERING_CONTEXT"
    assert bidmc["multimodal_engineering_only"] is True
    assert bidmc["allowed_for_arrhythmia_training"] is False
    assert bidmc["allowed_for_training"] is False


def test_mitdb_remains_the_only_core_training_dataset() -> None:
    roles = _roles()
    core_training = [
        dataset_id for dataset_id, role in roles.items() if role["allowed_for_training"]
    ]
    assert core_training == ["MITDB"]


def test_role_registry_has_no_overlapping_locked_roles() -> None:
    roles = _roles()
    exclusive_flags = ("external_evaluation_only", "robustness_only", "multimodal_engineering_only")
    for dataset_id, role in roles.items():
        true_flags = [flag for flag in exclusive_flags if role[flag]]
        assert len(true_flags) <= 1, f"{dataset_id} has overlapping exclusive roles: {true_flags}"


def _module_forbidden_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in FORBIDDEN_IMPORT_PREFIXES:
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".")[0]
            if top in FORBIDDEN_IMPORT_PREFIXES:
                hits.append(module)
    return hits


def test_dataset_loaders_never_import_training_or_evaluation_code() -> None:
    for module_name in ("mitdb.py", "incart.py", "nstdb.py", "bidmc.py", "physionet.py"):
        path = ROOT / "datasets" / module_name
        hits = _module_forbidden_imports(path)
        assert hits == [], f"{module_name} imports role-violating modules: {hits}"


def test_no_external_evaluation_metric_code_references_incart() -> None:
    """T020 owns the single locked INCART evaluation; nothing in T007's scope may compute a
    performance metric against it yet."""
    incart_source = (ROOT / "datasets/incart.py").read_text(encoding="utf-8").casefold()
    prohibited = ("auprc", "auroc", "sensitivity", "specificity", "accuracy_score", "f1_score")
    for term in prohibited:
        assert term not in incart_source


def test_no_robustness_metric_code_references_nstdb() -> None:
    """T019 owns the robustness experiment; T007's NSTDB loader must not compute one."""
    nstdb_source = (ROOT / "datasets/nstdb.py").read_text(encoding="utf-8").casefold()
    prohibited = ("auprc", "auroc", "sensitivity", "specificity", "accuracy_score", "f1_score")
    for term in prohibited:
        assert term not in nstdb_source


def test_bidmc_loader_never_produces_arrhythmia_labels() -> None:
    bidmc_source = (ROOT / "datasets/bidmc.py").read_text(encoding="utf-8").casefold()
    prohibited = ("aami", "svf_window", "arrhythmia_label", "beat_class")
    for term in prohibited:
        assert term not in bidmc_source
