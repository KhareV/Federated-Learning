"""UI waveform transport (PRODUCT_LIVE_EVENT_V1 ``waveform.chunk``) -- UI-ONLY, never scientific.

ObservedRecords are TEE'd at the coordinator: one branch feeds this chunker (360 Hz, ADC
counts), the
SAME records feed the unchanged WearableStreamRuntime (the scientific 250 Hz path). A chunk always
covers a fixed, contiguous block of sample-index positions. Positions with no delivered record (link
outage, dropped samples) or with ``ecg_raw is None`` are represented as ``None`` -- never 0, never a
held value, never interpolation -- and these placeholders exist ONLY in this UI transport.
"""

from __future__ import annotations

from dataclasses import dataclass

from product.events import WAVEFORM_MAX_SAMPLES_PER_CHUNK, WAVEFORM_SOURCE_RATE_HZ
from simulation.types import ObservedRecord

CHUNK_SAMPLES = 60  # 360 Hz / 60 = 6 waveform events per second (frozen CAP-003 policy)


@dataclass(frozen=True)
class WaveformChunk:
    first_sample_index: int
    first_sample_timestamp_us: int
    samples: tuple[int | None, ...]

    @property
    def null_count(self) -> int:
        return sum(1 for s in self.samples if s is None)


def timestamp_for_index(index: int) -> int:
    """Same rounding as the WEARABLE_SIM generator: round(index * 1e6 / 360)."""
    return round(index * 1_000_000 / WAVEFORM_SOURCE_RATE_HZ)


def index_for_timestamp(timestamp_us: int) -> int:
    return round(timestamp_us * WAVEFORM_SOURCE_RATE_HZ / 1_000_000)


class WaveformChunker:
    def __init__(self, chunk_samples: int = CHUNK_SAMPLES) -> None:
        if not 1 <= chunk_samples <= WAVEFORM_MAX_SAMPLES_PER_CHUNK:
            raise ValueError("CHUNK_SIZE_OUTSIDE_FROZEN_LIMITS")
        self._size = chunk_samples
        self._next_index = 0
        self._buffer: list[int | None] = []
        self._buffer_start = 0

    @property
    def next_index(self) -> int:
        return self._next_index

    def _push(self, value: int | None) -> list[WaveformChunk]:
        if not self._buffer:
            self._buffer_start = self._next_index
        self._buffer.append(value)
        self._next_index += 1
        if len(self._buffer) == self._size:
            return [self._take()]
        return []

    def _take(self) -> WaveformChunk:
        chunk = WaveformChunk(self._buffer_start, timestamp_for_index(self._buffer_start),
                              tuple(self._buffer))
        self._buffer = []
        return chunk

    def advance_to(self, index: int) -> list[WaveformChunk]:
        """Fill positions [next_index, index) with None (a known source gap), emitting chunks."""
        chunks: list[WaveformChunk] = []
        while self._next_index < index:
            chunks.extend(self._push(None))
        return chunks

    def add_record(self, record: ObservedRecord) -> list[WaveformChunk]:
        if record.sample_index < self._next_index:
            raise ValueError("NON_MONOTONIC_SAMPLE_INDEX")
        chunks = self.advance_to(record.sample_index)
        chunks.extend(self._push(record.ecg_raw))
        return chunks

    def flush(self) -> list[WaveformChunk]:
        return [self._take()] if self._buffer else []
