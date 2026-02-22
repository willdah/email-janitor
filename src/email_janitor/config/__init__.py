from .app import AppConfig
from .classifier import EmailClassifierConfig
from .collector import EmailCollectorConfig
from .gmail import GmailConfig
from .labeler import EmailLabelerConfig

__all__ = [
    "AppConfig",
    "EmailClassifierConfig",
    "EmailCollectorConfig",
    "EmailLabelerConfig",
    "GmailConfig",
]
