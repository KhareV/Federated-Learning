"""Typed product-engineering errors (CAPSTONE_PRODUCT_API_V1). No diagnostic/medical wording."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ProductErrorCode(StrEnum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    INVALID_STATE = "INVALID_STATE"
    INVALID_REQUEST = "INVALID_REQUEST"
    INFERENCE_INTEGRATION_ERROR = "INFERENCE_INTEGRATION_ERROR"
    INTERNAL_PRODUCT_ERROR = "INTERNAL_PRODUCT_ERROR"


HTTP_STATUS = {
    ProductErrorCode.UNAUTHENTICATED: 401, ProductErrorCode.FORBIDDEN: 403,
    ProductErrorCode.NOT_FOUND: 404, ProductErrorCode.INVALID_STATE: 409,
    ProductErrorCode.INVALID_REQUEST: 400, ProductErrorCode.INFERENCE_INTEGRATION_ERROR: 502,
    ProductErrorCode.INTERNAL_PRODUCT_ERROR: 500,
}


class ProductError(Exception):
    def __init__(self, code: ProductErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code, self.message = code, message

    @property
    def status_code(self) -> int:
        return HTTP_STATUS[self.code]


class ProductErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ProductErrorCode
    message: str


class ProductErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ProductErrorBody
