# ruff: noqa: E501
"""CAP-005 mutation / negative controls. Each mutation is applied in place, the named vitest files must
FAIL, and the original bytes are restored and verified (also via git). None is an equivalent mutant.
``--check`` only verifies that every anchor exists. Writes reports/capstone/cap_005/mutation_controls.json."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = "frontend/src/"
PRODUCT_TESTS = "src/lib/product"
MUTATIONS = (
    ("DEMO_MODE_INITIALIZES_CLERK", FE + "lib/product/auth.ts",
     "\t\t\t// DEMO: no Clerk import, no Clerk network request.\n",
     "\t\t\tawait (this.options.loadClerk ?? defaultClerkLoader)('pk_test_mutation');\n"),
    ("CLERK_SECRET_INSERTED_INTO_FRONTEND", FE + "lib/product/auth.ts",
     "export const defaultClerkLoader",
     "export const MUTATION_SECRET = 'CLERK_SECRET_KEY';\nexport const defaultClerkLoader"),
    ("PRODUCT_MONITOR_CALLS_INFER_WINDOW_DIRECTLY", FE + "routes/app/monitoring/+page.svelte",
     "\tonMount(() => { void store.loadDevices(); void store.loadSessions(); });",
     "\tonMount(() => { void fetch('/v1/infer-window', { method: 'POST' }); void store.loadDevices(); void store.loadSessions(); });"),
    ("UNUSABLE_LOCALLY_CREATES_RECHECK_SENSOR_STATE", FE + "lib/product/live-model.ts",
     "\t\t\t\tthis.pending = event.payload.ecg_quality !== 'UNUSABLE';\n",
     "\t\t\t\tthis.pending = event.payload.ecg_quality !== 'UNUSABLE';\n\t\t\t\tif (event.payload.ecg_quality === 'UNUSABLE') this.monitoringState = 'RECHECK_SENSOR';\n"),
    ("NULL_WAVEFORM_GAPS_CONVERTED_TO_ZERO", FE + "lib/product/waveform.ts",
     "\t\t\tthis.samples.push(value);\n", "\t\t\tthis.samples.push(value ?? 0);\n"),
    ("MODEL_SELECTOR_INSERTED", FE + "lib/product/api.ts",
     "call('POST', '/sessions', { device_id: deviceId, scenario_id: scenarioId }),",
     "call('POST', '/sessions', { device_id: deviceId, scenario_id: scenarioId, model_id: 'MODEL_V1' }),"),
    ("FAKE_HR_HARD_CODED_INTO_PRODUCT_DASHBOARD", FE + "routes/app/+page.svelte",
     '<p class="claim">{system?.claim ?? \'\'}</p>', '<p class="claim">{system?.claim ?? \'\'} Heart rate 72 bpm</p>'),
    ("WEBSOCKET_TOKEN_INSERTED_INTO_URL", FE + "lib/product/api.ts",
     "/sessions/${encodeURIComponent(sessionId)}/live`;", "/sessions/${encodeURIComponent(sessionId)}/live?token=abc`;"),
    ("SYNTHETIC_FL_SITE_PRESENTED_AS_REAL_INSTITUTION", FE + "routes/+page.svelte",
     'text-anchor="middle" fill="#94a3b8" font-size="10" font-family="JetBrains Mono, monospace">{site.id}</text>',
     'text-anchor="middle" fill="#94a3b8" font-size="10" font-family="JetBrains Mono, monospace">{site.id} (Delhi hospital)</text>'),
    ("PHYSICAL_WEARABLE_SHOWN_AS_CONNECTED", FE + "routes/app/device/+page.svelte",
     "<dt>PHYSICAL HARDWARE</dt><dd>NOT CONNECTED / NOT IMPLEMENTED</dd>", "<dt>PHYSICAL HARDWARE</dt><dd>CONNECTED</dd>"),
)


def main() -> int:
    if "--check" in sys.argv:
        bad = [name for name, rel, old, _n in MUTATIONS if old not in (ROOT / rel).read_text()]
        print(json.dumps({"mutations": len(MUTATIONS), "missing_anchor": bad}))
        return 1 if bad else 0
    results = []
    for name, rel, old, new in MUTATIONS:
        path = ROOT / rel
        original = path.read_bytes()
        text = original.decode()
        assert old in text, name
        try:
            path.write_text(text.replace(old, new, 1))
            run = subprocess.run(["npx", "vitest", "run", PRODUCT_TESTS], cwd=ROOT / "frontend", capture_output=True, text=True)
            failed = run.returncode != 0
            names = [ln.strip() for ln in run.stdout.splitlines() if ln.strip().startswith("\u00d7") or " FAIL " in ln][:2]
        finally:
            path.write_bytes(original)
        clean = subprocess.run(["git", "status", "--short", "--", rel], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
        results.append({"mutation": name, "file": rel, "suite_failed_as_designed": failed, "first_failures": names,
                        "file_restored_byte_identical": path.read_bytes() == original, "git_status_of_file_after_restore": clean})
        print(name, failed, names[:1], flush=True)
    payload = {"controls": results, "all_caught": all(r["suite_failed_as_designed"] for r in results),
               "all_restored": all(r["file_restored_byte_identical"] for r in results)}
    (ROOT / "reports/capstone/cap_005/mutation_controls.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("all_caught", "all_restored")}))
    return 0 if payload["all_caught"] and payload["all_restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
