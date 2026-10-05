"""Schema for CAPSTONE_SQLITE_STORE_V1, generated from contracts/capstone/storage_policy_v2.json.

The policy JSON is the single source of truth for tables/columns/keys/indexes. This module adds only
integrity hardening that the policy states in prose: a CHECK that a SIMULATED device carries its
scenario_id, boolean CHECKs, and BEFORE UPDATE triggers that make the session runtime identity and
the device scenario immutable after creation.
"""

from __future__ import annotations

from typing import Any

from product.contracts import ROOT

POLICY_PATH = ROOT / "contracts" / "capstone" / "storage_policy_v2.json"
SCHEMA_VERSION = 1
SQL_TYPES = {"TEXT": "TEXT", "INTEGER": "INTEGER", "REAL": "REAL", "BLOB": "BLOB"}
RUNTIME_COLUMNS = ("model_id", "calibration_id", "preprocess_id", "alert_policy_id",
                   "alert_policy_binding_id", "gateway_artifact_id", "api_contract_version",
                   "software_system_id")
BOOLEAN_COLUMNS = {"users": ("demo_mode",), "device_connections": ("recoverable",)}


def ddl_statements(policy: dict[str, Any]) -> list[str]:
    statements: list[str] = []
    for entity in policy["entities"]:
        table = entity["table"]
        parts = []
        for name, spec in entity["columns"].items():
            nullable = spec.endswith("?")
            sql_type = SQL_TYPES[spec.rstrip("?")]
            not_null = "" if nullable else " NOT NULL"
            parts.append(f"{name} {sql_type}{not_null}")
        parts.append(f"PRIMARY KEY ({entity['primary_key']})")
        for fk in entity["foreign_keys"]:
            ref_table, ref_column = fk["references"].split(".")
            parts.append(f"FOREIGN KEY ({fk['column']}) REFERENCES {ref_table}({ref_column})")
        for column in BOOLEAN_COLUMNS.get(table, ()):
            parts.append(f"CHECK ({column} IN (0, 1))")
        if table == "devices":
            parts.append("CHECK (adapter_type <> 'SIMULATED' OR scenario_id IS NOT NULL)")
        statements.append(f"CREATE TABLE {table} ({', '.join(parts)})")
        for index in entity["indexes"]:
            unique = "UNIQUE " if index["unique"] else ""
            statements.append(f"CREATE {unique}INDEX {index['name']} ON {table} "
                              f"({', '.join(index['columns'])})")
    statements.append(
        "CREATE TRIGGER trg_sessions_runtime_identity_immutable "
        f"BEFORE UPDATE OF {', '.join(RUNTIME_COLUMNS)} ON monitoring_sessions "
        "BEGIN SELECT RAISE(ABORT, 'RUNTIME_IDENTITY_IMMUTABLE'); END")
    statements.append(
        "CREATE TRIGGER trg_devices_scenario_immutable "
        "BEFORE UPDATE OF scenario_id, user_id ON devices "
        "BEGIN SELECT RAISE(ABORT, 'DEVICE_SCENARIO_AND_OWNER_IMMUTABLE'); END")
    return statements
