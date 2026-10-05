# ruff: noqa: E501
"""CAP-004: SQLite schema, storage-policy successor, event persistence mapping, context dual
representation, waveform preview, immutability and data-locality."""

from __future__ import annotations

import itertools
import json
import sqlite3
import zlib
from collections import Counter

import httpx
import pytest
from fastapi.testclient import TestClient

from product.contracts import ROOT, load_contract
from product.persistence import preview as preview_module
from product.persistence.schema import RUNTIME_COLUMNS, SCHEMA_VERSION, ddl_statements
from product.persistence.store import (
    FUTURE_TABLES,
    CapstoneSqliteStore,
    SchemaVersionError,
)
from tests.capstone_persistent_support import (
    BASE,
    USER_A,
    StrictInferenceDouble,
    collect_ws,
    make_persistent_app,
    provisioned_session,
)

POLICY_V2 = json.loads((ROOT / "contracts/capstone/storage_policy_v2.json").read_text())
POLICY_V1 = json.loads((ROOT / "contracts/capstone/storage_policy_v1.json").read_text())


class WithholdingDouble(StrictInferenceDouble):
    """Answers 200s whose context is context_available=false yet still carries PPG values."""

    def handler(self, request: httpx.Request) -> httpx.Response:
        response = super().handler(request)
        if response.status_code != 200:
            return response
        body = json.loads(response.content)
        body["context"].update(context_available=False, pr_ppg_bpm=71.5, spo2_pct=97.0,
                               spo2_valid=True, ppg_quality="VALID")
        return httpx.Response(200, json=body)


@pytest.fixture(scope="module")
def mixed(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "mixed.sqlite3"
    app, store = make_persistent_app(path, StrictInferenceDouble())
    with TestClient(app) as client:
        device_id, session_id = provisioned_session(client, "MIXED_MONITORING_SESSION")
        client.post(f"{BASE}/sessions/{session_id}/start", headers=USER_A)
        events = collect_ws(client, session_id)
    return {"app": app, "store": store, "events": events, "session_id": session_id,
            "device_id": device_id, "path": path}


# ---- schema ------------------------------------------------------------------------------------
def test_database_is_created_from_scratch_with_pragmas_and_schema_version(tmp_path) -> None:
    store = CapstoneSqliteStore(tmp_path / "fresh.sqlite3")
    assert store.pragma("foreign_keys") == 1
    assert store.pragma("journal_mode") == "wal"
    assert store.pragma("user_version") == SCHEMA_VERSION == 1
    assert store.integrity_check() == ["ok"] and store.foreign_key_check() == []
    expected = {e["table"] for e in POLICY_V2["entities"]}
    assert set(store.table_names()) == expected and len(expected) == 15
    assert "schema_version" not in " ".join(store.table_names())  # PRAGMA user_version only
    store.close()
    again = CapstoneSqliteStore(tmp_path / "fresh.sqlite3")  # reopen: no re-init, same version
    assert again.pragma("user_version") == 1 and again.pragma("foreign_keys") == 1
    again.close()


def test_unknown_schema_versions_and_unversioned_databases_are_refused(tmp_path) -> None:
    path = tmp_path / "v.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version = 7")
    connection.commit()
    connection.close()
    with pytest.raises(SchemaVersionError, match="UNSUPPORTED_SCHEMA_VERSION"):
        CapstoneSqliteStore(path)
    other = tmp_path / "u.sqlite3"
    connection = sqlite3.connect(other)
    connection.execute("CREATE TABLE stray (x INTEGER)")
    connection.commit()
    connection.close()
    with pytest.raises(SchemaVersionError, match="UNVERSIONED"):
        CapstoneSqliteStore(other)


