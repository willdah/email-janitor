"""Pydantic models for agent data contracts."""

from .schemas import (
    EmailData,
    EmailCollectionOutput,
    EmailClassificationInput,
    EmailClassificationOutput,
    ClassificationResult,
    ClassificationCollectionOutput,
    ProcessingResult,
    ProcessingSummaryOutput,
)

__all__ = [
    "EmailData",
    "EmailCollectionOutput",
    "EmailClassificationInput",
    "EmailClassificationOutput",
    "ClassificationResult",
    "ClassificationCollectionOutput",
    "ProcessingResult",
    "ProcessingSummaryOutput",
]
