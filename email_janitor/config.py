"""Configuration settings for email classification system."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models.schemas import EmailCategory


class ClassificationConfig(BaseSettings):
    """Configuration for email classification.

    All settings can be overridden via environment variables with prefix 'CLASSIFICATION_'.
    Example: CLASSIFICATION_CONFIDENCE_THRESHOLD=0.9
    """

    model_config = SettingsConfigDict(
        env_prefix="CLASSIFICATION_", case_sensitive=False, extra="ignore"
    )

    confidence_threshold: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for classification",
    )