def test_schema_matches_the_storage_policy_successor_exactly(tmp_path) -> None:
    store = CapstoneSqliteStore(tmp_path / "s.sqlite3")
    connection = store._connection
    for entity in POLICY_V2["entities"]:
        info = connection.execute(f"PRAGMA table_info({entity['table']})").fetchall()
        assert [r["name"] for r in info] == list(entity["columns"]), entity["table"]
        pk = [r["name"] for r in info if r["pk"]]
        assert pk == [entity["primary_key"]]
        for row in info:
            declared = entity["columns"][row["name"]]
            assert (row["notnull"] == 0) == (declared.endswith("?") and row["name"] not in pk
                                             ) or row["pk"], (entity["table"], row["name"])
        fks = {(r["from"], f"{r['table']}.{r['to']}")
               for r in connection.execute(f"PRAGMA foreign_key_list({entity['table']})")}
        assert fks == {(f["column"], f["references"]) for f in entity["foreign_keys"]}
        indexes = {r["name"]: r for r in connection.execute(
            f"PRAGMA index_list({entity['table']})") if r["origin"] == "c"}
        assert set(indexes) == {i["name"] for i in entity["indexes"]}
        for index in entity["indexes"]:
            assert bool(indexes[index["name"]]["unique"]) == index["unique"]
            cols = [r["name"] for r in connection.execute(f"PRAGMA index_info({index['name']})")]
            assert cols == index["columns"]
    assert len(ddl_statements(POLICY_V2)) == sum(1 + len(e["indexes"])
                                                 for e in POLICY_V2["entities"]) + 2


def test_storage_policy_v2_is_a_narrow_additive_successor_of_v1() -> None:
    v1, v2 = {e["entity"]: e for e in POLICY_V1["entities"]}, {
        e["entity"]: e for e in POLICY_V2["entities"]}
    assert set(v1) == set(v2)
    for name in v1:
        c1, c2 = v1[name]["columns"], v2[name]["columns"]
        if name == "devices":
            assert list(c2) == [*list(c1), "scenario_id"] and c2["scenario_id"] == "TEXT?"
            assert {k: c2[k] for k in c1} == c1
        else:
            assert c1 == c2, name
        for key in ("primary_key", "foreign_keys", "indexes", "ownership", "retention_intent"):
            assert v1[name][key] == v2[name][key], (name, key)
    assert POLICY_V2["supersedes"]["v1_modified"] is False
    assert POLICY_V2["high_rate_policy"] == POLICY_V1["high_rate_policy"]
    assert POLICY_V2["delta_from_v1"]["added_columns"] == [
        {"entity": "devices", "column": "scenario_id", "type": "TEXT?",
         "rule": "required for SIMULATED"}]
    from hashlib import sha256
    assert POLICY_V2["supersedes"]["sha256"] == sha256(
        (ROOT / "contracts/capstone/storage_policy_v1.json").read_bytes()).hexdigest()


def test_a_simulated_device_cannot_be_stored_without_its_scenario(tmp_path) -> None:
    store = CapstoneSqliteStore(tmp_path / "c.sqlite3")
    from product.auth.base import AuthIdentity, AuthProviderType
    store.upsert_user(AuthIdentity(user_id="demo:u", auth_provider=AuthProviderType.DEMO,
                                   auth_session_id="s", demo_mode=True))
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_device(device_id="D", user_id="demo:u", display_name="x",
                            adapter_type="SIMULATED", source_dataset_id=None, source_mode=None,
                            simulation_version=None, scenario_id=None, capabilities={})
    store.insert_device(device_id="D", user_id="demo:u", display_name="x",
                        adapter_type="SIMULATED", source_dataset_id=None, source_mode=None,
                        simulation_version=None, scenario_id="NORMAL_MONITORING", capabilities={})
    with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE"):
        store._run("UPDATE devices SET scenario_id = 'POOR_SIGNAL' WHERE device_id = 'D'")
    with pytest.raises(sqlite3.IntegrityError):  # foreign keys really are enforced
        store.insert_device(device_id="E", user_id="nobody", display_name="x",
                            adapter_type="SIMULATED", source_dataset_id=None, source_mode=None,
                            simulation_version=None, scenario_id="NORMAL_MONITORING",
                            capabilities={})


