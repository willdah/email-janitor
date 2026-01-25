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
    body: Optional[str] = Field(default=None, description="Email body text (truncated if long)")
    snippet: Optional[str] = Field(default=None, description="Email snippet if body not available")


class EmailClassificationOutput(BaseModel):
    """Output schema for EmailClassifier LLM sub-agent."""

    category: EmailCategory = Field(description="Classification category")
    reasoning: str = Field(description="One-sentence explanation citing specific keywords found")
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Confidence score 0-1"
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
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence score")
    critic_status: Literal["skipped", "approved", "rejected", "escalated"] = Field(
        default="skipped", description="Critic review status"
    )
    refinement_count: int = Field(
        default=0, ge=0, description="Number of refinement iterations"
    )
    consensus_confidence: Optional[float] = Field(
        default=None, description="Weighted consensus confidence"
    )
    escalation_reason: Optional[str] = Field(
        default=None, description="Reason if escalated"
    )


class ClassificationCollectionOutput(BaseModel):
    """EmailClassifier's output schema."""

    count: int = Field(description="Number of classifications")
    classifications: list[ClassificationResult] = Field(description="List of classification results")


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
    errors: Optional[list[str]] = Field(default=None, description="List of error messages if any")


class CriticReview(BaseModel):
    """Output schema for CriticAgent review."""

    approved: bool = Field(description="Whether the classification is approved")
    alternative_category: Optional[EmailCategory] = Field(
        default=None, description="Alternative if rejected"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Critic's confidence in review"
    )
    critique: str = Field(description="Detailed critique explaining approval/rejection")
    suggested_reasoning: Optional[str] = Field(
        default=None, description="Improved reasoning if rejected"
    )


class CriticInput(BaseModel):
    """Input schema for CriticAgent."""

    original_email: EmailClassificationInput = Field(
        description="Original email to be reviewed"
    )
    classification_output: EmailClassificationOutput = Field(
        description="Classification output to review"
    )
    email_body: Optional[str] = Field(
        default=None, description="Full email body for context"
    )
