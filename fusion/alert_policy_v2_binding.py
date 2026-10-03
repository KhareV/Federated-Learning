"""ALERT_POLICY_V1 -> MODEL_V2_FINAL/CAL_V2 binding (additive; ALERT_POLICY_V1 is unchanged).

fusion.episode_manager.AlertEpisodeManager is generic: every model/calibration-dependent value
lives in the `AlertPolicy` dataclass. Only `load_alert_policy` is coupled to MODEL_V1 (it reads
the threshold/model/calibration IDs from CAL_V1 and requires threshold.source == CAL_V1). This
module builds the same `AlertPolicy` with the threshold and identities taken from the frozen
CAL_V2 artifact, after re-validating that every temporal parameter (K=2, M=2, cooldown=30 s,
HR-disagreement tolerance/duration, comparator) in the UNCHANGED ALERT_POLICY_V1 config still has
its locked value. It introduces no new policy: the semantics are identical.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from fusion.episode_manager import AlertPolicy

ROOT = Path(__file__).resolve().parents[1]
BINDING_ID = "ALERT_POLICY_V1_MODEL_V2_BINDING"
POLICY_ID = "ALERT_POLICY_V1"

LOCKED_TEMPORAL_PARAMETERS = {
    "policy_id": "ALERT_POLICY_V1",
    "window_cadence_seconds": 5,
    "open": 2,
    "close": 2,
    "cooldown_seconds": 30,
    "threshold_comparator": ">=",
    "rate_policy_id": "HR_DISAGREEMENT_TOLERANCE_V1",
    "rate_tolerance": 20.0,
    "rate_duration": 10.0,
    "rate_comparator": ">",
}


class AlertPolicyV2BindingError(ValueError):
    """The V2 binding could not be built without altering a locked policy parameter."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observed_temporal_parameters(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_id": config["policy_id"],
        "window_cadence_seconds": config["window_cadence_seconds"],
        "open": config["open"]["required_consecutive_valid_above"],
        "close": config["close"]["required_consecutive_valid_below"],
        "cooldown_seconds": config["cooldown_seconds"],
        "threshold_comparator": config["threshold"]["comparator"],
        "rate_policy_id": config["rate_consistency"]["policy_id"],
        "rate_tolerance": config["rate_consistency"]["tolerance_bpm"],
        "rate_duration": config["rate_consistency"]["continuous_duration_seconds"],
        "rate_comparator": config["rate_consistency"]["comparator"],
    }


def load_alert_policy_v2_binding(root: Path = ROOT) -> AlertPolicy:
    config_path = root / "configs/alert_policy_v1.yaml"
    config: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if observed_temporal_parameters(config) != LOCKED_TEMPORAL_PARAMETERS:
        raise AlertPolicyV2BindingError("ALERT_POLICY_V1_TEMPORAL_PARAMETERS_CHANGED")
    cal = json.loads((root / "artifacts/CAL_V2.json").read_text(encoding="utf-8"))
    if cal.get("calibration_id") != "CAL_V2" or cal.get("model_id") != "MODEL_V2_FINAL":
        raise AlertPolicyV2BindingError("CAL_V2_IDENTITY_MISMATCH")
    if cal.get("threshold_comparator") != config["threshold"]["comparator"]:
        raise AlertPolicyV2BindingError("CAL_V2_COMPARATOR_MISMATCH")
    context_lock_path = root / "artifacts/ECG_HR_CONTEXT_V2.lock.json"
    context_lock = json.loads(context_lock_path.read_text(encoding="utf-8"))
    if config["ecg_hr_context"]["id"] != "ECG_HR_CONTEXT_V2" or config["ecg_hr_context"][
            "lock_sha256"] != _sha256(context_lock_path):
        raise AlertPolicyV2BindingError("ECG_HR_CONTEXT_BINDING_MISMATCH")
    if context_lock["selected_candidate"] != "WFDB_XQRS_V1":
        raise AlertPolicyV2BindingError("ECG_HR_CONTEXT_ESTIMATOR_MISMATCH")
    return AlertPolicy(
        policy_id=config["policy_id"],
        threshold=float(cal["threshold"]),
        threshold_comparator=config["threshold"]["comparator"],
        required_open=int(config["open"]["required_consecutive_valid_above"]),
        required_close=int(config["close"]["required_consecutive_valid_below"]),
        cooldown_us=int(config["cooldown_seconds"] * 1_000_000),
        disagreement_tolerance_bpm=float(config["rate_consistency"]["tolerance_bpm"]),
        disagreement_duration_us=int(
            config["rate_consistency"]["continuous_duration_seconds"] * 1_000_000),
        model_id=cal["model_id"],
        calibration_id=cal["calibration_id"],
        ecg_hr_context_id=config["ecg_hr_context"]["id"],
    )


def binding_payload(root: Path = ROOT) -> dict[str, Any]:
    policy = load_alert_policy_v2_binding(root)
    return {
        "binding_id": BINDING_ID,
        "policy_id": policy.policy_id,
        "policy_changed": False,
        "new_clinical_policy": False,
        "alert_policy_v1_config_sha256": _sha256(root / "configs/alert_policy_v1.yaml"),
        "alert_policy_v1_lock_sha256": _sha256(root / "artifacts/ALERT_POLICY_V1.lock.json"),
        "episode_manager_sha256": _sha256(root / "fusion/episode_manager.py"),
        "state_machine_sha256": _sha256(root / "fusion/state_machine.py"),
        "threshold_source": "CAL_V2",
        "cal_v2_sha256": _sha256(root / "artifacts/CAL_V2.json"),
        "threshold": policy.threshold,
        "threshold_comparator": policy.threshold_comparator,
        "model_id": policy.model_id,
        "calibration_id": policy.calibration_id,
        "required_consecutive_valid_above": policy.required_open,
        "required_consecutive_valid_below": policy.required_close,
        "cooldown_seconds": policy.cooldown_us // 1_000_000,
        "hr_disagreement_tolerance_bpm": policy.disagreement_tolerance_bpm,
        "hr_disagreement_duration_seconds": policy.disagreement_duration_us // 1_000_000,
        "ecg_hr_context_id": policy.ecg_hr_context_id,
    }


__all__ = ["BINDING_ID", "AlertPolicyV2BindingError", "binding_payload",
           "load_alert_policy_v2_binding"]
