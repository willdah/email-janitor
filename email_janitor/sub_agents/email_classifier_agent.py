"""
ClassificationCoordinator - Orchestrates email classification.

This coordinator classifies emails using an LLM classifier.
"""

import re
import uuid
from typing import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import Agent
from google.adk.events.event import Event
from google.adk.models.lite_llm import LiteLlm
from google.genai import types
from simplegmail.message import Message

from ..config import ClassificationConfig
from ..models.schemas import (
    ClassificationCollectionOutput,
    ClassificationResult,
    EmailCategory,
    EmailClassificationInput,
    EmailClassificationOutput,
    EmailCollectionOutput,
    EmailData,
)
from ..instructions.email_classifier_agent import build_instruction


class EmailClassifierAgent(BaseAgent):
    """
    Coordinates email classification.
    """

    def __init__(
        self,
        name: str = "EmailClassifierAgent",
        description: str | None = None,
        classifier_model: LiteLlm | None = None,
        config: ClassificationConfig | None = None,
    ):
        super().__init__(
            name=name,
            description=description or "Coordinates email classification.",
        )
        self._classifier_model = classifier_model or LiteLlm(
            model="ollama_chat/llama3.1:8b"
        )
        self._config = config or ClassificationConfig()

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
            generate_content_config=types.GenerateContentConfig(
                temperature=0.4, top_k=10
            ),
        )

        classification_output = None
        async for event in classifier_llm.run_async(ctx):
            if event.is_final_response() and event.content:
                raw_text = event.content.parts[0].text or ""
                try:
                    clean_json = self._extract_clean_json(raw_text)
                    classification_output = (
                        EmailClassificationOutput.model_validate_json(clean_json)
                    )
                except Exception as e:
                    classification_output = EmailClassificationOutput(
                        category=EmailCategory.NOISE,
                        reasoning=f"Parsing error: {str(e)}",
                        confidence=0.3,
                    )

        if not classification_output:
            classification_output = EmailClassificationOutput(
                category=EmailCategory.NOISE, reasoning="No response.", confidence=0.3
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

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """Main execution logic for the coordinator."""
        # 1. State Retrieval
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

        if current_index >= len(collection_output.emails):
            # Ensure final classifications are stored before escalating
            existing_state = ctx.agent_states.get(self.name, {})
            existing_collection = existing_state.get("collection_output")

            if existing_collection:
                ctx.session.state["final_classifications"] = (
                    existing_collection.model_dump()
                )

            # Signal loop completion
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(
                    parts=[types.Part(text="All emails classified.")]
                ),
            )
            event.actions.escalate = True
            yield event
            return

        email_data = collection_output.emails[current_index]

        # Get full email body if available
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

        # Process email through classification pipeline
        result = await self._process_email(ctx, email_data, email_body)

        # Update State & Yield - Accumulate all classifications
        existing_state = ctx.agent_states.get(self.name, {})
        existing_collection = existing_state.get("collection_output")

        if not existing_collection:
            final_classifications_data = ctx.session.state.get("final_classifications")
            if final_classifications_data:
                try:
                    existing_collection = ClassificationCollectionOutput.model_validate(
                        final_classifications_data
                    )
                except Exception:
                    existing_collection = None

        if existing_collection:
            all_classifications = existing_collection.classifications + [result]
        else:
            all_classifications = [result]

        collection_output = ClassificationCollectionOutput(
            count=len(all_classifications), classifications=all_classifications
        )

        ctx.agent_states[self.name] = {
            "current_classification": result,
            "collection_output": collection_output,
        }

        ctx.session.state["final_classifications"] = collection_output.model_dump()
        ctx.session.state["current_email_index"] = current_index + 1

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(
                parts=[types.Part(text=result.model_dump_json(indent=2))]
            ),
        )


# Create a default instance
email_classifier_agent = EmailClassifierAgent()
