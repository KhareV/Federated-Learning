# ruff: noqa: E501
"""CAP-008 mutation / negative controls. Each (non-equivalent) mutation is applied in place, the named frontend (vitest)
or Python tests must FAIL (the first failing test is recorded; a collection/compile error does not count), and the
original bytes are restored and verified (also via git). ``--check`` verifies anchors only.
Writes reports/capstone/cap_008/mutation_controls.json."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FE = ROOT / "frontend"
OUT = Path(os.environ.get("CAP008_OUT", ROOT / "reports/capstone/cap_008"))
SRC = "frontend/src"
T = f"{SRC}/lib/product/federation/__tests__"
COMP, STORE_T, STATIC, MODEL_T = f"{T}/components.test.ts", f"{T}/store-api.test.ts", f"{T}/static-audit.test.ts", f"{T}/events-model.test.ts"
LAYOUT = f"{SRC}/lib/components/product/federation"
MUTATIONS = (
    ("EIGHT_HOSPITALS_WORDING", [(f"{SRC}/routes/app/federation/clients/+page.svelte", "SYNTHETIC RESEARCH PARTITIONS — NOT HOSPITALS OR INSTITUTIONS.", "EIGHT HOSPITALS PARTICIPATE IN THIS FEDERATION.")], [COMP]),
    ("FAKE_ACCURACY_METRIC", [(f"{SRC}/routes/app/federation/+page.svelte", "\t<MetricTile label=\"Logical clients\"", "\t<MetricTile label=\"Global accuracy\" value=\"0.93\" detail=\"candidate\" />\n\t<MetricTile label=\"Logical clients\"")], [STATIC, COMP]),
    ("SMOOTH_PROGRESS_INVENTED", [(f"{LAYOUT}/ClientGrid.svelte", "'0% (started)'", "`${Math.round(Math.random() * 100)}% (training)`")], [STATIC]),
    ("CANDIDATE_SHOWN_AS_RELEASED_DEFAULT", [(f"{SRC}/routes/app/models/+page.svelte", "{#each fed.registry.released_scientific as m}", "{#each [...fed.registry.released_scientific, ...fed.registry.capstone_fl_candidates.map((c) => ({ model_id: c.candidate_id, role: 'RELEASED_DEFAULT' }))] as m}")], [COMP]),
    ("DEPLOY_BUTTON_ADDED", [(f"{LAYOUT}/CandidateCard.svelte", "\t<h3>{candidate.candidate_id}</h3>\n", "\t<h3>{candidate.candidate_id}</h3>\n\t<button type=\"button\">Deploy candidate</button>\n")], [STATIC, COMP]),
    ("CANDIDATE_INFERENCE_REQUEST_ADDED", [(f"{SRC}/lib/product/federation/state.svelte.ts", "\t\t\tthis.registry = await this.api.models();\n", "\t\t\tthis.registry = await this.api.models();\n\t\t\tvoid fetch('/product/v1/infer-window', { method: 'POST' });\n")], [STATIC]),
    ("SECAGG_PAGE_CLAIMS_DIFFERENTIAL_PRIVACY", [(f"{SRC}/routes/app/federation/privacy/+page.svelte", "<li>No differential privacy.</li>", "<li>Provides differential privacy.</li>")], [COMP]),
    ("SECAGG_SHOWN_AS_AUTHORITATIVE_AGGREGATION", [(f"{SRC}/routes/app/federation/live/+page.svelte", "{v.rounds.find((r) => r.aggregationMode)?.aggregationMode ?? '--'}", "{fed.run.secagg_mode}")], [COMP]),
    ("WEBSOCKET_TOKEN_IN_URL", [(f"{SRC}/lib/product/api.ts", "/federation/runs/${encodeURIComponent(runId)}/live`;", "/federation/runs/${encodeURIComponent(runId)}/live?token=session`;")], [STORE_T, STATIC]),
    ("RUN_FORM_EXPOSES_MU", [(f"{LAYOUT}/RunConfigForm.svelte", "\t<dl class=\"fixed\"", "\t<label>mu <input type=\"number\" name=\"mu\" value=\"0.1\" /></label>\n\t<dl class=\"fixed\"")], [COMP, STATIC]),
    ("REPLAY_UI_SAYS_TRAINING_IN_PROGRESS", [(f"{LAYOUT}/FederationBanner.svelte", "REPLAY · NO TRAINING IS EXECUTING", "REPLAY · TRAINING IN PROGRESS")], [COMP]),
    ("MONITORING_EVENT_ACCEPTED_BY_FEDERATION_REDUCER", [(f"{SRC}/lib/product/federation/live-model.ts", "\t\t\treturn this.stop(error instanceof FederationEventError ? error.reason : 'MALFORMED_EVENT');", "\t\t\tif (raw && typeof raw === 'object' && (raw as { event_type?: string }).event_type === 'inference.result') { this.expected += 1; this.view.eventCount += 1; return true; }\n\t\t\treturn this.stop(error instanceof FederationEventError ? error.reason : 'MALFORMED_EVENT');")], [MODEL_T]),
    ("CANDIDATE_COUNT_INCREMENTED_FROM_REPLAY_EVENT", [(f"{SRC}/lib/product/federation/live-model.ts", "if (!historical) v.newCandidatesCreatedByThisRun += 1;", "v.newCandidatesCreatedByThisRun += 1;")], [MODEL_T]),
    ("MODEL_V2_FINAL_REPLACED_BY_CANDIDATE_IN_MONITORING_LANE", [(f"{LAYOUT}/ArchitectureLanes.svelte", "<ol><li>{releasedModel}</li>", "<ol><li>CAPSTONE_FL_CANDIDATE_0001</li>")], [COMP]),
)


def apply(text: str, old: str, new: str) -> str:
    assert old in text, old[:60]
    return text.replace(old, new, 1)


def run_tests(tests: list[str]) -> tuple[bool, str | None]:
    files = [t.removeprefix("frontend/") for t in tests if t.endswith(".ts") and "__tests__" in t]
    proc = subprocess.run(["npx", "vitest", "run", *files], cwd=FE, capture_output=True, text=True, timeout=600)
    out = proc.stdout + proc.stderr
    first = [ln.strip() for ln in out.splitlines() if re.search(r"^\s*(\u00d7|FAIL)\s", ln)]
    failed_test = [ln for ln in first if "\u00d7" in ln]
    return proc.returncode != 0 and bool(failed_test), (failed_test[0] if failed_test else (first[0] if first else None))


def main() -> int:
    if "--check" in sys.argv:
        bad = [f"{n}:{rel}" for n, edits, _t in MUTATIONS for rel, old, _new in edits if old not in (ROOT / rel).read_text()]
        print(json.dumps({"mutations": len(MUTATIONS), "missing_anchor": bad}))
        return 1 if bad else 0
    results = []
    for name, edits, tests in MUTATIONS:
        originals = {rel: (ROOT / rel).read_bytes() for rel, _o, _n in edits}
        try:
            for rel, old, new in edits:
                (ROOT / rel).write_text(apply((ROOT / rel).read_text(), old, new))
            caught, first = run_tests(tests)
        finally:
            for rel, data in originals.items():
                (ROOT / rel).write_bytes(data)
        clean = subprocess.run(["git", "status", "--short", "--", *originals], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
        results.append({"mutation": name, "files": sorted(originals), "tests_run": tests, "caught_by_a_failing_test": caught, "first_failing_test": first,
                        "files_restored_byte_identical": all((ROOT / rel).read_bytes() == data for rel, data in originals.items()), "git_status_after_restore": clean})
        print(name, caught, first, flush=True)
    payload = {"controls": results, "all_caught": all(r["caught_by_a_failing_test"] for r in results), "all_restored": all(r["files_restored_byte_identical"] for r in results)}
    (OUT / "mutation_controls.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("all_caught", "all_restored")}))
    return 0 if payload["all_caught"] and payload["all_restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