def test_the_schema_has_no_raw_sample_table_or_per_user_model_state_or_credentials(mixed) -> None:
    store = mixed["store"]
    connection = store._connection
    banned_tables = ("sample", "raw", "ecg", "ppg", "waveform_sample")
    names = store.table_names()
    assert not [n for n in names if any(b in n for b in banned_tables)]
    columns = {(t, r["name"]) for t in names for r in connection.execute(f"PRAGMA table_info({t})")}
    forbidden_columns = {"ecg_raw", "ppg_red_raw", "ppg_ir_raw", "samples", "ecg_samples", "raw_ecg",
                         "raw_ppg", "user_model_id", "personal_checkpoint", "per_user_threshold",
                         "personal_calibration", "online_learning_state", "truth", "labels",
                         "label", "minibatch", "weights", "update_tensor", "password", "token",
                         "secret", "cookie", "jwt", "credential", "api_key"}
    assert not {c for _, c in columns} & forbidden_columns
    assert not [c for _, c in columns if any(w in c for w in ("password", "token", "secret"))]
    for entity in POLICY_V2["entities"]:
        assert not set(entity["columns"]) & set(POLICY_V2["high_rate_policy"]["forbidden_column_names"])


# ---- population + data locality ----------------------------------------------------------------
def test_future_tables_exist_but_stay_empty_and_the_database_is_clean(mixed) -> None:
    store = mixed["store"]
    counts = store.row_counts()
    for table in FUTURE_TABLES:
        assert counts[table] == 0, table
    assert store.integrity_check() == ["ok"] and store.foreign_key_check() == []
    assert counts["users"] == 1 and counts["devices"] == 1 and counts["monitoring_sessions"] == 1
    assert counts["waveform_previews"] == 1
    # bounded rows: far fewer rows than the 172,800 delivered source samples
    assert sum(counts.values()) < 600


def test_the_database_holds_product_metadata_not_training_data(mixed) -> None:
    store = mixed["store"]
    data = "\n".join(line for line in store._connection.iterdump()
                     if line.upper().startswith("INSERT")).lower()  # row data, not the schema text
    for token in ("simulationtruth", "simulation_truth", "minibatch", "update_digest",
                  "candidate_weights", "scheduled_events", "label_source"):
        assert token not in data


# ---- event persistence mapping -----------------------------------------------------------------
def test_every_live_event_kind_maps_to_its_table_with_the_real_sequence(mixed) -> None:
    store, events, sid = mixed["store"], mixed["events"], mixed["session_id"]
    kinds = Counter(e["event_type"] for e in events)
    counts = store.row_counts()
    inference = store.rows("inference_events", "session_id = ?", (sid,))
    assert len(inference) == counts["inference_events"] == kinds["inference.result"] == 86
    live_inference = {e["payload"]["timestamp_us"]: e["sequence_index"] for e in events
                      if e["event_type"] == "inference.result"}
    assert {r["timestamp_us"]: r["sequence_index"] for r in inference} == live_inference
    assert counts["monitoring_state_events"] == kinds["monitoring.state"]
    assert counts["context_snapshots"] == kinds["context.snapshot"] == 86
    stream_devices = [e for e in events if e["event_type"] == "device.status"]
    rows = store.list_device_connections(mixed["device_id"])
    assert len(rows) == 4 + len(stream_devices)  # 4 pre-stream (REST) + the stream events
    assert [r["device_state"] for r in rows][:4] == ["SCANNING", "FOUND", "PAIRING", "CONNECTED"]
    assert [r["session_id"] for r in rows][:4] == [None] * 4
    assert {r["session_id"] for r in rows[4:]} == {sid}
    assert [r["event_type"] for r in rows[4:]] == [
        "STREAM_STARTED", "DEVICE_DISCONNECTED", "RECONNECT_STARTED", "DEVICE_RECONNECTED",
        "STREAM_STARTED", "STREAM_STOPPED"]
    assert [r["sequence_index"] for r in rows[4:]] == [e["sequence_index"] for e in stream_devices]
    assert kinds["waveform.chunk"] == 2880 and "waveform.chunk" not in {
        t for t in counts}  # no per-chunk (or per-sample) relational rows exist at all


def test_session_lifecycle_rows_use_utc_lifecycle_time_not_source_time(mixed) -> None:
    session = mixed["store"].get_session(mixed["session_id"])
    assert session.state.value == "COMPLETED"
    assert session.created_at_us > 1_600_000_000_000_000  # UTC epoch microseconds
    assert session.started_at_us >= session.created_at_us
    assert session.ended_at_us >= session.started_at_us
    inference = mixed["store"].rows("inference_events")
    assert max(r["timestamp_us"] for r in inference) < 600_000_000  # source-relative, distinct


