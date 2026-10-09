# ruff: noqa: E501
"""Identities and fixed policy strings of the live evaluation (constants only)."""

from fl10 import PROTOCOL_ID

EVAL_PROTOCOL_ID = PROTOCOL_ID                        # NHM_FL10_SYNTHETIC_EVALUATION_V1 (unchanged protocol bytes, same fixed threshold 0.5, no calibration)
OBSERVER_ID = "NHM_STUDIO_LIVE_EVALUATION_OBSERVER_V1"
RECORD_SCHEMA = "STUDIO_ROUND_EVALUATION_V1"
COHORT_USE_LABEL = "REUSED SYNTHETIC DIAGNOSTIC EVALUATION — NOT A NEW UNTOUCHED FINAL TEST"
COHORT_USE_DETAIL = ("The 16-participant FL10 holdout was already examined by NHM_FL10_001 (and the 8-participant showcase holdout by NHM_FINAL_SHOWCASE_001). "
                     "Live per-round scores on it are diagnostic: no round, threshold or candidate is selected from them, and repeated viewing is not independent statistical confirmation.")
CLAIM_BOUNDARY = "SYNTHETIC_ENGINEERING_EVENT_EVALUATION_ONLY_NOT_AAMI_SVF_OR_CLINICAL"
RUN_LENGTHS = (3, 10)
STATUSES = ("QUEUED", "EVALUATING", "COMPLETED", "FAILED")
MAX_QUEUE = 64
FL10_LOCK = "artifacts/fl10/NHM_FL10_001.lock.json"
