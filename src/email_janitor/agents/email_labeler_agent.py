"""
EmailLabeler - A Custom Agent for labeling emails based on classifications.

This agent retrieves classifications from EmailClassifierAgent's agent_states and
applies appropriate Gmail labels to each email based on the classification category.
Low-confidence classifications are routed to the review label (kept in inbox) so
they can be reviewed before trusting the pipeline's decision. All emails remain
unread after processing.
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.genai import types
from simplegmail.message import Message

from ..config import EmailClassifierConfig, EmailLabelerConfig, GmailConfig
from ..database import PersistRunFn
from ..observability import get_logger
from ..schemas.schemas import (
    ClassificationCollectionOutput,
    EmailCategory,
    ProcessingResult,
    ProcessingSummaryOutput,
)
from ..tools.gmail_client import apply_label_to_message

_logger = get_logger(__name__)


@dataclass
class LabelDecision:
    """Outcome of the classification → Gmail-label mapping.

    ``status`` is either ``"success"`` (pipeline trusted the classification) or
    ``"needs_review"`` (confidence fell below the threshold, so the category
    label was skipped and the email was left in the inbox under the review label).
    """

    label: str
    remove_inbox: bool
    action: str
    status: str


def select_label_decision(
    category: EmailCategory,
    confidence: float,
    *,
    gmail_config: GmailConfig,
    confidence_threshold: float | None,
) -> LabelDecision:
    """Pure mapping from (category, confidence) to the Gmail label to apply.

    When ``confidence_threshold`` is set and the classification's confidence is
    below it, the email is routed to the review label and kept in the inbox,
    regardless of the predicted category. This prevents low-confidence
    classifications from silently archiving emails.
    """
    if confidence_threshold is not None and confidence < confidence_threshold:
        return LabelDecision(
            label=gmail_config.review_label,
            remove_inbox=False,
            action=(
                f"Confidence {confidence:.1f} < threshold {confidence_threshold:.1f}; "
                f"applied '{gmail_config.review_label}' and kept in inbox"
            ),
            status="needs_review",
        )

    if category == EmailCategory.NOISE:
        return LabelDecision(
            label=gmail_config.noise_label,
            remove_inbox=True,
            action=f"Applied '{gmail_config.noise_label}' label and removed from inbox",
            status="success",
        )
    if category == EmailCategory.PROMOTIONAL:
        return LabelDecision(
            label=gmail_config.promotional_label,
            remove_inbox=True,
            action=f"Applied '{gmail_config.promotional_label}' label and removed from inbox",
            status="success",
        )
    if category == EmailCategory.INFORMATIONAL:
        return LabelDecision(
            label=gmail_config.informational_label,
            remove_inbox=True,
            action=f"Applied '{gmail_config.informational_label}' label and removed from inbox",
            status="success",
        )
    if category == EmailCategory.URGENT:
        return LabelDecision(
            label=gmail_config.urgent_label,
            remove_inbox=False,
            action=f"Applied '{gmail_config.urgent_label}' label and kept in inbox",
            status="success",
        )
    if category == EmailCategory.PERSONAL:
        return LabelDecision(
            label=gmail_config.personal_label,
            remove_inbox=False,
            action=f"Applied '{gmail_config.personal_label}' label and kept in inbox",
            status="success",
        )

    # Unknown enum value — bubbles up as an error in the agent loop.
    raise ValueError(f"Unknown classification category: {category}")


class EmailLabelerAgent(BaseAgent):
    """
    A Custom Agent that labels emails based on classifications.

    Confidence threshold behavior: when ``confidence_threshold`` is set,
    classifications with confidence below it receive the review label and
    remain in the inbox instead of being archived to their category label.
    """

    def __init__(
        self,
        config: EmailLabelerConfig,
        name: str = "EmailLabelerAgent",
        description: str | None = None,
        persist_run: PersistRunFn | None = None,
        confidence_threshold: float | None = None,
    ):
        default_description = (
            "An agent that labels emails based on classifications and applies appropriate Gmail labels."
        )
        super().__init__(
            name=name,
            description=description or default_description,
        )
        self._config = config
        self._gmail_config = GmailConfig()
        self._persist_run = persist_run
        self._confidence_threshold = confidence_threshold

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """
        Custom execution logic for the EmailLabeler agent.

        Args:
            ctx: The invocation context containing session state and user input

        Yields:
            Events containing processing results
        """
        collection_output: ClassificationCollectionOutput | None = None
        final_classifications_data = ctx.session.state.get("final_classifications")
        if final_classifications_data:
            try:
                collection_output = ClassificationCollectionOutput.model_validate(final_classifications_data)
            except Exception:
                pass

        if not collection_output:
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(
                    parts=[types.Part(text="No classifications found. EmailClassifierAgent must run first.")]
                ),
            )
            yield event
            return

        classification_results = collection_output.classifications
        if not classification_results:
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(parts=[types.Part(text="No classifications to process.")]),
            )
            yield event
            return

        collector_state = ctx.agent_states.get("EmailCollectorAgent")
        if not collector_state or "emails" not in collector_state:
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(parts=[types.Part(text="No emails found. EmailCollectorAgent must run first.")]),
            )
            yield event
            return

        emails: list[Message] = collector_state["emails"]
        email_map: dict[str, Message] = {email.id: email for email in emails}

        gc = self._gmail_config

        processing_results = []
        db_entries: list[dict] = []
        label_counts: dict[str, int] = {
            gc.noise_label: 0,
            gc.promotional_label: 0,
            gc.informational_label: 0,
            gc.urgent_label: 0,
            gc.personal_label: 0,
            gc.review_label: 0,
        }
        errors = []

        for classification_result in classification_results:
            email_id = classification_result.email_id
            classification_category = classification_result.classification
            confidence = classification_result.confidence

            if not email_id:
                errors.append(f"Classification missing email_id: {classification_result.model_dump()}")
                continue

            message = email_map.get(email_id)
            if not message:
                errors.append(f"Message not found for email_id: {email_id}")
                continue

            try:
                decision = select_label_decision(
                    classification_category,
                    confidence,
                    gmail_config=gc,
                    confidence_threshold=self._confidence_threshold,
                )
                apply_label_to_message(message, decision.label, remove_inbox=decision.remove_inbox)
                apply_label_to_message(message, gc.processed_label, remove_inbox=False)
                label_counts[decision.label] = label_counts.get(decision.label, 0) + 1
                action = decision.action
                status = decision.status
            except ValueError as e:
                # Unknown category enum value
                errors.append(str(e))
                action = "Unknown classification - no action taken"
                status = "error"
            except Exception as e:
                error_msg = f"Error processing email_id {email_id}: {str(e)}"
                errors.append(error_msg)
                action = f"Error: {str(e)}"
                status = "error"

            processing_results.append(
                ProcessingResult(
                    email_id=email_id,
                    sender=classification_result.sender,
                    subject=classification_result.subject,
                    classification=classification_category,
                    action=action,
                    status=status,
                )
            )
            db_entries.append(
                {
                    "email_id": email_id,
                    "sender": classification_result.sender,
                    "subject": classification_result.subject,
                    "classification": classification_category.value
                    if hasattr(classification_category, "value")
                    else str(classification_category),
                    "reasoning": classification_result.reasoning,
                    "confidence": classification_result.confidence,
                    "refinement_count": classification_result.refinement_count,
                    "action": action,
                    "status": status,
                }
            )

        summary_output = ProcessingSummaryOutput(
            total_processed=len(processing_results),
            label_counts=label_counts,
            errors_count=len(errors),
            errors=errors if errors else None,
        )

        if self._persist_run and db_entries:
            try:
                run_id: str = ctx.session.state.get("run_id", "unknown")
                started_at: str = ctx.session.state.get("run_started_at", datetime.now(UTC).isoformat())
                finished_at: str = datetime.now(UTC).isoformat()
                await self._persist_run(
                    run_id=run_id,
                    started_at=started_at,
                    finished_at=finished_at,
                    db_entries=db_entries,
                    emails_collected=len(email_map),
                    emails_classified=len(classification_results),
                    emails_labelled=summary_output.total_processed,
                    errors_count=summary_output.errors_count,
                    status="success" if summary_output.errors_count == 0 else "partial",
                )
            except Exception:
                _logger.exception(
                    "persist_run_failed",
                    extra={"run_id": ctx.session.state.get("run_id", "unknown")},
                )

        ctx.agent_states[self.name] = {
            "summary_output": summary_output,
        }

        event = Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(parts=[types.Part(text=summary_output.model_dump_json(indent=2))]),
        )

        yield event


def create_email_labeler_agent(
    config: EmailLabelerConfig | None = None,
    name: str = "EmailLabelerAgent",
    description: str | None = None,
    persist_run: PersistRunFn | None = None,
    classifier_config: EmailClassifierConfig | None = None,
    confidence_threshold: float | None = None,
) -> EmailLabelerAgent:
    """Factory function for EmailLabelerAgent.

    ``confidence_threshold`` wins over ``classifier_config.confidence_threshold``
    if both are supplied. If neither is given, the low-confidence branch is
    disabled and every email is routed by category.
    """
    threshold = (
        confidence_threshold
        if confidence_threshold is not None
        else (classifier_config.confidence_threshold if classifier_config else None)
    )
    return EmailLabelerAgent(
        config=config or EmailLabelerConfig(),
        name=name,
        description=description,
        persist_run=persist_run,
        confidence_threshold=threshold,
    )
