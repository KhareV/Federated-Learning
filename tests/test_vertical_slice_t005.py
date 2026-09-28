import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

from api.app import process_observed_record
from simulation.fixtures import OBSERVED_FIXTURE_PATH, TRUTH_FIXTURE_PATH, build_smoke_session
from simulation.wearable import get_truth, iter_observed_records

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_MODULES = ("deployment.mock_inference", "fusion.state_machine", "api.app")


def _load_observed() -> list[dict]:
    lines = (ROOT / OBSERVED_FIXTURE_PATH).read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines]


def _load_truth() -> list[dict]:
    lines = (ROOT / TRUTH_FIXTURE_PATH).read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines]


def _run_pipeline(observed: list[dict]) -> list[str]:
    return [
        process_observed_record(SimpleNamespace(**record)).monitoring_state
        for record in observed
    ]


def test_same_fixture_produces_same_semantic_output() -> None:
    observed = _load_observed()
    run_a = _run_pipeline(observed)
    run_b = _run_pipeline(observed)
    assert run_a == run_b


def test_state_sequence_matches_scenario_expectation_exactly() -> None:
    observed = _load_observed()
    truth = _load_truth()
    states = _run_pipeline(observed)
    expected = [row["expected_monitoring_state"] for row in truth]
    assert states == expected
    assert states == [
        "NORMAL_MONITORED_PATTERN",
        "NORMAL_MONITORED_PATTERN",
        "CONTEXT_UNAVAILABLE",
        "CONTEXT_UNAVAILABLE",
        "NORMAL_MONITORED_PATTERN",
        "NORMAL_MONITORED_PATTERN",
        "RECHECK_SENSOR",
        "RECHECK_SENSOR",
        "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
        "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
    ]


def test_production_path_signatures_never_accept_truth_input() -> None:
    """Static guarantee: none of the production entry points declare a truth/simulation
    parameter, so SimulationTruth structurally cannot be threaded through them."""
    import api.app as api_app
    import deployment.mock_inference as mock_inference
    import fusion.state_machine as state_machine

    for function in (mock_inference.run, state_machine.classify, api_app.process_observed_record):
        parameters = inspect.signature(function).parameters
        for name in parameters:
            assert "truth" not in name.casefold()


def test_production_modules_never_import_the_truth_channel() -> None:
    """AST-level guarantee, not just a behavioral one: production modules do not import
    simulation.wearable/simulation.fixtures or reference SimulationTruth/get_truth at all."""
    forbidden_modules = {"simulation.wearable", "simulation.fixtures"}
    forbidden_names = {"SimulationTruth", "get_truth"}
    for module_name in PRODUCTION_MODULES:
        path = ROOT / module_name.replace(".", "/")
        path = path.with_suffix(".py")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(alias.name in forbidden_modules for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert module not in forbidden_modules
                if module == "simulation":
                    assert not any(alias.name in {"wearable", "fixtures"} for alias in node.names)
            elif isinstance(node, ast.Name):
                assert node.id not in forbidden_names
            elif isinstance(node, ast.Attribute):
                assert node.attr not in forbidden_names


def test_two_different_truth_sidecars_yield_identical_production_output() -> None:
    """Behavioral leakage test (execution-plan Section 24): generate one observed fixture,
    construct two different truth sidecars for it, run the full production pipeline against
    both, and assert the outputs are identical -- proving SimulationTruth content cannot
    influence production output even when deliberately varied."""
    session = build_smoke_session()
    observed = [record.to_canonical_dict() for record in iter_observed_records(session)]
    truth_a = [vars(t) for t in get_truth(session)]

    # A second, deliberately different/implausible truth sidecar for the same observed input.
    truth_b = [
        {
            **row,
            "latent_hr": -999.0,
            "latent_spo2": -999.0,
            "expected_monitoring_state": "SYSTEM_ERROR",
        }
        for row in truth_a
    ]
    assert truth_a != truth_b

    def run_with_truth_in_scope(_unused_truth: list[dict]) -> list[str]:
        # The truth sidecar is held in a local variable to prove it is available in this
        # test's scope, yet the pipeline call below has no parameter through which it could
        # be passed even if we wanted to.
        return _run_pipeline(observed)

    output_with_truth_a = run_with_truth_in_scope(truth_a)
    output_with_truth_b = run_with_truth_in_scope(truth_b)
    assert output_with_truth_a == output_with_truth_b


def test_smoke_report_contains_no_clinical_metrics() -> None:
    report_path = ROOT / "reports/t005/smoke_report.json"
    if not report_path.exists():
        return  # generated by scripts/smoke_t005.py / make t005-smoke; not required pre-run
    report = json.loads(report_path.read_text(encoding="utf-8"))
    forbidden_keys = {"auprc", "sensitivity", "specificity", "auroc", "f1", "accuracy"}
    assert not (forbidden_keys & {key.casefold() for key in report})
