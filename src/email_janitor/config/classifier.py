from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailClassifierConfig(BaseSettings):
    """Configuration for the email classifier agent.

    Environment variables use the prefix EMAIL_CLASSIFIER_.
    Example: EMAIL_CLASSIFIER_CONFIDENCE_THRESHOLD=4.0
    """

    model_config = SettingsConfigDict(env_prefix="EMAIL_CLASSIFIER_", case_sensitive=False, extra="ignore")

    confidence_threshold: float = Field(
        default=4.0,
        ge=1.0,
        le=5.0,
        description="Minimum confidence score (1-5) required to accept a classification",
    )
    model: str = Field(
        default="ollama_chat/llama3.1:8b",
        description="LiteLLM model identifier to use for classification",
    )
    llm_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Hard timeout (seconds) per LLM call. Exceeding this counts as a retryable failure.",
    )
    llm_num_retries: int = Field(
        default=3,
        ge=0,
        description="Built-in LiteLLM retry count for transient LLM errors (timeouts, 5xx, connection).",
    )