def test_signal_quality_rows_are_written_on_change_only(mixed) -> None:
    store, events = mixed["store"], mixed["events"]
    quality = [(e["payload"]["ecg_quality"], e["payload"]["ppg_quality"]) for e in events
               if e["event_type"] == "quality.status"]
    assert len(quality) == 93
    changes = [q for i, q in enumerate(quality) if i == 0 or q != quality[i - 1]]
    rows = store.rows("signal_quality_events")
    assert [(r["ecg_quality"], r["ppg_quality"]) for r in rows] == changes
    assert 1 < len(rows) < len(quality)
    audit = mixed["app"].state.bridge.audit[mixed["session_id"]]
    assert (audit.quality_events_seen, audit.quality_rows) == (93, len(rows))


def test_quality_deduplication_on_a_simple_sequence() -> None:
    from product.auth.base import AuthIdentity, AuthProviderType
    from product.monitoring.event_adapter import ProductEventAdapter
    from product.persistence.bridge import PersistenceBridge, SessionMeta
    from product.session import (
        MonitoringSession,
        SessionState,
        SimulationProvenance,
        default_runtime_identity,
    )
    store = CapstoneSqliteStore(":memory:")
    store.upsert_user(AuthIdentity(user_id="demo:u", auth_provider=AuthProviderType.DEMO,
                                   auth_session_id="s", demo_mode=True))
    store.insert_device(device_id="D", user_id="demo:u", display_name="n", adapter_type="SIMULATED",
                        source_dataset_id="WEARABLE_SIM_V1", source_mode="SYNTHETIC_PHYSIOLOGY",
                        simulation_version="WEARABLE_SIM_V1", scenario_id="NORMAL_MONITORING",
                        capabilities={})
    store.insert_session(MonitoringSession(
        session_id="S", user_id="demo:u", device_id="D", device_adapter_type="SIMULATED",
        created_at_us=1, state=SessionState.CREATED, runtime=default_runtime_identity(),
        simulation_provenance=SimulationProvenance(
            scenario_id="NORMAL_MONITORING", seed=1, simulation_version="WEARABLE_SIM_V1")))
    bridge = PersistenceBridge(store)
    bridge.register(SessionMeta("S", "D", 3600))
    adapter = ProductEventAdapter("S")
    states = ["VALID", "VALID", "VALID", "UNUSABLE", "UNUSABLE", "VALID"]
    for index, state in enumerate(states):
        bridge.on_event("S", adapter.quality_status(
            {"ecg_quality": state, "ppg_context": None, "timestamp_us": index}))
    rows = store.rows("signal_quality_events")
    assert [r["ecg_quality"] for r in rows] == ["VALID", "UNUSABLE", "VALID"]  # 6 events -> 3 rows
    assert bridge.audit["S"].quality_events_seen == 6 and bridge.audit["S"].quality_rows == 3
    ppg_change = adapter.quality_status({"ecg_quality": "VALID", "timestamp_us": 9,
                                         "ppg_context": {"quality": "DEGRADED"}})
    bridge.on_event("S", ppg_change)  # ppg_quality participates in the comparison
    assert len(store.rows("signal_quality_events")) == 4


