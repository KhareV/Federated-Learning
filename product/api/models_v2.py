"""PRODUCT_API_CONTRACT_V2 models (additive successor of the CAP-003 models)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from product.api.models import SystemInfo


class SystemInfoV2(SystemInfo):
    """Every V1 field is retained; V2 adds authentication/persistence metadata only."""

    product_api_implementation: str
    auth_provider: str
    demo_mode: bool


class CreateSessionRequest(BaseModel):
    """Exactly the frozen request fields. Any extra field (model, checkpoint, ...) is rejected."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=120)
    scenario_id: str = Field(min_length=1, max_length=80)
