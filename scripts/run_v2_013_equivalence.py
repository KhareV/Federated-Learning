#!/usr/bin/env python3
"""V2-013 Sections 11/12/13: API_RUNTIME_V2 numerical + semantic equivalence against an
independently computed canonical reference, and API contract/schema/error/vocabulary
compatibility. Synthetic fixtures only; no scientific metric; no held-out data."""

from __future__ import annotations

import json

import httpx
import numpy as np

import scripts._v2_013_lib as lib
from deployment import gateway_v2 as gw
from fusion.episode_manager import AlertEpisodeManager
from fusion.state_machine import FusionObservation
from preprocessing.ecg_hr_context import estimate_hr
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore

ROOT = lib.ROOT
OUT = lib.OUT
TOL = 1e-12
SESSION_PPG = "V2-013-EQUIV-PPG"
SESSION_NOPPG = "V2-013-EQUIV-NOPPG"
FORBIDDEN_TOKENS = ("ARRHYTHMIA", "AFIB", "DISEASE", "DIAGNOSIS", "EMERGENCY", "CARDIAC_EVENT",
                    "RISK_SCORE")
VOCABULARY = {"NORMAL_MONITORED_PATTERN", "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
              "RECHECK_SENSOR", "CONTEXT_UNAVAILABLE", "SYSTEM_ERROR"}


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def equivalence() -> dict:
    windows = lib.synthetic_api_windows(300)
    logits = lib.reference_raw_logits(windows)
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    ref = gw.calibrate_logits(logits, cal)
    policy = lib.independent_policy()
    managers = {SESSION_PPG: AlertEpisodeManager(policy),
                SESSION_NOPPG: AlertEpisodeManager(policy)}

    rows = []
    with lib.launch_api("v2") as (base, _pid), httpx.Client() as client:
        for i, window in enumerate(windows):
            with_ppg = i >= 200
            session = SESSION_PPG if with_ppg else SESSION_NOPPG
            ts = 10_000_000 + (i % 200 if not with_ppg else i - 200) * 5_000_000
            ppg = lib.PPG_CONTEXT if with_ppg else None
            samples = window.tolist()
            status, body = lib.post(client, base, lib.request_body(
                session, ts, samples, quality="VALID", model_id=lib.V2_MODEL_ID, ppg_context=ppg))
            hr = estimate_hr(np.asarray(samples, dtype=np.float64), timestamp_us=ts,
                             candidate_id="WFDB_XQRS_V1")
            observation = FusionObservation(
                session_id=session, timestamp_us=ts,
                source_domain_calibrated_probability=float(ref["calibrated_probability"][i]),
                ecg_quality="VALID", ppg_quality=ppg["quality"] if ppg else None,
                spo2_pct=ppg["spo2_pct"] if ppg else None,
                spo2_valid=bool(ppg["spo2_valid"]) if ppg else False,
                hr_ecg_bpm=hr.hr_ecg_bpm, hr_ecg_valid=hr.valid,
                pr_ppg_bpm=ppg["pr_bpm"] if ppg else None, pr_ppg_valid=bool(ppg),
                model_id="MODEL_V2_FINAL", calibration_id="CAL_V2")
            decision = managers[session].process(observation)
            rows.append((status, body, i, decision))

    n = len(rows)
    finite = sum(1 for s, b, *_ in rows if s == 200 and all(
        np.isfinite(b[k]) for k in ("raw_probability", "source_domain_calibrated_probability")))
    d_raw = max(abs(b["raw_probability"] - float(ref["raw_probability"][i]))
                for s, b, i, _ in rows)
    d_cal = max(abs(b["source_domain_calibrated_probability"]
                    - float(ref["calibrated_probability"][i])) for s, b, i, _ in rows)
    decision_agree = sum(
        int((b["source_domain_calibrated_probability"] >= cal["threshold"])
            == bool(ref["prediction"][i])) for s, b, i, _ in rows)
    state_agree = sum(int(b["monitoring_state"] == d.monitoring_state) for s, b, i, d in rows)
    ids = {
        "model_id": all(b["model_id"] == "MODEL_V2_FINAL" for s, b, *_ in rows),
        "calibration_id": all(b["calibration_id"] == cal["calibration_id"] for s, b, *_ in rows),
        "calibration_domain": all(b["calibration_domain"] == cal["calibration_domain"]
                                  for s, b, *_ in rows),
        "calibration_patient_count": all(
            b["calibration_patient_count"] == cal["calibration_patient_count"]
            for s, b, *_ in rows),
        "preprocess_version": all(b["preprocess_version"] == "PREPROC_V1" for s, b, *_ in rows),
        "contract_version": all(b["contract_version"] == "API_SCHEMA_V1" for s, b, *_ in rows),
        "alert_policy_id": all(b["alert_policy_id"] == "ALERT_POLICY_V1" for s, b, *_ in rows),
        "threshold": all(b["threshold"] == cal["threshold"] for s, b, *_ in rows),
        "target": all(b["target"] == "AAMI_SVF_WINDOW_V1" for s, b, *_ in rows),
    }
    # in-process raw-logit comparison (not observable over HTTP)
    from api.runtime_v2 import ResearchRuntimeV2

    runtime = ResearchRuntimeV2(verify="manifest")
    runtime_logits = []
    for window in windows:
        x = normalize_window_zscore(window, epsilon=NORMALIZATION_EPSILON)
        result = runtime.gateway.infer(x.astype(np.float32).reshape(1, 1, -1))
        runtime_logits.append(result.raw_logit)
    d_logit = float(np.max(np.abs(np.asarray(runtime_logits) - logits)))
    ok = (n == 300 and finite == n and d_raw <= TOL and d_cal <= TOL and decision_agree == n
          and state_agree == n and all(ids.values()) and d_logit <= TOL
          and all(s == 200 for s, *_ in rows))
    data = {
        "request_count": n,
        "http_200_count": sum(1 for s, *_ in rows if s == 200),
        "finite_output_count": finite,
        "sessions": {"without_ppg_context": 200, "with_valid_ppg_context": 100},
        "reference": ("locked per-window z-score -> frozen TorchScript artifact loaded directly -> "
                      "canonical CAL_V2 helpers -> independent AlertEpisodeManager with LITERAL "
                      "K=2/M=2/cooldown=30 s and CAL_V2's threshold"),
        "max_raw_logit_delta_in_process_gateway": d_logit,
        "raw_logit_observable_over_http": False,
        "max_raw_probability_delta": d_raw,
        "max_calibrated_probability_delta": d_cal,
        "threshold_decision_agreement": decision_agree / n,
        "monitoring_state_agreement": state_agree / n,
        "identity_and_version_agreement": ids,
        "tolerance": TOL,
        "scientific_metrics_reported": False,
        "api_process": "fresh uvicorn process (explicit V2 research profile)",
        "status": "PASS" if ok else "FAIL",
    }
    _write("api_runtime_equivalence.json", data)
    if not ok:
        raise RuntimeError("V2_013_API_EQUIVALENCE_FAILED")
    return data


