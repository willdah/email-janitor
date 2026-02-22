from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Top-level application configuration.

    Environment variables use the prefix EMAIL_JANITOR_.
    Example: EMAIL_JANITOR_POLL_INTERVAL=30
    """

    model_config = SettingsConfigDict(env_prefix="EMAIL_JANITOR_", case_sensitive=False, extra="ignore")

    app_name: str = Field(
        default="Email-Janitor",
        description="Application name passed to the ADK runner",
    )
    user_id: str = Field(
        default="email-janitor-user",
        description="User ID for ADK session management",
    )
    poll_interval: int = Field(
        default=10,
        ge=1,
        description="Seconds to wait between processing runs",
    )
