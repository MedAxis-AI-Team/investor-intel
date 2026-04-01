from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SCHEMA_VERSION = "2026-03-03"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = Field(
        default="development", alias="ENVIRONMENT"
    )

    anthropic_api_key: str = Field(alias="ANTHROPIC_API_KEY")

    request_timeout_seconds: float = Field(default=20.0, alias="REQUEST_TIMEOUT_SECONDS")

    llm_model: str = Field(default="claude-sonnet-4-20250514", alias="LLM_MODEL")
    llm_max_tokens: int = Field(default=1024, alias="LLM_MAX_TOKENS", ge=1, le=8192)

    rate_limit_window_seconds: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS")
    rate_limit_max_requests: int = Field(default=60, alias="RATE_LIMIT_MAX_REQUESTS")

    confidence_high_threshold: float = Field(default=0.8, alias="CONFIDENCE_HIGH_THRESHOLD", ge=0.0, le=1.0)
    confidence_medium_threshold: float = Field(default=0.6, alias="CONFIDENCE_MEDIUM_THRESHOLD", ge=0.0, le=1.0)
    evidence_missing_penalty: float = Field(default=0.25, alias="EVIDENCE_MISSING_PENALTY", ge=0.0, le=1.0)

    score_weight_thesis_alignment: float = Field(default=0.30, alias="SCORE_WEIGHT_THESIS_ALIGNMENT", ge=0.0, le=1.0)
    score_weight_stage_fit: float = Field(default=0.25, alias="SCORE_WEIGHT_STAGE_FIT", ge=0.0, le=1.0)
    score_weight_check_size_fit: float = Field(default=0.15, alias="SCORE_WEIGHT_CHECK_SIZE_FIT", ge=0.0, le=1.0)
    score_weight_scientific_regulatory_fit: float = Field(default=0.15, alias="SCORE_WEIGHT_SCIENTIFIC_REGULATORY_FIT", ge=0.0, le=1.0)
    score_weight_recency: float = Field(default=0.10, alias="SCORE_WEIGHT_RECENCY", ge=0.0, le=1.0)
    score_weight_geography: float = Field(default=0.05, alias="SCORE_WEIGHT_GEOGRAPHY", ge=0.0, le=1.0)

    database_url: str = Field(default="", alias="DATABASE_URL")

    @model_validator(mode="after")
    def _validate_thresholds_and_weights(self) -> "Settings":
        if self.confidence_high_threshold < self.confidence_medium_threshold:
            raise ValueError("CONFIDENCE_HIGH_THRESHOLD must be >= CONFIDENCE_MEDIUM_THRESHOLD")

        total = (
            self.score_weight_thesis_alignment
            + self.score_weight_stage_fit
            + self.score_weight_check_size_fit
            + self.score_weight_scientific_regulatory_fit
            + self.score_weight_recency
            + self.score_weight_geography
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError("Score weights must sum to 1.0")

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
