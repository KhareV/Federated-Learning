"""Request/response models of the CAP-003 product API. Request models forbid extra fields, so a
model/checkpoint/calibration/threshold/gateway selector can never be smuggled into a body."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CreateSimulatedDeviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    scenario_id: str | None = Field(default=None, min_length=1, max_length=80)


class SystemInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_api_version: str
    capstone_protocol: str
    monitoring_protocol: str
    software_system: str
    model_id: str
    calibration_id: str
    api_contract_version: str
    hardware_mode: str
    physical_hardware_available: bool
    persistence_mode: str
    federation_runtime: str
    auth_status: str
    claim: str
