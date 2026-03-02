"""
EmailLabeler - A Custom Agent for labeling emails based on classifications.

This agent retrieves classifications from EmailClassifierAgent's agent_states and
applies appropriate Gmail labels to each email based on the classification category.
All emails remain unread after processing.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.genai import types
from simplegmail.message import Message

from ..config import EmailLabelerConfig, GmailConfig
from ..database import PersistRunFn
from ..schemas.schemas import (
    ClassificationCollectionOutput,
    EmailCategory,
    ProcessingResult,
    ProcessingSummaryOutput,
)
from ..tools.gmail_client import apply_label_to_message


class EmailLabelerAgent(BaseAgent):
    """
    A Custom Agent that labels emails based on classifications.

    This agent retrieves classifications from EmailClassifierAgent's agent_states and
    applies Gmail labels to emails based on their classification:
    - NOISE -> "Noise" label (removes from inbox)
    - PROMOTIONAL -> "Promotions" label (removes from inbox)
    - INFORMATIONAL -> "Newsletters" label (removes from inbox)
    - URGENT -> "Urgent" label (stays in inbox)
    - PERSONAL -> "Personal" label (stays in inbox)

    All emails remain unread after processing.
    """

    def __init__(
        self,
        config: EmailLabelerConfig,
        name: str = "EmailLabelerAgent",
        description: str | None = None,
        persist_run: PersistRunFn | None = None,
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

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """
        Custom execution logic for the EmailLabeler agent.

        This method retrieves accumulated classifications from session state,
        maps them to Message objects from EmailCollectorAgent's agent_states, and
        applies appropriate labels based on the classification.

        Args:
            ctx: The invocation context containing session state and user input

        Yields:
            Events containing processing results
        """
        # Classifications are accumulated into session.state by the LoopAgent's
        # after_agent_callback (accumulate_classifications_callback) after each iteration.
        collection_output: ClassificationCollectionOutput | None = None
        final_classifications_data = ctx.session.state.get("final_classifications")
        if final_classifications_data:
            try:
                collection_output = ClassificationCollectionOutput.model_validate(final_classifications_data)
            except Exception:
                pass

        if not collection_output:
            # No classifications found
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
            # Empty classification list
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(parts=[types.Part(text="No classifications to process.")]),
            )
            yield event
            return

        # Retrieve emails from EmailCollectorAgent's agent_states
        collector_state = ctx.agent_states.get("EmailCollectorAgent")
        if not collector_state or "emails" not in collector_state:
            # No emails found
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(parts=[types.Part(text="No emails found. EmailCollectorAgent must run first.")]),
            )
            yield event
            return

        emails: list[Message] = collector_state["emails"]

        # Create a mapping from email_id to Message object
        email_map: dict[str, Message] = {email.id: email for email in emails}

        gc = self._gmail_config

        # Process each classification
        processing_results = []
        db_entries: list[dict] = []
        label_counts = {
            gc.noise_label: 0,
            gc.promotional_label: 0,
            gc.informational_label: 0,
            gc.urgent_label: 0,
            gc.personal_label: 0,
        }
        errors = []

        for classification_result in classification_results:
            email_id = classification_result.email_id
            classification_category = classification_result.classification

            if not email_id:
                errors.append(f"Classification missing email_id: {classification_result.model_dump()}")
                continue

            # Find the corresponding Message object
            message = email_map.get(email_id)
            if not message:
                errors.append(f"Message not found for email_id: {email_id}")
                continue

            # Apply label based on classification
            try:
                if classification_category == EmailCategory.NOISE:
                    apply_label_to_message(message, gc.noise_label, remove_inbox=True)
                    apply_label_to_message(message, gc.processed_label, remove_inbox=False)
                    label_counts[gc.noise_label] += 1
                    action = f"Applied '{gc.noise_label}' label and removed from inbox"
                    status = "success"
                elif classification_category == EmailCategory.PROMOTIONAL:
                    apply_label_to_message(message, gc.promotional_label, remove_inbox=True)
                    apply_label_to_message(message, gc.processed_label, remove_inbox=False)
                    label_counts[gc.promotional_label] += 1
                    action = f"Applied '{gc.promotional_label}' label and removed from inbox"
                    status = "success"
                elif classification_category == EmailCategory.INFORMATIONAL:
                    apply_label_to_message(message, gc.informational_label, remove_inbox=True)
                    apply_label_to_message(message, gc.processed_label, remove_inbox=False)
                    label_counts[gc.informational_label] += 1
                    action = f"Applied '{gc.informational_label}' label and removed from inbox"
                    status = "success"
                elif classification_category == EmailCategory.URGENT:
                    apply_label_to_message(message, gc.urgent_label, remove_inbox=False)
                    apply_label_to_message(message, gc.processed_label, remove_inbox=False)
                    label_counts[gc.urgent_label] += 1
                    action = f"Applied '{gc.urgent_label}' label and kept in inbox"
                    status = "success"
                elif classification_category == EmailCategory.PERSONAL:
                    apply_label_to_message(message, gc.personal_label, remove_inbox=False)
                    apply_label_to_message(message, gc.processed_label, remove_inbox=False)
                    label_counts[gc.personal_label] += 1
                    action = f"Applied '{gc.personal_label}' label and kept in inbox"
                    status = "success"
                else:
                    errors.append(
                        f"Unknown classification category: {classification_category} for email_id: {email_id}"
                    )
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

        # Create structured output summary
        summary_output = ProcessingSummaryOutput(
            total_processed=len(processing_results),
            label_counts=label_counts,
            errors_count=len(errors),
            errors=errors if errors else None,
        )

        # Persist to database asynchronously
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
            except Exception as e:
                print(f"[{self.name}] Failed to persist run to database: {e}")

        # Store processing results in agent_states
        ctx.agent_states[self.name] = {
            "summary_output": summary_output,
        }

        # Create event with structured output
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
) -> EmailLabelerAgent:
    """Factory function for EmailLabelerAgent."""
    return EmailLabelerAgent(
        config=config or EmailLabelerConfig(),
        name=name,
        description=description,
        persist_run=persist_run,
    )
