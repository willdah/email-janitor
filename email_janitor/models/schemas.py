"""Pydantic models defining data contracts between agents."""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class EmailCategory(str, Enum):
    """Email classification categories."""

    ACTIONABLE = "ACTIONABLE"
    INFORMATIONAL = "INFORMATIONAL"
    PROMOTIONAL = "PROMOTIONAL"
    NOISE = "NOISE"


class EmailData(BaseModel):
    """Individual email data structure."""

    id: str = Field(description="Gmail message ID")
    sender: str = Field(description="Email sender address")
    recipient: str = Field(description="Email recipient address")
    subject: str = Field(description="Email subject line")
    date: Optional[datetime] = Field(default=None, description="Email date")
    snippet: Optional[str] = Field(default=None, description="Email snippet/preview")
    thread_id: Optional[str] = Field(default=None, description="Gmail thread ID")
    labels: list[str] = Field(default_factory=list, description="Gmail labels")


class EmailCollectionOutput(BaseModel):
    """EmailCollector's output schema."""

    count: int = Field(description="Number of emails collected")
    emails: list[EmailData] = Field(description="List of collected emails")


class EmailClassificationInput(BaseModel):
    """Input schema for EmailClassifier LLM sub-agent."""

    sender: str = Field(description="Email sender address")
    subject: str = Field(description="Email subject line")
    body: Optional[str] = Field(
        default=None, description="Email body text (truncated if long)"
    )
    snippet: Optional[str] = Field(
        default=None, description="Email snippet if body not available"
    )


class EmailClassificationOutput(BaseModel):
    """Output schema for EmailClassifier LLM sub-agent."""

    category: EmailCategory = Field(description="Classification category")
    reasoning: str = Field(
        description="One-sentence explanation citing specific keywords found"
    )
    confidence: float = Field(
        default=3.0, ge=1.0, le=5.0, description="Confidence score 1-5"
    )
    keywords_found: list[str] = Field(
        default_factory=list, description="Key terms that influenced classification"
    )


class ClassificationResult(BaseModel):
    """Full classification result with email metadata."""

    email_id: str = Field(description="Gmail message ID")
    sender: str = Field(description="Email sender address")
    subject: str = Field(description="Email subject line")
    classification: EmailCategory = Field(description="Classification category")
    reasoning: str = Field(description="Classification reasoning")
    confidence: float = Field(
        default=3.0, ge=1.0, le=5.0, description="Confidence score 1-5"
    )
    refinement_count: int = Field(
        default=0, ge=0, description="Number of refinement iterations"
    )


class ClassificationCollectionOutput(BaseModel):
    """EmailClassifier's output schema."""

    count: int = Field(description="Number of classifications")
    classifications: list[ClassificationResult] = Field(
        description="List of classification results"
    )


class ProcessingResult(BaseModel):
    """Individual email processing result."""

    email_id: str = Field(description="Gmail message ID")
    sender: str = Field(description="Email sender address")
    subject: str = Field(description="Email subject line")
    classification: EmailCategory = Field(description="Classification category")
    action: str = Field(description="Action taken (label applied or no action)")
    status: str = Field(description="Processing status: success or error")


class ProcessingSummaryOutput(BaseModel):
    """EmailProcessor's output schema."""

    total_processed: int = Field(description="Total number of emails processed")
    label_counts: dict[str, int] = Field(description="Count of emails per label/action")
    errors_count: int = Field(description="Number of errors encountered")
    errors: Optional[list[str]] = Field(
        default=None, description="List of error messages if any"
    )
