"""Tests for Pydantic Settings configuration classes."""

import pytest
from pydantic import ValidationError

from email_janitor.config import (
    AppConfig,
    DatabaseConfig,
    EmailClassifierConfig,
    GmailConfig,
)


class TestAppConfig:
    def test_defaults(self):
        cfg = AppConfig()
        assert cfg.app_name == "EmailJanitor"
        assert cfg.user_id == "email-janitor-user"
        assert cfg.poll_interval == 10

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("EMAIL_JANITOR_POLL_INTERVAL", "30")
        cfg = AppConfig()
        assert cfg.poll_interval == 30

    def test_poll_interval_min(self):
        with pytest.raises(ValidationError):
            AppConfig(poll_interval=0)


class TestEmailClassifierConfig:
    def test_defaults(self):
        cfg = EmailClassifierConfig()
        assert cfg.model == "ollama_chat/llama3.1:8b"
        assert cfg.confidence_threshold == 4.0

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("EMAIL_CLASSIFIER_MODEL", "openai/gpt-4o")
        cfg = EmailClassifierConfig()
        assert cfg.model == "openai/gpt-4o"

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            EmailClassifierConfig(confidence_threshold=0.5)
        with pytest.raises(ValidationError):
            EmailClassifierConfig(confidence_threshold=6.0)


class TestGmailConfig:
    def test_defaults(self):
        cfg = GmailConfig()
        assert cfg.processed_label == "janitor/done"
        assert cfg.urgent_label == "janitor/urgent"
        assert cfg.personal_label == "janitor/personal"
        assert cfg.noise_label == "janitor/noise"
        assert cfg.promotional_label == "janitor/promotions"
        assert cfg.informational_label == "janitor/newsletters"
        assert cfg.inbox_query == "in:inbox -in:sent"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("GMAIL_NOISE_LABEL", "custom/noise")
        cfg = GmailConfig()
        assert cfg.noise_label == "custom/noise"


class TestDatabaseConfig:
    def test_default_path(self):
        cfg = DatabaseConfig()
        assert str(cfg.path) == "email_janitor.db"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DATABASE_PATH", "/data/test.db")
        cfg = DatabaseConfig()
        assert str(cfg.path) == "/data/test.db"
