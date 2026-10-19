# ruff: noqa: E501
"""Writes (or verifies) ``configs/realistic/realistic_cohort_manifest_v3.json``: the per-participant dataset digests of the realistic cohort with recorded NSTDB noise, plus the official digests of the noise records.

    PYTHONPATH=src:. python -m scripts.pin_realistic_cohort_v3 [--verify]

Pinning is a one-time act; a later run only verifies. The note records the order of events honestly: the cohort was looked at once (central V2, the round-50 federated checkpoint, an untrained model and two logistic baselines)
BEFORE this pin, and no generator parameter was changed after that look."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation import fl_cohort_realistic_v3 as c

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/realistic/realistic_cohort_manifest_v3.json"
PIN_NOTE = ("Realistic cohort with RECORDED noise (NSTDB bw, em, ma at NSTDB's documented SNR levels). The SNR levels and their probabilities, the noise power shares, the training/evaluation noise regions and the annotation-noise "
            "parameters were fixed in simulation/realistic_ecg_v3.py before any model saw this cohort. The cohort was then looked at ONCE, before this pin: on the 16 evaluation participants (1,446 windows, 129 positive) "
            "the central MODEL_V2_FINAL scored AUROC 0.949 / AUPRC 0.900, the V2-FL-001 round-50 checkpoint 0.971 / 0.906, the untrained FL_INIT_V2 0.610 / 0.316, an amplitude logistic 0.816 / 0.671 and a beat-timing logistic "
            "0.918 / 0.888. No parameter was changed after that look, so the cohort is fresh, not untouched. Its difficulty is whatever the recorded noise at NSTDB's levels produces; it was not tuned to make any model look better or worse.")


def build() -> dict:
    train_ds = [c.build_dataset(p) for p in c.train_profiles()]
    eval_ds = [c.build_dataset(p) for p in c.eval_profiles()]
    return {"pin_note": PIN_NOTE, "pinned_before_any_model_scoring": False, "train": c.build_manifest(c.COHORT_ID, c.train_profiles(), train_ds), "eval": c.build_manifest(c.EVAL_COHORT_ID, c.eval_profiles(), eval_ds)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    built = build()
    if args.verify or MANIFEST.exists():
        pinned = json.loads(MANIFEST.read_text())
        same = all([e["dataset_sha256"] for e in pinned[t]["participants"]] == [e["dataset_sha256"] for e in built[t]["participants"]] for t in ("train", "eval"))
        print("VERIFIED" if same else "DRIFT")
        return 0 if same else 1
    MANIFEST.write_text(json.dumps(built, indent=1, sort_keys=True) + "\n")
    print("wrote", MANIFEST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
