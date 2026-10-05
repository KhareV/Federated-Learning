"""CAP-003 mutation / negative controls. Each mutation is applied in place, the named targeted tests
must FAIL, and the original bytes are restored and verified (also via git). None is an equivalent
mutant: each changes observable behaviour or a statically checked property.
Writes reports/capstone/cap_003/mutation_controls.json."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COORD = "product/monitoring/coordinator.py"
API_T = "tests/test_capstone_product_api.py"
COORD_T = "tests/test_capstone_monitoring_coordinator.py"
CLIENT_T = "tests/test_capstone_inference_client.py"
MUTATIONS = (
    ("PUBLIC_MODEL_SELECTOR_INSERTED", "product/api/models.py",
     "    scenario_id: str | None = Field(default=None, min_length=1, max_length=80)\n",
     "    scenario_id: str | None = Field(default=None, min_length=1, max_length=80)\n"
     "    model_id: str | None = None\n", [API_T]),
    ("NONE_GAP_PLACEHOLDER_PASSED_TO_SCIENTIFIC_RUNTIME", COORD,
     "        self._batch.append(record)  # scientific branch: the SAME unmodified record object\n",
     "        self._batch.append(__import__('dataclasses').replace(record, ecg_raw=None)"
     " if record.sample_index % 997 == 0 else record)\n", [COORD_T]),
    ("HTTP_422_CONVERTED_INTO_FAKE_INFERENCE_RESULT", COORD,
     '            self.telemetry["expected_unusable_windows"] += 1\n',
     '            self.telemetry["expected_unusable_windows"] += 1\n'
     "            self._publish(self._adapter.inference_result(__import__('api.schemas',"
     " fromlist=['x']).InferWindowResponse(timestamp_us=window['timestamp_us'],"
     " model_id='MODEL_V2_FINAL', calibration_domain='X', calibration_id='CAL_V2',"
     " ecg_quality='UNUSABLE', monitoring_state='RECHECK_SENSOR', context=None,"
     " preprocess_version='PREPROC_V1', alert_policy_id='ALERT_POLICY_V1')))\n", [COORD_T]),
    ("DUPLICATE_PRODUCT_SEQUENCE_INDEX", "product/monitoring/event_adapter.py",
     "        self._sequence += 1\n        return event\n",
     "        self._sequence += 0 if event_type == 'quality.status' else 1\n        return event\n",
     [COORD_T]),
    ("WRONG_OWNER_ACCEPTED", "product/devices/manager.py",
     "        if entry.owner_user_id != owner_user_id:\n", "        if False:\n", [API_T]),
    ("DIRECT_RUNTIME_IMPORT_IN_INFERENCE_CLIENT", "product/inference/client.py",
     "import httpx\n",
     "import httpx\nfrom api.runtime_v2 import ResearchRuntimeV2  # MUTATION\n", [CLIENT_T]),
    ("LOST_DEVICE_DISCONNECT_EVENT", COORD,
     "    async def _on_device_event(self, event: DeviceEvent) -> None:\n",
     "    async def _on_device_event(self, event: DeviceEvent) -> None:\n"
     "        if event.event_type is DeviceEventType.DEVICE_DISCONNECTED:\n            return\n",
     [API_T, COORD_T]),
)


def main() -> int:
    results = []
    for name, rel, old, new, tests in MUTATIONS:
        path = ROOT / rel
        original = path.read_bytes()
        text = original.decode()
        assert old in text, name
        try:
            path.write_text(text.replace(old, new, 1))
            run = subprocess.run(
                [sys.executable, "-m", "pytest", *tests, "-x", "-q", "-p", "no:cacheprovider",
                 "-W", "ignore::DeprecationWarning"], cwd=ROOT, capture_output=True, text=True,
                env={**os.environ, "PYTHONPATH": "src:."})
            failed = run.returncode != 0
            first = [ln for ln in run.stdout.splitlines() if ln.startswith("FAILED")][:1]
        finally:
            path.write_bytes(original)
        clean = subprocess.run(["git", "status", "--short", "--", rel], cwd=ROOT, check=True,
                               capture_output=True, text=True).stdout.strip()
        results.append({"mutation": name, "file": rel, "tests_run": tests,
                        "suite_failed_as_designed": failed,
                        "first_failing_test": first[0] if first else None,
                        "file_restored_byte_identical": path.read_bytes() == original,
                        "git_status_of_file_after_restore": clean})
        print(name, failed, first[:1], flush=True)
    payload = {"controls": results,
               "all_caught": all(r["suite_failed_as_designed"] for r in results),
               "all_restored": all(r["file_restored_byte_identical"] for r in results)}
    (ROOT / "reports/capstone/cap_003/mutation_controls.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("all_caught", "all_restored")}))
    return 0 if payload["all_caught"] and payload["all_restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
