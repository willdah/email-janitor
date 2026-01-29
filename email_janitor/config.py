"""Configuration settings for email classification system."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models.schemas import EmailCategory


class ClassificationConfig(BaseSettings):
    """Configuration for email classification.

    All settings can be overridden via environment variables with prefix 'CLASSIFICATION_'.
    Example: CLASSIFICATION_CONFIDENCE_THRESHOLD=4.0
    """

    model_config = SettingsConfigDict(
        env_prefix="CLASSIFICATION_", case_sensitive=False, extra="ignore"
    )

    confidence_threshold: float = Field(
        default=4.0,
        ge=1.0,
        le=5.0,
        description="Confidence threshold for classification (1-5 scale)",
    )
