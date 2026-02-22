"""Pydantic models for agent data contracts."""

from .schemas import (
    ClassificationCollectionOutput,
    ClassificationResult,
    EmailClassificationInput,
    EmailClassificationOutput,
    EmailCollectionOutput,
    EmailData,
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
