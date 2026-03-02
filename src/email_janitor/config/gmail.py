from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GmailConfig(BaseSettings):
    """Configuration for the Gmail integration.

    Environment variables use the prefix GMAIL_.
    Example: GMAIL_PROCESSED_LABEL=MyJanitor-Done
    """

    model_config = SettingsConfigDict(env_prefix="GMAIL_", case_sensitive=False, extra="ignore")

    processed_label: str = Field(
        default="janitor/done",
        description="Gmail label applied to every email after processing to prevent reprocessing",
    )
    urgent_label: str = Field(
        default="janitor/urgent",
        description="Gmail label applied to emails classified as URGENT (kept in inbox)",
    )
    personal_label: str = Field(
        default="janitor/personal",
        description="Gmail label applied to emails classified as PERSONAL (kept in inbox)",
    )
    noise_label: str = Field(
        default="janitor/noise",
        description="Gmail label applied to emails classified as NOISE",
    )
    promotional_label: str = Field(
        default="janitor/promotions",
        description="Gmail label applied to emails classified as PROMOTIONAL",
    )
    informational_label: str = Field(
        default="janitor/newsletters",
        description="Gmail label applied to emails classified as INFORMATIONAL",
    )
    inbox_query: str = Field(
        default="in:inbox -in:sent",
        description="Base Gmail search query for fetching emails (processed_label exclusion is appended automatically)",
    )
