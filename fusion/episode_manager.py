"""Deterministic temporal engine for ALERT_POLICY_V1."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fusion.state_machine import (
    FusionDecision,
    FusionObservation,
    QualityState,
    WindowSignal,
    context_available,
    public_monitoring_state,
    validate_observation,
    window_signal,
)

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class AlertPolicy:
    policy_id: str
    threshold: float
    threshold_comparator: str
    required_open: int
    required_close: int
    cooldown_us: int
    disagreement_tolerance_bpm: float
    disagreement_duration_us: int
    model_id: str
    calibration_id: str
    ecg_hr_context_id: str


def load_alert_policy(root: Path = ROOT) -> AlertPolicy:
    config_path = root / "configs/alert_policy_v1.yaml"
    config: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    cal_path = root / "artifacts/CAL_V1.json"
    cal = json.loads(cal_path.read_text(encoding="utf-8"))
    context_lock_path = root / "artifacts/ECG_HR_CONTEXT_V2.lock.json"
    context_lock = json.loads(context_lock_path.read_text(encoding="utf-8"))
    required = {
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
    observed = {
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
    if observed != required:
        raise ValueError("ALERT_POLICY_V1_CONFIG_MISMATCH")
    if config["threshold"]["source"] != "CAL_V1":
        raise ValueError("ALERT_POLICY_V1_THRESHOLD_SOURCE_MISMATCH")
    if config["ecg_hr_context"]["id"] != "ECG_HR_CONTEXT_V2":
        raise ValueError("ALERT_POLICY_V1_CONTEXT_ID_MISMATCH")
    if config["ecg_hr_context"]["lock_sha256"] != _sha256(context_lock_path):
        raise ValueError("ALERT_POLICY_V1_CONTEXT_HASH_MISMATCH")
    if context_lock["selected_candidate"] != "WFDB_XQRS_V1":
        raise ValueError("ALERT_POLICY_V1_CONTEXT_ESTIMATOR_MISMATCH")
    return AlertPolicy(
        policy_id=config["policy_id"],
        threshold=float(cal["threshold"]),
        threshold_comparator=config["threshold"]["comparator"],
        required_open=int(config["open"]["required_consecutive_valid_above"]),
        required_close=int(config["close"]["required_consecutive_valid_below"]),
        cooldown_us=int(config["cooldown_seconds"] * 1_000_000),
        disagreement_tolerance_bpm=float(config["rate_consistency"]["tolerance_bpm"]),
        disagreement_duration_us=int(
            config["rate_consistency"]["continuous_duration_seconds"] * 1_000_000
        ),
        model_id=cal["model_id"],
        calibration_id=cal["calibration_id"],
        ecg_hr_context_id=config["ecg_hr_context"]["id"],
    )


def policy_lock_payload(root: Path = ROOT) -> dict[str, Any]:
    policy = load_alert_policy(root)
    config_path = root / "configs/alert_policy_v1.yaml"
    state_path = root / "fusion/state_machine.py"
    episode_path = root / "fusion/episode_manager.py"
    cal_path = root / "artifacts/CAL_V1.json"
    context_path = root / "artifacts/ECG_HR_CONTEXT_V2.lock.json"
    config: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return {
        "policy_id": policy.policy_id,
        "status": "FROZEN_ENGINEERING_POLICY",
        "config_sha256": _sha256(config_path),
        "state_machine_sha256": _sha256(state_path),
        "episode_manager_sha256": _sha256(episode_path),
        "CAL_V1_sha256": _sha256(cal_path),
        "threshold_source": "CAL_V1",
        "threshold": policy.threshold,
        "threshold_comparator": policy.threshold_comparator,
        "ECG_HR_CONTEXT_V2_sha256": _sha256(context_path),
        "ecg_hr_context_id": policy.ecg_hr_context_id,
        "required_consecutive_valid_above": policy.required_open,
        "required_consecutive_valid_below": policy.required_close,
        "cooldown_seconds": policy.cooldown_us // 1_000_000,
        "hr_disagreement_tolerance_bpm": policy.disagreement_tolerance_bpm,
        "hr_disagreement_duration_seconds": policy.disagreement_duration_us // 1_000_000,
        "monitoring_state_vocabulary": config["monitoring_state_vocabulary"],
        "state_precedence": config["state_precedence"],
        "change_control": config["change_control"],
    }


def verify_alert_policy_lock(root: Path = ROOT, *, lock_path: Path | None = None) -> dict[str, Any]:
    path = lock_path or root / "artifacts/ALERT_POLICY_V1.lock.json"
    observed = json.loads(path.read_text(encoding="utf-8"))
    expected = policy_lock_payload(root)
    if observed != expected:
        raise ValueError("ALERT_POLICY_V1_LOCK_MISMATCH")
    return {
        "status": "PASS",
        "policy_id": expected["policy_id"],
        "config_sha256": expected["config_sha256"],
        "lock_sha256": _sha256(path),
        "threshold": expected["threshold"],
    }


class AlertEpisodeManager:
    def __init__(self, policy: AlertPolicy) -> None:
        self.policy = policy
        self._session_id: str | None = None
        self.reset()

    def reset(self, session_id: str | None = None) -> None:
        self._session_id = session_id
        self._last_timestamp_us: int | None = None
        self._episode_active = False
        self._open_counter = 0
        self._close_counter = 0
        self._episode_count = 0
        self._cooldown_until_us: int | None = None
        self._disagreement_started_at_us: int | None = None
        self._quality_warning = False

    def _validate_session(self, observation: FusionObservation) -> None:
        validate_observation(observation)
        if observation.model_id != self.policy.model_id:
            raise ValueError("MODEL_ID_MISMATCH")
        if observation.calibration_id != self.policy.calibration_id:
            raise ValueError("CALIBRATION_ID_MISMATCH")
        if self._session_id is None:
            self._session_id = observation.session_id
        elif observation.session_id != self._session_id:
            raise ValueError("SESSION_CHANGE_REQUIRES_EXPLICIT_RESET")
        if (
            self._last_timestamp_us is not None
            and observation.timestamp_us <= self._last_timestamp_us
        ):
            raise ValueError("NON_MONOTONIC_TIMESTAMP")

    def _update_rate_warning(self, observation: FusionObservation) -> None:
        comparable = (
            not observation.system_error
            and observation.hr_ecg_valid
            and observation.pr_ppg_valid
            and observation.hr_ecg_bpm is not None
            and observation.pr_ppg_bpm is not None
            and observation.ppg_quality not in (None, QualityState.UNUSABLE.value)
        )
        if not comparable:
            self._disagreement_started_at_us = None
            self._quality_warning = False
            return
        difference = abs(observation.hr_ecg_bpm - observation.pr_ppg_bpm)
        if difference <= self.policy.disagreement_tolerance_bpm:
            self._disagreement_started_at_us = None
            self._quality_warning = False
            return
        if self._disagreement_started_at_us is None:
            self._disagreement_started_at_us = observation.timestamp_us
        self._quality_warning = (
            observation.timestamp_us - self._disagreement_started_at_us
            >= self.policy.disagreement_duration_us
        )

    def process(self, observation: FusionObservation) -> FusionDecision:
        self._validate_session(observation)
        signal = window_signal(observation, self.policy.threshold)
        opened = False
        closed = False
        cooldown_active = (
            self._cooldown_until_us is not None
            and observation.timestamp_us < self._cooldown_until_us
        )

        if self._episode_active:
            self._open_counter = 0
            if signal is WindowSignal.VALID_BELOW_THRESHOLD:
                self._close_counter += 1
                if self._close_counter >= self.policy.required_close:
                    self._episode_active = False
                    closed = True
                    self._close_counter = 0
                    self._cooldown_until_us = observation.timestamp_us + self.policy.cooldown_us
                    cooldown_active = True
            else:
                self._close_counter = 0
        else:
            self._close_counter = 0
            if cooldown_active:
                self._open_counter = 0
            elif signal is WindowSignal.VALID_ABOVE_THRESHOLD:
                self._open_counter += 1
                if self._open_counter >= self.policy.required_open:
                    self._episode_active = True
                    opened = True
                    self._episode_count += 1
            else:
                self._open_counter = 0

        self._update_rate_warning(observation)
        has_context = context_available(observation)
        state, possible_pattern = public_monitoring_state(
            signal, episode_active=self._episode_active, has_context=has_context
        )
        self._last_timestamp_us = observation.timestamp_us
        return FusionDecision(
            timestamp_us=observation.timestamp_us,
            monitoring_state=state.value,
            window_signal=signal.value,
            episode_active=self._episode_active,
            episode_opened=opened,
            episode_closed=closed,
            episode_count=self._episode_count,
            open_counter=self._open_counter,
            close_counter=self._close_counter,
            cooldown_active=cooldown_active,
            cooldown_until_us=self._cooldown_until_us,
            possible_pattern=possible_pattern,
            context_available=has_context,
            quality_warning=self._quality_warning,
            quality_warning_reasons=(
                ("ECG_PPG_RATE_DISAGREEMENT",) if self._quality_warning else ()
            ),
            ecg_quality=observation.ecg_quality,
            ppg_quality=observation.ppg_quality,
            hr_ecg_bpm=observation.hr_ecg_bpm,
            pr_ppg_bpm=observation.pr_ppg_bpm,
            spo2_pct=observation.spo2_pct,
            spo2_valid=observation.spo2_valid,
            source_domain_calibrated_probability=(observation.source_domain_calibrated_probability),
            threshold=self.policy.threshold,
            alert_policy_id=self.policy.policy_id,
        )
