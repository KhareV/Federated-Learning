"""Application-level server visibility instrumentation for T028."""

from __future__ import annotations

from dataclasses import dataclass, field

from flwr.app import Message
from flwr.common.secure_aggregation.secaggplus_constants import Key


@dataclass
class ServerVisibilityProbe:
    path_id: str
    clear_individual_update_count: int = 0
    masked_vector_count: int = 0
    aggregate_visible: bool = False
    client_ids_visible: set[int] = field(default_factory=set)
    weight_metadata_visible: bool = False
    key_share_metadata_count: int = 0
    object_types: set[str] = field(default_factory=set)

    def observe_plain_update(self, client_id: int, *, has_arrays: bool, has_weight: bool) -> None:
        self.client_ids_visible.add(client_id)
        self.object_types.add("individual_clear_model_arrays")
        self.weight_metadata_visible |= has_weight
        if has_arrays:
            self.clear_individual_update_count += 1

    def observe_protected_reply(self, message: Message) -> None:
        self.client_ids_visible.add(message.metadata.src_node_id)
        self.object_types.add(type(message.content).__name__)
        for record in message.content.array_records.values():
            if len(record) > 0:
                self.clear_individual_update_count += 1
                self.object_types.add("individual_clear_model_arrays")
        for record in message.content.config_records.values():
            keys = set(record.keys())
            if Key.MASKED_PARAMETERS in keys:
                self.masked_vector_count += 1
                self.object_types.add("masked_vector_bytes")
            if keys & {
                Key.PUBLIC_KEY_1,
                Key.PUBLIC_KEY_2,
                Key.CIPHERTEXT_LIST,
                Key.SHARE_LIST,
            }:
                self.key_share_metadata_count += 1
                self.object_types.add("key_share_protocol_metadata")

    def observe_aggregate(self) -> None:
        self.aggregate_visible = True
        self.object_types.add("aggregate_model_arrays")

    def as_dict(self) -> dict[str, object]:
        return {
            "path_id": self.path_id,
            "individual_clear_model_update_arrays_visible": self.clear_individual_update_count,
            "masked_vectors_visible": self.masked_vector_count,
            "aggregate_visible": self.aggregate_visible,
            "client_ids_visible": sorted(self.client_ids_visible),
            "weight_count_metadata_visible": self.weight_metadata_visible,
            "key_share_metadata_objects_visible": self.key_share_metadata_count,
            "object_types": sorted(self.object_types),
            "sensitive_fields_intentionally_not_persisted": [
                "private_keys",
                "raw_secret_shares",
                "protected_clear_client_updates",
            ],
        }


def require_visibility_contract(
    plain: ServerVisibilityProbe, protected: ServerVisibilityProbe
) -> None:
    if plain.clear_individual_update_count == 0:
        raise RuntimeError("VISIBILITY_PROBE_NOT_SENSITIVE")
    if protected.clear_individual_update_count != 0:
        raise RuntimeError("PROTECTED_CLEAR_UPDATE_EXPOSED")
    if not protected.aggregate_visible:
        raise RuntimeError("PROTECTED_AGGREGATE_UNAVAILABLE")