def _identifier_strings(node, out: list[str] | None = None) -> list[str]:
    """Property names and enum values only (NOT free-text descriptions, where a negated
    'no diagnosis field' disclaimer is legitimate)."""
    out = [] if out is None else out
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                out.extend(value)
            if key == "enum" and isinstance(value, list):
                out.extend(str(v) for v in value)
            _identifier_strings(value, out)
    elif isinstance(node, list):
        for item in node:
            _identifier_strings(item, out)
    return out


def _scan_tokens(value) -> list[str]:
    identifiers = [s.upper() for s in _identifier_strings(value)]
    hits = [token for token in FORBIDDEN_TOKENS for ident in identifiers if token in ident]
    hits += ["AF" for ident in identifiers if ident == "AF"]
    return sorted(set(hits))


def schema_compatibility() -> dict:
    from fastapi.testclient import TestClient

    from api.app_v2 import create_research_app
    from api.runtime_v2 import ResearchRuntimeV2

    frozen = json.loads((ROOT / "contracts/openapi_v1.json").read_text())
    runtime = ResearchRuntimeV2(verify="manifest")
    app = create_research_app(runtime=runtime)
    live = json.loads(json.dumps(app.openapi()))
    comparable = {k: v for k, v in live.items() if k != "info"}
    frozen_cmp = {k: v for k, v in frozen.items() if k != "info"}
    openapi_identical = comparable == frozen_cmp and live["info"]["version"] == frozen["info"][
        "version"]
    states = set(live["components"]["schemas"]["MonitoringState"]["enum"])
    client = TestClient(app, raise_server_exceptions=False)
    window = lib.synthetic_api_windows(10)[9]
    base_body = lib.request_body("V2-013-SCHEMA", 10_000_000, window.tolist(), quality="VALID",
                                 model_id=lib.V2_MODEL_ID)

    def post(body: dict):
        r = client.post(lib.ROUTE, json=body)
        return r.status_code, r.json()

    cases: dict[str, dict] = {}
    s, b = post(base_body)
    cases["200_valid"] = {"status": s, "model_id": b.get("model_id")}
    s, b = post({**base_body, "timestamp_us": 15_000_000, "model_id": "MODEL_V1"})
    cases["400_wrong_model_id"] = {"status": s, "error_type": b.get("error_type")}
    s, b = post({k: v for k, v in base_body.items() if k != "ecg"})
    cases["400_schema_error"] = {"status": s, "error_type": b.get("error_type")}
    s, b = post({**base_body, "timestamp_us": 10_000_000})
    cases["400_non_monotonic"] = {"status": s, "error_type": b.get("error_type")}
    calls_before = runtime.gateway.model is not None
    del calls_before
    unusable_body = lib.request_body("V2-013-SCHEMA", 20_000_000, window.tolist(),
                                     quality="UNUSABLE", model_id=lib.V2_MODEL_ID)
    infer_calls = {"n": 0}
    original = runtime.infer

    def counting(samples):
        infer_calls["n"] += 1
        return original(samples)

    runtime.infer = counting  # type: ignore[method-assign]
    s, b = post(unusable_body)
    cases["422_unusable"] = {"status": s, "error_type": b.get("error_type"),
                             "model_executed": infer_calls["n"] > 0}
    s, b = post(lib.request_body("V2-013-SCHEMA", 25_000_000, window.tolist()[:2499],
                                 quality="VALID", model_id=lib.V2_MODEL_ID))
    cases["422_incomplete"] = {"status": s, "error_type": b.get("error_type"),
                               "model_executed": infer_calls["n"] > 0}

    def boom(samples):
        raise RuntimeError("scripted internal failure")

    runtime.infer = boom  # type: ignore[method-assign]
    s, b = post(lib.request_body("V2-013-SCHEMA", 30_000_000, window.tolist(), quality="VALID",
                                 model_id=lib.V2_MODEL_ID))
    cases["500_internal"] = {"status": s, "error_type": b.get("error_type")}
    runtime.infer = original  # type: ignore[method-assign]

    ok = (
        openapi_identical and states == VOCABULARY and cases["200_valid"]["status"] == 200
        and cases["400_wrong_model_id"] == {"status": 400, "error_type": "UNSUPPORTED_MODEL_ID"}
        and cases["400_schema_error"]["status"] == 400
        and cases["400_non_monotonic"] == {"status": 400, "error_type": "NON_MONOTONIC_TIMESTAMP"}
        and cases["422_unusable"]["status"] == 422 and not cases["422_unusable"]["model_executed"]
        and cases["422_incomplete"]["status"] == 422
        and not cases["422_incomplete"]["model_executed"]
        and cases["500_internal"]["status"] == 500
        and cases["500_internal"]["error_type"] == "INTERNAL_SERVER_ERROR"
    )
    hits = _scan_tokens(live["components"]["schemas"]) + _scan_tokens(sorted(states))
    data = {
        "contract_version": "API_SCHEMA_V1",
        "endpoint": lib.ROUTE,
        "new_http_contract_version_created": False,
        "openapi_semantically_identical_to_frozen_contract_ignoring_info_title_description": (
            openapi_identical),
        "info_version_identical": live["info"]["version"] == frozen["info"]["version"],
        "monitoring_state_vocabulary": sorted(states),
        "vocabulary_exactly_five_unchanged": states == VOCABULARY,
        "quality_warning_is_public_state": "QUALITY_WARNING" in states,
        "cases": cases,
        "diagnostic_wording_hits_in_schema_vocabulary": hits,
        "model_id_selection": "runtime-bound only; request model_id must equal the bound model; "
        "no query/header/checkpoint/threshold selector exists",
        "status": "PASS" if (ok and not hits) else "FAIL",
    }
    _write("api_schema_compatibility.json", data)
    if data["status"] != "PASS":
        raise RuntimeError("V2_013_API_SCHEMA_COMPATIBILITY_FAILED")
    return data


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    equivalence()
    schema_compatibility()
    print("V2-013 equivalence + schema compatibility complete")


if __name__ == "__main__":
    main()
