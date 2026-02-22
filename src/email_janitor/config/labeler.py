from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailLabelerConfig(BaseSettings):
    """Configuration for the email labeler agent.

    Environment variables use the prefix EMAIL_LABELER_.
    """

    model_config = SettingsConfigDict(env_prefix="EMAIL_LABELER_", case_sensitive=False, extra="ignore")
