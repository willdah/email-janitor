"""
ClassificationCoordinator - Orchestrates email classification.

This coordinator classifies emails using an LLM classifier.
"""

import re
import uuid
from collections.abc import AsyncGenerator, Callable

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import Agent
from google.adk.events.event import Event
from google.adk.models.lite_llm import LiteLlm
from google.genai import types
from simplegmail.message import Message

from ..callbacks import cleanup_llm_json_callback
from ..config import ClassificationConfig
from ..instructions.email_classifier_agent import build_instruction
from ..models.schemas import (
    ClassificationResult,
    EmailCategory,
    EmailClassificationInput,
    EmailClassificationOutput,
    EmailCollectionOutput,
    EmailData,
)

# Type alias for callback functions
AfterAgentCallback = Callable[[CallbackContext], types.Content | None]


class EmailClassifierAgent(BaseAgent):
    """
    Coordinates email classification.

    This agent classifies a single email per invocation. When wrapped in a LoopAgent,
    it processes emails one at a time until all are classified.

    Callbacks:
        - after_agent_callback: Called after each classification. Use this to
          accumulate results or perform post-classification processing.
    """

    def __init__(
        self,
        name: str = "EmailClassifierAgent",
        description: str | None = None,
        classifier_model: LiteLlm | None = None,
        config: ClassificationConfig | None = None,
        after_agent_callback: AfterAgentCallback | None = None,
    ):
        super().__init__(
            name=name,
            description=description or "Coordinates email classification.",
        )
        self._classifier_model = classifier_model or LiteLlm(model="ollama_chat/llama3.1:8b")
        self._config = config or ClassificationConfig()
        self._after_agent_callback = after_agent_callback

    def _extract_clean_json(self, text: str) -> str:
        """Regex helper to handle local LLM markdown 'chatter'."""
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return match.group(0) if match else text.strip()

    async def _classify_email(
        self,
        ctx: InvocationContext,
        email_data: EmailData,
        email_body: str | None = None,
    ) -> EmailClassificationOutput:
        """
        Classify an email using the ClassifierAgent.

        Args:
            ctx: Invocation context
            email_data: Email data to classify
            email_body: Full email body if available

        Returns:
            EmailClassificationOutput with classification
        """
        classification_input = EmailClassificationInput(
            sender=email_data.sender,
            subject=email_data.subject,
            snippet=email_data.snippet[:500] if email_data.snippet else None,
            body=email_body[:2000] if email_body else None,  # Cap body length
        )

        unique_agent_id = f"Triage_{uuid.uuid4().hex[:8]}"

        classifier_llm = Agent(
            model=self._classifier_model,
            name=unique_agent_id,
            instruction=build_instruction(classification_input),
            output_schema=EmailClassificationOutput,
            generate_content_config=types.GenerateContentConfig(temperature=0.4, top_k=10),
            # Use callback to clean JSON from markdown code blocks
            after_model_callback=cleanup_llm_json_callback,
        )

        classification_output = None
        async for event in classifier_llm.run_async(ctx):
            if event.is_final_response() and event.content:
                # JSON is already cleaned by after_model_callback
                raw_text = event.content.parts[0].text or ""
                try:
                    # Fallback cleanup in case callback didn't catch everything
                    clean_json = self._extract_clean_json(raw_text)
                    classification_output = EmailClassificationOutput.model_validate_json(
                        clean_json
                    )
                except Exception as e:
                    classification_output = EmailClassificationOutput(
                        category=EmailCategory.NOISE,
                        reasoning=f"Parsing error: {str(e)}",
                        confidence=1.0,
                    )

        if not classification_output:
            classification_output = EmailClassificationOutput(
                category=EmailCategory.NOISE, reasoning="No response.", confidence=1.0
            )

        return classification_output

    async def _process_email(
        self, ctx: InvocationContext, email_data: EmailData, email_body: str | None
    ) -> ClassificationResult:
        """
        Process a single email through the classification pipeline.

        Returns:
            ClassificationResult with final classification
        """
        # Classify email
        classifier_output = await self._classify_email(ctx, email_data, email_body)

        return ClassificationResult(
            email_id=email_data.id,
            sender=email_data.sender,
            subject=email_data.subject,
            classification=classifier_output.category,
            reasoning=classifier_output.reasoning,
            confidence=classifier_output.confidence,
            refinement_count=0,
        )

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """
        Main execution logic for the classifier.

        This method:
        1. Retrieves the current email to classify based on current_email_index
        2. Classifies the email using the LLM
        3. Stores the result in session.state for the after_agent_callback to accumulate
        4. Signals loop completion when all emails are processed

        Note: State initialization (current_email_index) is handled by the
        before_agent_callback on the parent LoopAgent. Classification accumulation
        is handled by the after_agent_callback.
        """
        # Retrieve collection output from agent_states (for Message objects)
        # and session.state (for serialized data)
        collector_state = ctx.agent_states.get("EmailCollectorAgent")
        if not collector_state or "collection_output" not in collector_state:
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(
                    parts=[types.Part(text="Error: EmailCollectorAgent state missing.")]
                ),
            )
            return

        collection_output: EmailCollectionOutput = collector_state["collection_output"]
        current_index = ctx.session.state.get("current_email_index", 0)

        # Check if all emails have been processed
        if current_index >= len(collection_output.emails):
            # Signal loop completion
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(parts=[types.Part(text="All emails classified.")]),
            )
            event.actions.escalate = True
            yield event
            return

        email_data = collection_output.emails[current_index]

        # Get full email body if available (from Message objects in agent_states)
        email_body = None
        emails: list[Message] | None = collector_state.get("emails")
        if emails:
            for msg in emails:
                if msg.id == email_data.id:
                    try:
                        email_body = msg.plain or msg.html or email_data.snippet
                    except Exception:
                        email_body = email_data.snippet
                    break

        # Classify the email
        result = await self._process_email(ctx, email_data, email_body)

        # Store current classification in session.state for the after_agent_callback
        # The callback will handle accumulation and index increment
        ctx.session.state["current_classification"] = result.model_dump()

        # Also store in agent_states for immediate access by downstream code
        ctx.agent_states[self.name] = {
            "current_classification": result,
        }

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(parts=[types.Part(text=result.model_dump_json(indent=2))]),
        )

        # Invoke after_agent_callback for accumulation and state updates
        if self._after_agent_callback:
            # Create a callback context from the invocation context
            callback_ctx = CallbackContext(ctx)
            callback_result = self._after_agent_callback(callback_ctx)
            if callback_result:
                # If callback returns content, yield it as an additional event
                yield Event(
                    invocation_id=ctx.invocation_id,
                    author=self.name,
                    branch=ctx.branch,
                    content=callback_result,
                )


# Create a default instance
email_classifier_agent = EmailClassifierAgent()
