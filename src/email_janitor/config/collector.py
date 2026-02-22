from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailCollectorConfig(BaseSettings):
    """Configuration for the email collector agent.

    Environment variables use the prefix EMAIL_COLLECTOR_.
    """

    model_config = SettingsConfigDict(
        env_prefix="EMAIL_COLLECTOR_", case_sensitive=False, extra="ignore"
    )
