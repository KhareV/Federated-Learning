# ruff: noqa: E501
"""Seed (or remove) the prerecorded DEMO hardware session in its own MongoDB collection.

The documents are generated, not recorded (see product/hardware_demo_session.py); they use the sketch's document shape so the demo can show a recorded-looking hardware session in MongoDB
without waiting for a live recording. Live monitoring never reads this collection (it is not a records_YYYY-MM-DD collection).

  NHM_HARDWARE_MONGO_URI=... python -m scripts.seed_demo_hardware_session --database nhm_rehearsal
  NHM_HARDWARE_MONGO_URI=... python -m scripts.seed_demo_hardware_session --database health_db --production-database   # your own database; you run this, deliberately
  ... --remove    deletes only the demo collection

Then start NHM with NHM_HARDWARE_DEMO_COLLECTION=demo_prerecorded_hardware_session_v1 (and NHM_HARDWARE_MONGO_DATABASE set to the same database)."""

from __future__ import annotations

import argparse
import os
import sys

from pymongo import MongoClient

from product.hardware_demo_session import DEMO_COLLECTION, FORBIDDEN_DATABASES, generate_documents


def seed(uri: str, database: str) -> int:
    docs = generate_documents()
    collection = MongoClient(uri, serverSelectionTimeoutMS=5000)[database][DEMO_COLLECTION]
    collection.drop()                                 # deterministic content: reseeding replaces, never appends
    for start in range(0, len(docs), 1000):
        collection.insert_many(docs[start : start + 1000], ordered=True)
    return len(docs)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--database", required=True, help="target database (required; there is no default)")
    p.add_argument("--production-database", action="store_true", help=f"required to write to {sorted(FORBIDDEN_DATABASES)}")
    p.add_argument("--remove", action="store_true")
    args = p.parse_args(argv)
    if args.database in FORBIDDEN_DATABASES and not args.production_database:
        print(f"refusing to write to {args.database}: pass --production-database if this is deliberate", file=sys.stderr)
        return 2
    uri = os.environ.get("NHM_HARDWARE_MONGO_URI")
    if not uri:
        print("NHM_HARDWARE_MONGO_URI is not set", file=sys.stderr)
        return 2
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    collection = client[args.database][DEMO_COLLECTION]
    if args.remove:
        collection.drop()
        print(f"dropped {args.database}.{DEMO_COLLECTION}")
        return 0
    print(f"seeded {seed(uri, args.database)} generated documents into {args.database}.{DEMO_COLLECTION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
