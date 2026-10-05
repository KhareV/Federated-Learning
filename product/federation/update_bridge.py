# ruff: noqa: E501
"""CAPSTONE_FL_UPDATE_BRIDGE_V1 -- exposes the EXISTING V2 update envelope to the future coordinator.

No new envelope schema exists: the envelope is exactly ``federated.wearable_fl_system_v1.make_envelope``
output (ENVELOPE_FIELDS + payload.delta). Every export is re-verified: zero forbidden raw/label/truth
findings (``scan_forbidden`` on the real object structure), digest reconciled with the payload, delta keys /
shapes / dtypes equal to the base state, floating deltas finite, integer buffers zero.

Distinction: ``FLClient.produce_update()`` is the metadata projection; this bridge hands out the full
envelope (with the model delta) for CAP-007. Neither contains training examples. CAP-006 never calls a
coordinator from here.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from federated.wearable_fl_system_v1 import (
    ENVELOPE_FIELDS,
    PAYLOAD_FIELD,
    delta_sha,
    scan_forbidden,
)
from product.federation.base import UpdateSubmission
from product.federation.client import CapstoneFlClientAdapterV1, ClientError

BRIDGE_ID = "CAPSTONE_FL_UPDATE_BRIDGE_V1"
SUBMISSION_FIELD_MAP = {"client_id": "client_id", "round_id": "round_id",
                        "base_state_digest": "base_global_state_sha256",
                        "update_digest": "update_sha256", "examples_seen": "examples_seen"}


def submission_from_envelope(envelope: dict[str, Any]) -> UpdateSubmission:
    return UpdateSubmission(**{product: envelope[existing]
                               for product, existing in SUBMISSION_FIELD_MAP.items()})


def validate_envelope(envelope: dict[str, Any], base_state: dict[str, np.ndarray]) -> dict[str, Any]:
    forbidden = scan_forbidden(envelope)
    delta = envelope[PAYLOAD_FIELD]["delta"]
    keys_ok = list(delta) == list(base_state)
    shapes_ok = keys_ok and all(np.asarray(delta[k]).shape == np.asarray(base_state[k]).shape
                                for k in base_state)
    dtypes_ok = keys_ok and all(np.asarray(delta[k]).dtype == np.asarray(base_state[k]).dtype
                                for k in base_state)
    floating = [k for k, v in delta.items() if np.issubdtype(np.asarray(v).dtype, np.floating)]
    finite = all(bool(np.isfinite(delta[k]).all()) for k in floating)
    integer_zero = all(not np.any(delta[k]) for k in delta if k not in floating)
    return {"forbidden_findings": forbidden, "envelope_fields_exact": sorted(
        k for k in envelope if k != PAYLOAD_FIELD) == sorted(ENVELOPE_FIELDS),
        "keys_match_base": keys_ok, "shapes_match_base": shapes_ok, "dtypes_match_base": dtypes_ok,
        "floating_tensors": len(floating), "integer_buffers": len(delta) - len(floating),
        "all_floating_finite": finite, "integer_buffers_zero_delta": integer_zero,
        "update_digest_matches_payload": delta_sha(delta) == envelope["update_sha256"],
        "examples_seen_positive": envelope["examples_seen"] > 0,
        "engineering_only": envelope["engineering_only"] is True}


def export_envelope(client: CapstoneFlClientAdapterV1,
                    base_state: dict[str, np.ndarray]) -> tuple[dict[str, Any], dict[str, Any]]:
    envelope = client._envelope_for_bridge()
    report = validate_envelope(envelope, base_state)
    ok = (not report["forbidden_findings"] and report["envelope_fields_exact"]
          and report["keys_match_base"] and report["shapes_match_base"] and report["dtypes_match_base"]
          and report["all_floating_finite"] and report["integer_buffers_zero_delta"]
          and report["update_digest_matches_payload"] and report["examples_seen_positive"])
    if not ok:
        raise ClientError("UPDATE_ENVELOPE_INVALID")
    return envelope, report
