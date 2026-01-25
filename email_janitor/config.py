"""Configuration settings for email classification system."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models.schemas import EmailCategory


class ClassificationConfig(BaseSettings):
    """Configuration for email classification with critic review.

    All settings can be overridden via environment variables with prefix 'CLASSIFICATION_'.
    Example: CLASSIFICATION_CONFIDENCE_THRESHOLD=0.9
    """

    model_config = SettingsConfigDict(
        env_prefix="CLASSIFICATION_", case_sensitive=False, extra="ignore"
    )

    confidence_threshold: float = Field(
        default=0.95, ge=0.0, le=1.0, description="Threshold to skip critic"
    )
    max_refinements: int = Field(
        default=1, ge=0, le=5, description="Max refinement iterations"
    )
    classifier_weight: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Weight for classifier in consensus"
    )
    critic_weight: float = Field(
        default=0.4, ge=0.0, le=1.0, description="Weight for critic in consensus"
    )
    escalation_category: EmailCategory = Field(
        default=EmailCategory.ACTIONABLE,
        description="Default category when max refinements reached",
    )

    def get_consensus_weights(self) -> dict[str, float]:
        """Get consensus weights as a dictionary."""
        # Normalize weights to ensure they sum to 1.0
        total = self.classifier_weight + self.critic_weight
        if total == 0:
            return {"classifier": 0.5, "critic": 0.5}
        return {
            "classifier": self.classifier_weight / total,
            "critic": self.critic_weight / total,
        }
