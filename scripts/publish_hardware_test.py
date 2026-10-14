# ruff: noqa: E501
"""Insert bounded, explicitly synthetic telemetry into isolated Atlas test collection.

Usage: NHM_HARDWARE_MONGO_URI=... python3 -m scripts.publish_hardware_test --count 20
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import UTC, datetime

from pymongo import MongoClient

COLLECTION = "nhm_integration_test"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--interval", type=float, default=0.05)
    args = parser.parse_args()
    if not 1 <= args.count <= 200 or not 0 <= args.interval <= 5:
        parser.error("count must be 1..200 and interval 0..5 seconds")
    uri = os.environ.get("NHM_HARDWARE_MONGO_URI")
    if not uri:
        parser.error("NHM_HARDWARE_MONGO_URI is required")
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    collection = client["health_db"][COLLECTION]
    for i in range(args.count):
        reading = {
            "bpm": 68 + i % 14,
            "spo2": 96 + i % 3,
            "ecg": 1900 + ((i * 73) % 400),
            "timestamp": datetime.now(UTC),
            "source": "NHM_SYNTHETIC_INTEGRATION_TEST",
        }
        result = collection.insert_one(reading)
        print(
            f"{result.inserted_id} ecg={reading['ecg']} bpm={reading['bpm']} spo2={reading['spo2']}",
            flush=True,
        )
        time.sleep(args.interval)
    client.close()


if __name__ == "__main__":
    main()
