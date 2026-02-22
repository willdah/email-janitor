"""
EmailClassifier - Classifies emails using an LLM.

This agent is a thin orchestrator: it handles loop control (escalation when all
emails are classified) and delegates the actual LLM classification to a pre-built
LlmAgent sub-agent with a callable instruction.
"""

import re
from collections.abc import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import Agent
from google.adk.events.event import Event
from google.adk.models.lite_llm import LiteLlm
from google.genai import types
from simplegmail.message import Message

from ..callbacks.callbacks import cleanup_llm_json_callback
from ..config import EmailClassifierConfig
from ..instructions.email_classifier_agent import build_instruction
from ..schemas.schemas import (
    ClassificationCollectionOutput,
    ClassificationResult,
    EmailCategory,
    EmailClassificationInput,
    EmailClassificationOutput,
    EmailCollectionOutput,
)


class EmailClassifierAgent(BaseAgent):
    """
    Thin orchestrator that handles loop control and delegates to an LLM Agent.

    Responsibilities:
    - Signal loop completion (escalate) when all emails are classified
    - Prepare the current email's body in session state for the LLM Agent's instruction
    - Delegate classification to a pre-built LlmAgent sub-agent
    - Store the result in session state for the LoopAgent's after_agent_callback

    The LLM Agent (self._classifier) is built once at construction time with a
    callable instruction that reads the current email from session state on each call.
    """

    def __init__(
        self,
        config: EmailClassifierConfig,
        name: str = "EmailClassifierAgent",
        description: str | None = None,
    ):
        super().__init__(
            name=name,
            description=description or "Classifies emails using an LLM.",
        )
        self._config = config
        self._classifier = Agent(
            model=LiteLlm(model=config.model),
            name=f"{name}_LLM",
            instruction=self._build_instruction,
            output_schema=EmailClassificationOutput,
            generate_content_config=types.GenerateContentConfig(temperature=0.4, top_k=10),
            after_model_callback=cleanup_llm_json_callback,
        )

    def _build_instruction(self, ctx) -> str:
        """
        Callable instruction that reads the current email from session state.

        Called by the LLM Agent before each LLM invocation, so the prompt always
        reflects the email at the current loop index.
        """
        current_index = ctx.state.get("current_email_index", 0)
        collector_output_data = ctx.state.get("collector_output")

        if not collector_output_data:
            return "No emails available to classify."

        collection_output = EmailCollectionOutput.model_validate(collector_output_data)
        if current_index >= len(collection_output.emails):
            return "All emails have been classified."

        email_data = collection_output.emails[current_index]
        email_body = ctx.state.get("current_email_body")

        return build_instruction(
            EmailClassificationInput(
                sender=email_data.sender,
                subject=email_data.subject,
                snippet=email_data.snippet[:500] if email_data.snippet else None,
                body=email_body[:2000] if email_body else None,
            )
        )

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """
        Loop control: escalate when done, otherwise delegate to the LLM classifier.
        """
        collector_state = ctx.agent_states.get("EmailCollectorAgent")
        if not collector_state or "collection_output" not in collector_state:
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(parts=[types.Part(text="Error: EmailCollectorAgent state missing.")]),
            )
            return

        collection_output: EmailCollectionOutput = collector_state["collection_output"]
        current_index = ctx.session.state.get("current_email_index", 0)

        # Escalate to signal the LoopAgent that all emails have been classified
        if current_index >= len(collection_output.emails):
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

        # Stash the full email body in session state so _build_instruction can read it.
        # agent_states is not accessible from the LLM Agent's instruction callable.
        emails: list[Message] | None = collector_state.get("emails")
        email_body = None
        if emails:
            for msg in emails:
                if msg.id == email_data.id:
                    try:
                        email_body = msg.plain or msg.html or email_data.snippet
                    except Exception:
                        email_body = email_data.snippet
                    break
        ctx.session.state["current_email_body"] = email_body

        # Delegate to the pre-built LLM classifier, forwarding all events upstream
        classification_result = None
        async for event in self._classifier.run_async(ctx):
            yield event
            if event.is_final_response() and event.content and event.content.parts:
                raw_text = event.content.parts[0].text or ""
                try:
                    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                    output = EmailClassificationOutput.model_validate_json(match.group(0) if match else raw_text)
                except Exception:
                    output = EmailClassificationOutput(
                        category=EmailCategory.NOISE,
                        reasoning="Parsing error",
                        confidence=1.0,
                    )
                classification_result = ClassificationResult(
                    email_id=email_data.id,
                    sender=email_data.sender,
                    subject=email_data.subject,
                    classification=output.category,
                    reasoning=output.reasoning,
                    confidence=output.confidence,
                    refinement_count=0,
                )

        # Accumulate result into session state and advance the index.
        # This must happen inside _run_async_impl because LoopAgent callbacks only
        # fire once (before/after the entire loop), not once per iteration.
        if classification_result:
            existing_data = ctx.session.state.get("final_classifications")
            existing_classifications = []
            if existing_data:
                try:
                    existing = ClassificationCollectionOutput.model_validate(existing_data)
                    existing_classifications = [
                        c.model_dump() if hasattr(c, "model_dump") else c for c in existing.classifications
                    ]
                except Exception:
                    pass
            all_classifications = existing_classifications + [classification_result.model_dump()]
            ctx.session.state["final_classifications"] = {
                "count": len(all_classifications),
                "classifications": all_classifications,
            }

        # Always advance the index so the loop terminates even on LLM failure
        ctx.session.state["current_email_index"] = current_index + 1


def create_email_classifier_agent(
    config: EmailClassifierConfig | None = None,
    name: str = "EmailClassifierAgent",
    description: str | None = None,
) -> EmailClassifierAgent:
    """Factory function for EmailClassifierAgent."""
    return EmailClassifierAgent(
        config=config or EmailClassifierConfig(),
        name=name,
        description=description,
    )
