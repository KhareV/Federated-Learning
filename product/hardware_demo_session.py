"""A prerecorded DEMO hardware session: sketch-format documents in their own MongoDB collection, imported into History as a STOPPED hardware session.

Nothing here is a physical recording. The documents are generated (seeded, deterministic) by the same hyper-realistic ESP32/AD8232 signal model the rehearsal emulator uses
(``scripts.emulate_esp32_ws.Signal``, pattern ``sketch_real``, vitals ``sketch``): the exact document shape the supplied firmware's server stores (``bpm``, ``spo2``, ``ecg``, ``timestamp``), ~17 Hz arrival
with jitter and short network pauses, a settling period, and a finger on the sensor throughout. They live in a separate collection (never a ``records_YYYY-MM-DD`` collection), so live monitoring
never ingests them, and the imported session is named and labelled as a prerecorded demo: its id starts ``HW-SHOWCASE-`` and its collection is ``DEMO_COLLECTION``. It flows through every hardware path
(History, Observatory replay, tabular and pretrained-V2 federated runs) exactly as a recorded session does, which is the point."""

from __future__ import annotations

import functools
import hashlib
import random
from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId

DEMO_COLLECTION = "demo_prerecorded_hardware_session_v1"
DEMO_SEED = 20261017
DEMO_SECONDS = 300.0                      # 30 ten-second windows: enough for a pretrained-V2 run (16 train + 4 holdout) from this one session
DEMO_START = datetime(2026, 10, 17, 10, 0, 0, tzinfo=UTC)
SETTLE_SECONDS = 4.0                      # electrodes just applied: no finger yet (bpm/spo2 0, ECG still the lead-off placeholder)
FORBIDDEN_DATABASES = {"health_db"}       # the production database is never seeded by the script


LONG_DEMO_COLLECTION = "demo_prerecorded_hardware_session_long_v1"
LONG_DEMO_SEED = 20261018
LONG_DEMO_SECONDS = 480.0                 # about 93 complete 10 s windows (5 s stride), every one usable: 74 training + 19 holdout from this one session
LONG_DEMO_START = datetime(2026, 10, 17, 12, 0, 0, tzinfo=UTC)

# collection -> (session ordinal, seed, seconds, start, ObjectId tag); each prerecorded demo session lives in its own collection and is imported as its own HW-SHOWCASE-* session
SHOWCASES: dict[str, tuple[int, int, float, datetime, bytes]] = {
    DEMO_COLLECTION: (1, DEMO_SEED, DEMO_SECONDS, DEMO_START, b"DEMO1"),
    LONG_DEMO_COLLECTION: (2, LONG_DEMO_SEED, LONG_DEMO_SECONDS, LONG_DEMO_START, b"DEMO2"),
}


def generate_documents(seed: int = DEMO_SEED, seconds: float = DEMO_SECONDS, start: datetime = DEMO_START, tag: bytes = b"DEMO1") -> list[dict[str, Any]]:
    from scripts.emulate_esp32_ws import Signal

    rng = random.Random(seed ^ 0x5EED)
    signal = Signal(seed)
    docs: list[dict[str, Any]] = []
    t = 0.0
    counter = 0
    next_pause = rng.uniform(25.0, 45.0)
    while t < seconds:
        dt = max(0.052, rng.gauss(0.0585, 0.006))          # the sketch sends when more than 50 ms have passed; loop work and Wi-Fi add a few ms
        if t >= next_pause:                                 # short Render/Wi-Fi pause (kept under the 1 s bridging limit of the V2 resampler)
            dt += rng.uniform(0.25, 0.7)
            next_pause = t + rng.uniform(25.0, 45.0)
        t += dt
        signal.step(dt)
        settling = t < SETTLE_SECONDS
        bpm, spo2 = signal.vitals("sketch", settling)
        ecg = 2048 if settling else signal.ecg("sketch_real")
        stamp = start + timedelta(seconds=t)
        stamp = stamp.replace(microsecond=(stamp.microsecond // 1000) * 1000)
        counter += 1
        object_id = ObjectId(int(stamp.timestamp()).to_bytes(4, "big") + tag + counter.to_bytes(3, "big"))
        docs.append({"_id": object_id, "bpm": int(bpm), "spo2": int(spo2), "ecg": int(ecg), "timestamp": stamp})
    return docs


def documents_for(collection: str) -> list[dict[str, Any]]:
    _, seed, seconds, start, tag = SHOWCASES[collection]
    return generate_documents(seed, seconds, start, tag)


@functools.lru_cache(maxsize=None)
def expected_count(collection: str) -> int:
    """How many documents a complete showcase collection holds (the generator is deterministic), so a collection still being seeded is never imported half-written."""
    return len(documents_for(collection))


def owner_session_id(owner: str, collection: str = DEMO_COLLECTION) -> str:
    ordinal, _, _, start, _ = SHOWCASES[collection]
    return f"HW-SHOWCASE-{start:%Y-%m-%d}-{ordinal:02d}-" + hashlib.sha256(owner.encode()).hexdigest()[:8]