# ---- context: raw API evidence vs product projection -------------------------------------------
@pytest.fixture(scope="module")
def withheld(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "withheld.sqlite3"
    app, store = make_persistent_app(path, WithholdingDouble())
    with TestClient(app) as client:
        _, session_id = provisioned_session(client, "NORMAL_MONITORING")
        client.post(f"{BASE}/sessions/{session_id}/start", headers=USER_A)
        events = collect_ws(client, session_id)
    return {"app": app, "store": store, "events": events, "session_id": session_id}


def test_raw_response_context_is_preserved_separately_from_the_product_projection(withheld) -> None:
    store, sid = withheld["store"], withheld["session_id"]
    raw = store.rows("inference_events", "session_id = ?", (sid,))
    product = store.rows("context_snapshots", "session_id = ?", (sid,))
    assert len(raw) == len(product) == 21
    for raw_row, product_row in zip(raw, product, strict=True):
        context = json.loads(raw_row["context_json"])
        assert context["context_available"] is False
        assert context["pr_ppg_bpm"] == 71.5 and context["spo2_pct"] == 97.0
        assert context["spo2_valid"] is True  # the ACTUAL released-response values, unaltered
        assert product_row["context_available"] == 0  # same availability in both
        assert product_row["pr_ppg_bpm"] is None and product_row["spo2_pct"] is None
        assert product_row["spo2_valid"] == 0  # the CAP-003 normalised, product-facing form
        assert product_row["hr_ecg_bpm"] == context["hr_ecg_bpm"]  # nothing fabricated


def test_every_context_withholding_case_is_auditable(withheld) -> None:
    audit = withheld["app"].state.bridge.audit[withheld["session_id"]]
    inference_ts = [e["payload"]["timestamp_us"] for e in withheld["events"]
                    if e["event_type"] == "inference.result"]
    assert audit.withheld_context_timestamps == inference_ts and len(inference_ts) == 21
    live = [e["payload"] for e in withheld["events"] if e["event_type"] == "context.snapshot"]
    assert all(c["pr_ppg_bpm"] is None and c["context_available"] is False for c in live)
    coordinator = withheld["app"].state.runtime_state.sessions[withheld["session_id"]].coordinator
    assert coordinator.telemetry["context_values_withheld"] == 21  # CAP-003's own counter agrees


def test_normal_available_context_is_stored_identically_in_both_places(mixed) -> None:
    store = mixed["store"]
    raw = {r["timestamp_us"]: json.loads(r["context_json"]) for r in store.rows("inference_events")}
    snapshots = {r["timestamp_us"]: r for r in store.rows("context_snapshots")}
    available = [t for t, c in raw.items() if c["context_available"]]
    assert available
    for ts in available:
        assert snapshots[ts]["pr_ppg_bpm"] == raw[ts]["pr_ppg_bpm"]
        assert snapshots[ts]["spo2_pct"] == raw[ts]["spo2_pct"]
    assert mixed["app"].state.bridge.audit[mixed["session_id"]].withheld_context_timestamps == []


def test_context_snapshots_respect_the_bounded_cadence_and_none_exist_for_422_windows(mixed) -> None:
    rows = mixed["store"].rows("context_snapshots")
    times = [r["timestamp_us"] for r in rows]
    assert times == sorted(times) and len(set(times)) == len(times)
    gaps = [b - a for a, b in itertools.pairwise(times)]
    assert min(gaps) >= 5_000_000  # at most one snapshot per 5 s window <= the 1/s ceiling
    unusable = {e["source_timestamp_us"] for e in mixed["events"]
                if e["event_type"] == "quality.status"
                and e["payload"]["ecg_quality"] == "UNUSABLE"}
    assert unusable and not unusable & set(times)  # no context fabricated for 422 windows


# ---- waveform preview --------------------------------------------------------------------------
def test_waveform_preview_is_bounded_ecg_only_and_keeps_the_gap_as_null(mixed) -> None:
    store = mixed["store"]
    (row,) = store.rows("waveform_previews")
    assert row["channel"] == "ECG" and row["source_rate_hz"] == 360
    assert row["encoding"] == "JSON_ZLIB_V1" and row["start_timestamp_us"] == 0
    points = preview_module.decode(row["data"])
    assert len(points) == row["point_count"] <= 4000
    assert row["decimation_factor"] == 44  # ceil(172_800 / 4000)
    nulls = [i for i, p in enumerate(points) if p is None]
    first, last = 118800 // 44, 124199 // 44  # the outage in preview coordinates
    assert nulls and first <= nulls[0] and nulls[-1] <= last + 1
    assert set(range(first + 1, last)) <= set(nulls)
    assert all(p is None or isinstance(p, int) for p in points)
    audit = mixed["app"].state.bridge.audit[mixed["session_id"]]
    assert audit.preview["source_samples_seen"] == 172800 and audit.preview["point_count"] <= 4000
    assert audit.preview["null_points"] == len(nulls)
    assert len(row["data"]) < 172800  # a bounded blob, not the raw stream


def test_waveform_preview_is_deterministic_and_never_substitutes_zero() -> None:
    accumulator = preview_module.PreviewAccumulator(total_samples=20, max_points=5)
    assert accumulator.factor == 4
    samples = [1, 5, 2, 8, None, None, None, None, 7, 3, 9, 1, 4, 4, 4, 4, None, 6, None, None]
    accumulator.add_chunk(0, 0, samples[:10])
    accumulator.add_chunk(10, 27_777, samples[10:])
    points = accumulator.finish()
    assert points == [8, None, 9, 4, 6]  # max-deviation per bucket; the all-missing bucket is null
    again = preview_module.PreviewAccumulator(20, 5)
    again.add_chunk(0, 0, samples[:10])
    again.add_chunk(10, 27_777, samples[10:])
    assert again.finish() == points
    assert preview_module.encode(points) == preview_module.encode(points)
    assert zlib.decompress(preview_module.encode(points))  # plain stdlib encoding
    with pytest.raises(ValueError, match="EXCEEDS"):
        over = preview_module.PreviewAccumulator(total_samples=4, max_points=1)
        over.factor = 1
        over.add_chunk(0, 0, [1, 2, 3, 4])
        over.finish()


def test_preview_code_is_not_reachable_from_the_scientific_or_monitoring_path() -> None:
    for path in ("product/monitoring/coordinator.py", "product/monitoring/mux.py",
                 "product/monitoring/event_adapter.py", "product/inference/client.py",
                 "simulation/stream_runtime_v2013.py"):
        assert "persistence" not in (ROOT / path).read_text().replace(
            "product.monitoring.runtime_state", ""), path
    assert "preview" not in (ROOT / "product/inference/client.py").read_text().lower()


# ---- immutability ------------------------------------------------------------------------------
def test_session_runtime_identity_cannot_be_changed_after_creation(mixed) -> None:
    store, sid = mixed["store"], mixed["session_id"]
    for column in RUNTIME_COLUMNS:
        with pytest.raises(sqlite3.IntegrityError, match="RUNTIME_IDENTITY_IMMUTABLE"):
            store._run(f"UPDATE monitoring_sessions SET {column} = 'X' WHERE session_id = ?",
                       (sid,))
    import inspect
    update_sig = inspect.signature(CapstoneSqliteStore.update_session_state).parameters
    assert set(update_sig) == {"self", "session_id", "state", "started_at_us", "ended_at_us"}
    session = store.get_session(sid)
    assert session.runtime.model_id == "MODEL_V2_FINAL" and session.runtime.calibration_id == "CAL_V2"
    assert session.runtime.software_system_id == "SOFTWARE_SYSTEM_V2"
    assert session.runtime.gateway_artifact_id == "GATEWAY_ARTIFACT_V2"


def test_the_persisted_runtime_identity_is_the_frozen_default_binding(mixed) -> None:
    lock = json.loads((ROOT / "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json").read_text())
    session = mixed["store"].get_session(mixed["session_id"])
    assert session.runtime.model_id == lock["identity"]["model_id"]
    assert session.runtime.calibration_id == lock["identity"]["calibration_id"]
    assert session.runtime.preprocess_id == lock["identity"]["preprocess_id"]
    assert session.runtime.alert_policy_binding_id == lock["identity"]["alert_policy_binding_id"]
    assert load_contract("session")["required_runtime_identity"] == session.runtime.model_dump()


def test_no_per_sample_sql_writes_happen_during_a_full_session(tmp_path) -> None:
    app, store = make_persistent_app(tmp_path / "w.sqlite3", StrictInferenceDouble())
    statements: list[str] = []
    store._connection.set_trace_callback(statements.append)
    with TestClient(app) as client:
        _, sid = provisioned_session(client, "MIXED_MONITORING_SESSION")
        client.post(f"{BASE}/sessions/{sid}/start", headers=USER_A)
        collect_ws(client, sid)
    inserts = [s for s in statements if s.lstrip().upper().startswith("INSERT")]
    delivered = 172_800
    assert 100 < len(inserts) < 700 and len(inserts) * 100 < delivered  # ~1 write per 600 samples
    targets = {s.split()[2] for s in inserts}
    assert not {t for t in targets if "sample" in t or "raw_ecg" in t or "waveform_chunks" in t}
    assert Counter(s.split()[2] for s in inserts)["waveform_previews"] == 1
