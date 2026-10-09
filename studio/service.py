# ruff: noqa: E501
"""The unified Studio service: one presentation/orchestration surface over the frozen 3-round product federation and the 10-round FL10 runner.

* 3-round runs execute ONLY through the unchanged product ``FederationService`` (frozen contract); the capture layer observes them read-only.
* 10-round runs execute through ``fl10.runner.run_training`` via ``StudioFl10Service``.
* Both feed the same evaluation observer, the same bundle schema and the same figure/table/export builders.
* Ownership: a run is only ever visible to the user who owns it (recorded FL10 evidence is global read-only reference)."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from fl10.constants import RECORDED
from fl10.evaluate import ROOT
from product.api.errors import ProductError, ProductErrorCode
from product.federation.service import FederationService
from studio import STUDIO_ID
from studio.bundle import build_live_bundle, read_run_report
from studio.capture3 import ProductRunCapture
from studio.constants import CLAIM_BOUNDARY, COHORT_USE_DETAIL, COHORT_USE_LABEL, EVAL_PROTOCOL_ID, OBSERVER_ID, RUN_LENGTHS
from studio.exports import export_run
from studio.observer import EvaluationObserver
from studio.recorded import RECORDED_LABEL, from_fl10_bundle, recorded_bundle, recorded_records
from studio.runner10 import MODES, CLIENT_IDS, StudioFl10Service, StudioRunError
from studio.specs import build_specs
from studio.tables import build_tables

PUBLICATION = ROOT / "reports/fl10/publication"
_CODES = {"NOT_FOUND": ProductErrorCode.NOT_FOUND, "FORBIDDEN": ProductErrorCode.FORBIDDEN, "INVALID_REQUEST": ProductErrorCode.INVALID_REQUEST}


def _as_product_error(error: StudioRunError) -> ProductError:
    return ProductError(_CODES.get(error.code, ProductErrorCode.INVALID_STATE), error.detail or error.code)


class StudioService:
    def __init__(self, *, root: Path, federation: FederationService, inference_factory: Any | None, other_run_active: Any, observer: EvaluationObserver | None = None) -> None:
        self.root = Path(root) / "studio_runs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.federation = federation
        self.observer = observer or EvaluationObserver(self.root)
        self.capture = ProductRunCapture(federation, self.observer, self.root)
        self.capture.install()
        self.runner10 = StudioFl10Service(root=self.root, observer=self.observer, inference_factory=inference_factory,
                                          other_run_active=lambda: bool(other_run_active()) or federation.active_live_run(), finalize=self._finalize_10)
        self._exports: dict[str, dict[str, Any]] = {}
        self._recorded_journals: dict[str, Any] = {}
        self._bundles: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()
        self._lock = threading.RLock()
        self._wrap_finish_for_exports()

    # ---- 3-round export finalisation (after the frozen engine finished AND every evaluation settled) -------------------
    def _wrap_finish_for_exports(self) -> None:
        service = self.federation
        original_finish = service._finish

        def finish(ctx: Any) -> None:
            original_finish(ctx)
            if ctx.run_type.value == "LIVE_RUN":
                threading.Thread(target=self._finalize_3, args=(ctx.run_id, ctx.planned_rounds), name=f"studio-export-{ctx.run_id}", daemon=True).start()

        service._finish = finish  # type: ignore[method-assign]

    def _settled(self, run_id: str, n: int, timeout: float = 1800.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            records = self.observer.records(run_id)
            if len(records) == n + 1 and all(r.evaluation_status in ("COMPLETED", "FAILED") for r in records):
                if any(r.evaluation_status == "FAILED" for r in records) or self.observer.paired(run_id) is not None:
                    return True
            time.sleep(0.5)
        return False

    def _finalize_3(self, run_id: str, n: int) -> None:
        with self._lock:
            self._exports[run_id] = {"status": "PREPARING"}
        try:
            self._settled(run_id, n)
            self._export(run_id, n, "PRODUCT_3R", "A", self.root / run_id)
        except Exception as error:
            with self._lock:
                self._exports[run_id] = {"status": "FAILED", "message": str(error)[:300]}

    def _finalize_10(self, run_id: str, directory: Path) -> None:
        self._export(run_id, 10, "FL10_10R", self.runner10.jobs[run_id].mode, directory)

    def _export(self, run_id: str, n: int, engine: str, mode: str, directory: Path) -> None:
        bundle = build_live_bundle(run_id=run_id, run_length=n, run_dir=directory / "run", observer=self.observer, mode=mode, engine=engine, status="COMPLETED", training_cohort=self._training_cohort(run_id))
        manifest = export_run(bundle, directory / "export", eval_dir=self.observer.run_dir(run_id), run_dir=directory / "run")
        with self._lock:
            self._exports[run_id] = {"status": "READY", "figures": len(manifest["figures"]), "tables": len(manifest["tables"])}

    def _training_cohort(self, run_id: str) -> list[dict[str, Any]] | None:
        path = self.root / run_id / "training_cohort.json"
        if path.exists():
            import json

            return json.loads(path.read_text())
        return None

    # ---- run identity --------------------------------------------------------------------------------------------------
    @staticmethod
    def is_recorded(run_id: str) -> bool:
        return run_id in RECORDED

    def kind(self, run_id: str) -> str:
        if run_id in RECORDED:
            return "RECORDED"
        return "FL10_10R" if run_id.startswith("FL10RUN-") else "PRODUCT"

    def owner_of(self, run_id: str) -> str | None:
        return self.runner10.owner_of(run_id) if run_id.startswith("FL10RUN-") else self.federation.owner_of(run_id)

    def authorize(self, user_id: str, run_id: str) -> None:
        if self.is_recorded(run_id):
            return
        owner = self.owner_of(run_id)
        if owner is None:
            raise ProductError(ProductErrorCode.NOT_FOUND, "run not found")
        if owner != user_id:
            raise ProductError(ProductErrorCode.FORBIDDEN, "not the owner of this run")

    def journal_for(self, run_id: str) -> Any:
        if self.is_recorded(run_id):
            with self._lock:
                if run_id not in self._recorded_journals:
                    from studio.recorded_events import build_recorded_journal

                    self._recorded_journals[run_id] = build_recorded_journal(run_id, recorded_bundle(run_id))
                return self._recorded_journals[run_id]
        return self.runner10.journal_for(run_id) if run_id.startswith("FL10RUN-") else self.federation.journal_for(run_id)

    # ---- descriptors ---------------------------------------------------------------------------------------------------
    def _eval_run_id(self, run_id: str) -> str:
        if run_id.startswith("FL10RUN-") or self.is_recorded(run_id):
            return run_id
        meta = self.federation.artifacts.read_run_meta(run_id) or {}
        return meta.get("replay_source_run_id") or run_id

    def _evaluation_state(self, run_id: str) -> dict[str, Any]:
        eval_id = self._eval_run_id(run_id)
        if self.is_recorded(run_id):
            return {"available": True, "source": "RECORDED", "evaluation_run_id": run_id, "reason": None, "revision": 0}
        has_report = (self.root / eval_id / "run").is_dir() and read_run_report(self.root / eval_id / "run") is not None
        records = self.observer.records(eval_id)
        available = bool(records) or has_report
        return {"available": available, "source": "LIVE" if eval_id == run_id else "RECORDED_FROM_SOURCE_RUN", "evaluation_run_id": eval_id,
                "reason": None if available else "RUN_PREDATES_LIVE_EVALUATION", "revision": self.observer.revision(eval_id)}

    def describe(self, user_id: str, run_id: str) -> dict[str, Any]:
        self.authorize(user_id, run_id)
        if self.is_recorded(run_id):
            bundle = recorded_bundle(run_id)
            return {"run_id": run_id, "run_length": 10, "engine": "FL10_10R", "origin": "RECORDED", "run_type": "REPLAY", "algorithm": "FEDAVG", "secagg_mode": "PLAIN",
                    "source_mode": MODES[bundle["mode"]], "status": "COMPLETED", "phase": "DONE", "current_round": 10, "planned_rounds": 10, "client_ids": list(CLIENT_IDS), "candidate": bundle["run"]["candidate"],
                    "label": RECORDED[run_id][1], "source_label": RECORDED_LABEL, "replay_of": None, "evaluation": self._evaluation_state(run_id), "export_status": "READY", "created_at": None}
        if run_id.startswith("FL10RUN-"):
            try:
                job = self.runner10.get(user_id, run_id)
            except StudioRunError as error:
                raise _as_product_error(error) from error
            return {"run_id": run_id, "run_length": 10, "engine": "FL10_10R", "origin": "LIVE", "run_type": "LIVE_RUN", "algorithm": "FEDAVG", "secagg_mode": "PLAIN", "source_mode": MODES[job.mode], "status": job.status,
                    "phase": job.phase, "current_round": job.current_round, "planned_rounds": 10, "client_ids": list(CLIENT_IDS), "candidate": job.candidate, "failure": job.failure, "label": "10-round extended run",
                    "source_label": "LIVE RUN (this session)", "replay_of": None, "evaluation": self._evaluation_state(run_id), "export_status": job.export_status, "created_at": job.created_at}
        run = self.federation.get_run(user_id, run_id)
        meta = self.federation.artifacts.read_run_meta(run_id) or {}
        replay = run.run_type.value == "REPLAY"
        export = self._exports.get(run_id) or ({"status": "READY"} if (self.root / run_id / "export" / "export_manifest.json").exists() else {"status": "NOT_STARTED"})
        return {"run_id": run_id, "run_length": run.planned_rounds, "engine": "PRODUCT_3R", "origin": "REPLAY" if replay else "LIVE", "run_type": run.run_type.value, "algorithm": run.algorithm.value, "secagg_mode": run.secagg_mode.value,
                "source_mode": "CANONICAL_SYNTHETIC", "status": run.status.value, "phase": {"CREATED": "CREATED", "RUNNING": "TRAINING", "COMPLETED": "DONE", "FAILED": "FAILED"}[run.status.value], "current_round": run.current_round,
                "planned_rounds": run.planned_rounds, "client_ids": list(run.client_ids), "candidate": ({"candidate_id": run.candidate_ids[0], "promoted": False, "deployed": False} if run.candidate_ids else None), "failure": None,
                "label": "3-round default run", "source_label": "REPLAY OF A PREVIOUS RUN" if replay else "LIVE RUN (this session)", "replay_of": meta.get("replay_source_run_id"), "evaluation": self._evaluation_state(run_id),
                "export_status": export["status"], "created_at": None}

    def list_runs(self, user_id: str) -> list[dict[str, Any]]:
        out = [self.describe(user_id, r.run_id) for r in self.federation.list_runs(user_id)]
        out += [self.describe(user_id, j.run_id) for j in self.runner10.list(user_id)]
        out += [self.describe(user_id, key) for key in RECORDED]
        return out

    # ---- data ----------------------------------------------------------------------------------------------------------
    def bundle(self, user_id: str, run_id: str) -> dict[str, Any]:
        self.authorize(user_id, run_id)
        if self.is_recorded(run_id):
            return recorded_bundle(run_id)
        d = self.describe(user_id, run_id)
        if not d["evaluation"]["available"]:
            raise ProductError(ProductErrorCode.INVALID_STATE, "RUN_PREDATES_LIVE_EVALUATION: no per-round evaluation or training diagnostics were captured for this run")
        eval_id = d["evaluation"]["evaluation_run_id"]
        key = (run_id, self.observer.revision(eval_id), d["status"], d["current_round"])
        with self._lock:
            if key in self._bundles:
                self._bundles.move_to_end(key)
                return self._bundles[key]
        bundle = build_live_bundle(run_id=run_id, run_length=d["run_length"], run_dir=self.root / eval_id / "run", observer=self.observer, mode="A" if d["source_mode"] == "CANONICAL_SYNTHETIC" else "B", engine=d["engine"],
                                   status=d["status"], source_label=d["source_label"] if d["origin"] != "REPLAY" else f"REPLAY — evaluation recorded from source run {eval_id}", eval_run_id=eval_id, training_cohort=self._training_cohort(eval_id)
                                   or self._product_cohort(eval_id), replay_of=d["replay_of"])
        with self._lock:
            self._bundles[key] = bundle
            while len(self._bundles) > 8:
                self._bundles.popitem(last=False)
        return bundle

    def _product_cohort(self, run_id: str) -> list[dict[str, Any]]:
        return self.capture._cohort_summary()

    def evaluation_summary(self, user_id: str, run_id: str) -> dict[str, Any]:
        d = self.describe(user_id, run_id)
        if self.is_recorded(run_id):
            records = recorded_records(recorded_bundle(run_id))
        else:
            records = [r.light() for r in self.observer.records(d["evaluation"]["evaluation_run_id"])] if d["evaluation"]["available"] else []
        n = d["run_length"]
        from studio.specs import comparison_pair

        a, e = comparison_pair(n)
        paired = recorded_bundle(run_id)["evaluation"]["paired"] if self.is_recorded(run_id) else self.observer.paired(d["evaluation"]["evaluation_run_id"])
        return {"run_id": run_id, "run_length": n, "evaluation": d["evaluation"], "records": records, "rounds_expected": list(range(n + 1)), "comparison": {"comparator_round": a, "endpoint_round": e, "paired_available": paired is not None},
                "evaluation_protocol_id": EVAL_PROTOCOL_ID, "observer_id": OBSERVER_ID, "cohort_use": COHORT_USE_LABEL, "cohort_use_detail": COHORT_USE_DETAIL, "claim_boundary": CLAIM_BOUNDARY, "threshold": 0.5, "calibration": "NONE",
                "source_label": d["source_label"], "run_status": d["status"], "revision": d["evaluation"]["revision"]}

    def evaluation_round(self, user_id: str, run_id: str, round_id: int) -> dict[str, Any]:
        d = self.describe(user_id, run_id)
        if not 0 <= round_id <= d["run_length"]:
            raise ProductError(ProductErrorCode.NOT_FOUND, "round out of range for this run")
        if self.is_recorded(run_id):
            b = recorded_bundle(run_id)
            key = f"R{round_id:02d}"
            block = b["evaluation"]["states"][key]
            rec = next(r for r in recorded_records(b) if r["round_id"] == round_id)
            return {**rec, "participant_metrics": block["participants"], "participant_summary": {k: block[k] for k in ("participant_macro_F1", "participants_defined", "participants_undefined")}, "curves": block["curves"],
                    "metric_result": block["pooled"]}
        if not d["evaluation"]["available"]:
            raise ProductError(ProductErrorCode.INVALID_STATE, "RUN_PREDATES_LIVE_EVALUATION")
        eval_id = d["evaluation"]["evaluation_run_id"]
        record = self.observer.get(eval_id, round_id)
        if record is None:
            return {"run_id": run_id, "round_id": round_id, "evaluation_status": "NOT_SUBMITTED", "reason": "this round has not been committed yet; nothing is invented"}
        data = record.model_dump(mode="json")
        if record.curve_artifact_reference is not None:
            import json

            data["curves"] = json.loads((self.observer.run_dir(eval_id) / record.curve_artifact_reference.path).read_text())
        return data

    def figures(self, user_id: str, run_id: str, selected: int | None = None) -> dict[str, Any]:
        bundle = self.bundle(user_id, run_id)
        return {"run_id": run_id, "revision": bundle.get("revision"), "selected_round": selected, "specs": build_specs(bundle, selected), "source_label": bundle["source_label"]}

    def tables(self, user_id: str, run_id: str) -> dict[str, Any]:
        bundle = self.bundle(user_id, run_id)
        return {"run_id": run_id, "revision": bundle.get("revision"), "tables": build_tables(bundle), "source_label": bundle["source_label"]}

    def round_detail(self, user_id: str, run_id: str, round_id: int) -> dict[str, Any]:
        bundle = self.bundle(user_id, run_id)
        row = next((r for r in bundle["rounds"] if r["round"] == round_id), None)
        return {"run_id": run_id, "round_id": round_id, "committed": row is not None, "round": row, "client_rounds": [r for r in bundle["client_rounds"] if r["round"] == round_id],
                "batches": [r for r in bundle["batches"] if r["round"] == round_id], "state": bundle["state_progression"].get(str(round_id))}

    # ---- exports -------------------------------------------------------------------------------------------------------
    def export_dir(self, run_id: str) -> Path:
        if self.is_recorded(run_id):
            return PUBLICATION / RECORDED[run_id][0]
        eval_id = self._eval_run_id(run_id)
        return self.root / eval_id / "export"

    def export_manifest(self, user_id: str, run_id: str) -> dict[str, Any]:
        d = self.describe(user_id, run_id)
        path = self.export_dir(run_id) / "export_manifest.json"
        if path.exists():
            import json

            return {"status": "READY", **json.loads(path.read_text())}
        status = d["export_status"] if d["origin"] != "REPLAY" else self._exports.get(self._eval_run_id(run_id), {"status": "NOT_STARTED"})["status"]
        message = {"PREPARING": "EXPORT PREPARING", "NOT_STARTED": "Exports are generated when the run completes and every evaluation has settled.", "FAILED": "Export generation failed; see run status."}.get(status, status)
        return {"status": status, "message": message, "run_id": run_id}
