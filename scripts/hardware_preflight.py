"""Read-only demo preflight.

    PYTHONPATH=src:. python -m scripts.hardware_preflight [--json] [--ws-url wss://host/]

It never writes to MongoDB, never sends WebSocket frames and never prints secrets. It reports two separate
verdicts: SOFTWARE READY (the NHM stack can run the demo) and whether FRESH RECORDS ARE ARRIVING in the selected
source. Fresh records do not prove a physical sensor is attached: the writer could be the ESP32, the emulator or
any other client of the ingestion service.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

DAILY = re.compile(r"records_\d{4}-\d{2}-\d{2}$")
FRESH_MAX_AGE_S = 10.0  # the app's stale threshold is 5 s; allow one extra poll period


def http(url: str, timeout: float = 4.0) -> tuple[int | None, str]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "nhm-preflight"}), timeout=timeout) as r:
            return r.status, ""
    except urllib.error.HTTPError as error:
        return error.code, ""
    except Exception as error:
        return None, type(error).__name__


def classify(database: str, collection: str) -> str:
    if database == "health_db" and (collection == "records_*" or DAILY.fullmatch(collection)):
        return "PRODUCTION HARDWARE"
    if database.startswith("nhm_rehearsal") or collection.startswith("nhm_integration_test") or collection.startswith("nhm_"):
        return "STAGING TEST"
    return "UNKNOWN (neither the production hardware collections nor a known test target)"


def mongo_report(uri: str, database: str, collection: str) -> dict[str, Any]:
    from bson import ObjectId
    from pymongo import MongoClient

    out: dict[str, Any] = {"reachable": False}
    client = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)
    try:
        client.admin.command("ping")
        out["reachable"] = True
        db = client[database]
        names = sorted(n for n in db.list_collection_names() if (DAILY.fullmatch(n) if collection == "records_*" else n == collection))
        out["collections_matched"] = names[-3:]
        if not names:
            return out | {"newest_record": None, "reason": "no matching collection exists yet"}
        newest = None
        for name in names[-2:]:
            doc = db[name].find_one({}, sort=[("_id", -1)])
            if doc and (newest is None or doc["_id"] > newest[1]["_id"]):
                newest = (name, doc)
        if newest is None:
            return out | {"newest_record": None, "reason": "collection(s) empty"}
        name, doc = newest
        stamp = doc.get("timestamp") or doc.get("ingestedAt")
        now = datetime.now(UTC)
        recent_floor = ObjectId.from_datetime(now - timedelta(seconds=30))
        recent = sum(db[n].count_documents({"_id": {"$gt": recent_floor}}) for n in names[-2:])
        out |= {
            "newest_record": {"collection": name, "id": str(doc["_id"]), "stored_timestamp": stamp.isoformat() if hasattr(stamp, "isoformat") else None,
                              "age_seconds": round((now - stamp.astimezone(UTC)).total_seconds(), 1) if hasattr(stamp, "astimezone") else None,
                              "field_types": {k: type(v).__name__ for k, v in doc.items() if k != "_id"}},
            "records_last_30s": recent, "rate_hz_last_30s": round(recent / 30.0, 2),
        }
    except Exception as error:
        out["error"] = type(error).__name__
    finally:
        client.close()
    return out


async def ws_handshake(url: str) -> dict[str, Any]:
    from websockets.asyncio.client import connect

    started = time.monotonic()
    try:
        async with connect(url, open_timeout=15, ping_interval=None) as ws:
            return {"handshake": "OK", "seconds": round(time.monotonic() - started, 2), "note": "no frame was sent; a handshake alone says nothing about the sensor"}
    except Exception as error:
        return {"handshake": "FAILED", "error": type(error).__name__, "seconds": round(time.monotonic() - started, 2)}


def build(args: argparse.Namespace) -> dict[str, Any]:
    from dotenv import dotenv_values

    env = {**dotenv_values(args.env_file), **__import__("os").environ}
    uri = env.get("NHM_HARDWARE_MONGO_URI", "")
    database = args.database or env.get("NHM_HARDWARE_MONGO_DATABASE", "")
    collection = args.collection or env.get("NHM_HARDWARE_MONGO_COLLECTION", "")
    checks: dict[str, Any] = {}

    checks["hardware_config"] = {"enabled": env.get("NHM_HARDWARE_MONGO_ENABLED", "").lower() == "true", "uri_configured": bool(uri),
                                 "database": database, "collection": collection, "source": classify(database, collection)}
    checks["clerk"] = {"publishable_key": bool(env.get("CLERK_PUBLISHABLE_KEY")), "secret_key": bool(env.get("CLERK_SECRET_KEY")),
                       "mode": "TEST" if str(env.get("CLERK_PUBLISHABLE_KEY", "")).startswith("pk_test_") else ("LIVE" if env.get("CLERK_PUBLISHABLE_KEY") else None)}
    for name, url in (("frontend", args.frontend_url), ("product_backend", args.product_url), ("inference", args.inference_url)):
        code, err = http(url)
        checks[name] = {"url": url, "http_status": code, "ready": code is not None and code < 500, "error": err or None}
    checks["mongodb"] = mongo_report(uri, database, collection) if uri and database and collection else {"reachable": False, "error": "not configured"}
    if args.ws_url:
        checks["websocket_endpoint"] = asyncio.run(ws_handshake(args.ws_url))
    free = shutil.disk_usage(args.workspace).free
    checks["disk"] = {"workspace": args.workspace, "free_gb": round(free / 1e9, 1), "ok": free > 2e9}
    try:
        import flwr  # noqa: F401
        import torch

        from api.hardware_v2_experimental import build_windows  # noqa: F401
        from studio.hardware_demo import HardwareDemoService  # noqa: F401

        checks["demo_fl_components"] = {"ok": True, "torch": torch.__version__, "flower": __import__("flwr").__version__}
    except Exception as error:
        checks["demo_fl_components"] = {"ok": False, "error": type(error).__name__}

    cfg_ok = checks["hardware_config"]["enabled"] and checks["hardware_config"]["uri_configured"]
    clerk_ok = checks["clerk"]["publishable_key"] and checks["clerk"]["secret_key"]
    services_ok = all(checks[k]["ready"] for k in ("frontend", "product_backend", "inference"))
    mongo_ok = bool(checks["mongodb"].get("reachable"))
    software_ready = bool(cfg_ok and clerk_ok and services_ok and mongo_ok and checks["disk"]["ok"] and checks["demo_fl_components"]["ok"])
    newest = (checks["mongodb"].get("newest_record") or {})
    fresh = bool(newest.get("age_seconds") is not None and newest["age_seconds"] <= FRESH_MAX_AGE_S
                 and checks["mongodb"].get("records_last_30s", 0) > 0)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "SOFTWARE": "SOFTWARE READY" if software_ready else "SOFTWARE NOT READY",
        "SOURCE": checks["hardware_config"]["source"],
        "RECORDS": ("FRESH RECORDS ARRIVING (writer identity NOT verified: could be the ESP32, an emulator or any client)" if fresh
                    else "NO FRESH RECORDS in the selected source"),
        "PHYSICAL_DEVICE": "NOT VERIFIED BY THIS CHECK (fresh records are not proof of a sensor; run the physical smoke test)",
        "blocking": [k for k, ok in (("hardware_config", cfg_ok), ("clerk", clerk_ok), ("services", services_ok), ("mongodb", mongo_ok),
                                       ("disk", checks["disk"]["ok"]), ("demo_fl_components", checks["demo_fl_components"]["ok"])) if not ok],
        "checks": checks,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", default=str(ROOT / ".env"))
    ap.add_argument("--frontend-url", default="http://127.0.0.1:4173/sign-in")
    ap.add_argument("--product-url", default="http://127.0.0.1:8002/product/v1/system")
    ap.add_argument("--inference-url", default="http://127.0.0.1:8001/docs")
    ap.add_argument("--database")
    ap.add_argument("--collection")
    ap.add_argument("--ws-url", help="optional: attempt a WebSocket handshake only (no frames) against this endpoint")
    ap.add_argument("--workspace", default=str(ROOT))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    report = build(args)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"{report['SOFTWARE']}   |   source: {report['SOURCE']}\n{report['RECORDS']}\n{report['PHYSICAL_DEVICE']}")
        for name, c in report["checks"].items():
            print(f"  - {name}: {json.dumps(c, default=str)[:260]}")
        if report["blocking"]:
            print("BLOCKING:", ", ".join(report["blocking"]))
    return 0 if report["SOFTWARE"] == "SOFTWARE READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
