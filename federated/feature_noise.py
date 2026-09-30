"""Fixed deterministic NSTDB feature-noise transform for T026."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import wfdb

from evaluation.noise import _preprocess
from federated.client_manifest import SITE_IDS
from nhm.hashing import hash_bytes, hash_file
from preprocessing.windowing import NORMALIZATION_EPSILON

NOISE_SCHEDULE = {
    "SITE_00": ("bw", 24.0),
    "SITE_01": ("em", 24.0),
    "SITE_02": ("ma", 18.0),
    "SITE_03": ("bw", 12.0),
    "SITE_04": ("em", 6.0),
    "SITE_05": ("ma", 0.0),
    "SITE_06": ("bw", -6.0),
    "SITE_07": ("em", -6.0),
}


def build_noise_bank(root: Path) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    bank: dict[str, np.ndarray] = {}
    audit: dict[str, Any] = {}
    raw = root / "data/raw/nstdb/1.0.0"
    for record_id in ("bw", "em", "ma"):
        record = wfdb.rdrecord(str(raw / record_id), physical=True)
        signal = np.asarray(record.p_signal[:, 0], dtype=np.float64)
        filtered = np.ascontiguousarray(_preprocess(signal), dtype=np.float64)
        if filtered.size < 2500 or not np.isfinite(filtered).all():
            raise RuntimeError("NSTDB_NOISE_BANK_INVALID")
        bank[record_id] = filtered
        audit[record_id] = {
            "dataset": "NSTDB",
            "version": "1.0.0",
            "source_record": record_id,
            "source_dat_sha256": hash_file(raw / f"{record_id}.dat"),
            "source_header_sha256": hash_file(raw / f"{record_id}.hea"),
            "source_rate_hz": 360,
            "result_rate_hz": 250,
            "preprocess_id": "PREPROC_V1_MITDB_360_TO_250_CAUSAL_PATH",
            "samples": int(filtered.size),
            "result_sha256": hash_bytes(filtered.tobytes()),
        }
    return bank, audit


def noise_offset(site_id: str, example_id: str, source: str, length: int) -> int:
    material = f"FL_FEATURE_NOISE_V1|{site_id}|{example_id}|{source}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big") % (length - 2500 + 1)


def mix_noise(clean: np.ndarray, noise: np.ndarray, snr_db: float) -> tuple[np.ndarray, float]:
    clean = np.asarray(clean, dtype=np.float64)
    noise = np.asarray(noise, dtype=np.float64)
    signal_rms = float(np.sqrt(np.mean(clean**2)))
    noise_rms = float(np.sqrt(np.mean(noise**2)))
    if not (signal_rms > 0 and noise_rms > 0 and np.isfinite([signal_rms, noise_rms]).all()):
        raise ValueError("finite positive RMS required")
    scale = signal_rms / (noise_rms * 10 ** (snr_db / 20))
    scaled = scale * noise
    achieved = 20 * np.log10(signal_rms / np.sqrt(np.mean(scaled**2)))
    return np.ascontiguousarray(clean + scaled), float(achieved)


def transform_population(
    clean_windows: np.ndarray,
    example_ids: np.ndarray,
    site_for_example: dict[str, str],
    bank: dict[str, np.ndarray],
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    result = np.empty((clean_windows.shape[0], 1, 2500), dtype=np.float32)
    fixtures: list[dict[str, Any]] = []
    seen = set()
    for index, (clean, example_id) in enumerate(zip(clean_windows, example_ids, strict=True)):
        site = site_for_example[str(example_id)]
        source, target = NOISE_SCHEDULE[site]
        offset = noise_offset(site, str(example_id), source, bank[source].size)
        noisy, achieved = mix_noise(clean, bank[source][offset : offset + 2500], target)
        mean, std = float(np.mean(noisy)), float(np.std(noisy))
        result[index, 0] = ((noisy - mean) / (std + NORMALIZATION_EPSILON)).astype(np.float32)
        if site not in seen:
            fixtures.append(
                {
                    "site_id": site,
                    "example_id": str(example_id),
                    "noise_source": source,
                    "target_snr_db": target,
                    "achieved_snr_db": achieved,
                    "offset": offset,
                    "clean_sha256": hash_bytes(np.ascontiguousarray(clean).tobytes()),
                    "noisy_sha256": hash_bytes(noisy.tobytes()),
                    "absolute_error_db": abs(achieved - target),
                    "status": "PASS" if abs(achieved - target) <= 0.05 else "FAIL",
                }
            )
            seen.add(site)
    if set(seen) != set(SITE_IDS):
        raise RuntimeError("missing feature-noise fixture site")
    return result, sorted(fixtures, key=lambda row: row["site_id"])
