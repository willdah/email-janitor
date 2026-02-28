from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """Configuration for the SQLite persistence layer.

    Environment variables use the prefix DATABASE_.
    Example: DATABASE_PATH=/data/email_janitor.db
    """

    model_config = SettingsConfigDict(env_prefix="DATABASE_", case_sensitive=False, extra="ignore")

    path: Path = Field(
        default=Path("email_janitor.db"),
        description=(
            "Path to the SQLite database file. "
            "In Docker, set this to a path inside a mounted volume, e.g. /data/email_janitor.db"
        ),
    )
