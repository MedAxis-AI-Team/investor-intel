from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiError(BaseModel):
    code: str
    message: str
    details: dict | None = None


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    request_id: str | None = None
    data: T | None = None
    error: ApiError | None = None


ConfidenceTier = Literal["HIGH", "MEDIUM", "LOW"]


class Confidence(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    tier: ConfidenceTier
