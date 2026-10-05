"""CAPSTONE_WAVEFORM_PREVIEW_V1 -- bounded ECG preview for FUTURE session-history visualisation.

It is NOT the raw stream. Samples are folded into fixed buckets (``decimation_factor`` source
samples each, chosen so that at most ``MAX_POINTS`` points can exist); each bucket stores the
delivered sample with the largest deviation from the bucket mean (deterministic, first wins ties),
and a bucket with no delivered sample is ``null`` - never 0, never held, never interpolated.
Encoded as JSON_ZLIB_V1 (zlib-compressed JSON array of int|null). The preview is never read by
the scientific runtime or by inference.
"""

from __future__ import annotations

import json
import math
import zlib
from typing import Any

MAX_POINTS = 4000
ENCODING = "JSON_ZLIB_V1"
CHANNEL = "ECG"
SOURCE_RATE_HZ = 360


def decimation_factor_for(total_samples: int, max_points: int = MAX_POINTS) -> int:
    return max(1, math.ceil(total_samples / max_points))


def encode(points: list[int | None]) -> bytes:
    return zlib.compress(json.dumps(points, separators=(",", ":")).encode(), 9)


def decode(blob: bytes) -> list[int | None]:
    return json.loads(zlib.decompress(blob))


class PreviewAccumulator:
    def __init__(self, total_samples: int, max_points: int = MAX_POINTS) -> None:
        self.factor = decimation_factor_for(total_samples, max_points)
        self.max_points = max_points
        self.points: list[int | None] = []
        self.start_timestamp_us: int | None = None
        self.source_samples_seen = 0
        self._bucket = -1
        self._values: list[int] = []

    def _close_bucket(self) -> None:
        if self._bucket < 0:
            return
        if self._values:
            mean = sum(self._values) / len(self._values)
            chosen = max(self._values, key=lambda v: abs(v - mean))  # first max wins ties
            self.points.append(chosen)
        else:
            self.points.append(None)
        self._values = []

    def add_chunk(self, first_index: int, first_timestamp_us: int,
                  samples: list[int | None]) -> None:
        if self.start_timestamp_us is None:
            self.start_timestamp_us = first_timestamp_us
        for offset, sample in enumerate(samples):
            index = first_index + offset
            bucket = index // self.factor
            while self._bucket < bucket:  # also closes buckets that were entirely a gap
                self._close_bucket()
                self._bucket += 1
            if sample is not None:
                self._values.append(sample)
        self.source_samples_seen += len(samples)

    def finish(self) -> list[int | None]:
        self._close_bucket()
        self._bucket = -1
        if len(self.points) > self.max_points:
            raise ValueError("PREVIEW_EXCEEDS_BOUND")
        return self.points

    def describe(self) -> dict[str, Any]:
        return {"channel": CHANNEL, "source_rate_hz": SOURCE_RATE_HZ,
                "decimation_factor": self.factor, "point_count": len(self.points),
                "max_points": self.max_points, "source_samples_seen": self.source_samples_seen,
                "null_points": sum(1 for p in self.points if p is None),
                "encoding": ENCODING}
