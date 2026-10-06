# ruff: noqa: E501
"""Claim audit of the faculty runbook: required statements must be present, and every occurrence of a watched
claim word must sit in an accurate negation/limitation (or be a quoted question / reviewed technical context)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs/capstone/FACULTY_DEMO_RUNBOOK_V1.md"
REQUIRED = {
    "accelerated_timing": "SIMULATION TIMING: ACCELERATED FOR PRESENTATION", "simulated_only_hardware": "SIMULATED_ONLY", "non_diagnostic": "non-diagnostic research monitor",
    "no_personal_model": "There is no personal model", "logical_one_laptop_fl": "eight logical synthetic partitions on one laptop", "secagg_narrow": "round 1 only",
    "candidate_not_deployed": "never automatically deployed", "short_path": "SHORT PATH", "full_path": "FULL PATH", "promotion_decision": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
    "release_decision": "SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED", "hardware_unverified": "VERIFICATION_REQUIRED", "mixed_hero": "MIXED_MONITORING_SESSION",
    "replay_no_training": "NO TRAINING IS EXECUTING", "not_a_release": "not a clean-machine release", "recovery_logs": "inference.log", "port_guidance": "PORT_IN_USE",
}
WATCHED = re.compile(r"hospital|clinical|diagnos\w*|secure\b|private\b|anonym\w*|differential privacy|\bdeployed\b|\bproduction\b|personal model|personali[sz]ed|physical wearable|real hardware|on-device|continuous learning|training in progress|is training", re.I)
NEGATION = re.compile(r"\bnon-\w+|\bnot\b|\bno\b|\bnever\b|\bnor\b|without|isn't|n't\b|neither", re.I)
TECHNICAL = re.compile(r"production frontend|production build", re.I)


def sentences(text: str) -> list[str]:
    plain = re.sub(r"```.*?```", " ", text, flags=re.S)
    plain = re.sub(r"[*`#>|]", " ", plain)
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+|\n+", plain) if s.strip()]


def audit_runbook(text: str) -> dict:
    missing = [k for k, phrase in REQUIRED.items() if phrase not in text]
    violations = []
    for sentence in sentences(text):
        if sentence.endswith("?"):
            continue  # a quoted faculty question, answered in the next sentences
        for match in WATCHED.finditer(sentence):
            if TECHNICAL.search(sentence) and match.group(0).lower() == "production":
                continue
            if not NEGATION.search(sentence):
                violations.append({"word": match.group(0), "sentence": sentence[:200]})
    return {"missing_required": missing, "unnegated_watched_claims": violations, "ok": not missing and not violations}
