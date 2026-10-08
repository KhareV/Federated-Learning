# ruff: noqa: E501
"""NHM-FL10-001: opt-in 10-round synthetic engineering federated experiment (additive successor of NHM_FINAL_SHOWCASE_001).

Reuses, unchanged: federated.model_v2_fl.train_local_epoch_v2, federated.wearable_fl_system_v1.Coordinator (and its aggregate_weighted_deltas),
the canonical eight-client cohort, the frozen training constants, final_showcase.metrics, product.observatory/BatchCapture read-only hooks and the
verified live-SITE_00 link. Nothing here changes the 3-round product contract, a frozen scientific artifact or an accepted lock."""

from final_showcase import LANE_LABEL

LIVE_LABEL = "LIVE-MONITORED SIMULATED ECG — NOT A REAL PHYSIOLOGICAL PATIENT"
EXPERIMENT_ID = "NHM_FL10_SYNTHETIC_ENGINEERING_V1"
PROTOCOL_ID = "NHM_FL10_SYNTHETIC_EVALUATION_V1"
ROUNDS = 10
CLIENTS = 8
ENGINEERING_BANNER = LANE_LABEL
