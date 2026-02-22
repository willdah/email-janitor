"""
EmailCollector - A Custom Agent for fetching unread emails.

This agent is designed to fetch unread emails using email client tools.
Currently uses Gmail client, but can be extended to support other email providers.

This implementation follows Google ADK Custom Agent pattern:
https://google.github.io/adk-docs/agents/custom-agents/#part-1-simplified-custom-agent-initialization

This is a deterministic agent that always fetches unread emails when called,
without using an LLM for decision-making.
"""

from collections.abc import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.genai import types
from simplegmail.message import Message

from ..config import EmailCollectorConfig
from ..schemas.schemas import EmailCollectionOutput, EmailData
from ..tools.gmail_client import get_unread_emails


class EmailCollectorAgent(BaseAgent):
    """
    A deterministic Custom Agent that specializes in fetching unread emails.

    This agent directly calls email client functions to retrieve unread messages.
    It does not use an LLM - it deterministically fetches emails every time it's called.
    The underlying email client can be swapped in the future without changing the agent interface.

    This custom agent inherits from BaseAgent and implements _run_async_impl
    to define custom orchestration logic for email fetching.
    """

    def __init__(
        self,
        config: EmailCollectorConfig,
        name: str = "EmailCollectorAgent",
        description: str | None = None,
    ):
        default_description = (
            "An agent specialized in fetching and collecting unread emails from your inbox."
        )
        super().__init__(
            name=name,
            description=description or default_description,
        )
        self._config = config

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """
        Custom execution logic for the EmailCollector agent.

        This method deterministically fetches unread emails by directly calling
        the email client function. The Message objects are preserved in agent_states
        for programmatic access, while a serialized dictionary is provided in the event.

        Args:
            ctx: The invocation context containing session state and user input

        Yields:
            Event containing a dictionary summary of the fetched unread emails.

        Note:
            The Message objects are stored in ctx.agent_states[self.name]["emails"].
            This agent_states dictionary is shared across all agents in the same invocation,
            so other agents can access the emails via:
            `ctx.agent_states["EmailCollectorAgent"]["emails"]`
        """
        # Directly fetch unread emails (deterministic, no LLM)
        emails: list[Message] = get_unread_emails()

        # Convert emails to Pydantic EmailData models
        email_data_list = []
        for email in emails:
            labels = []
            # Handle label_ids - they might be strings or Label objects
            for label_id in email.label_ids:
                if hasattr(label_id, "name"):
                    labels.append(label_id.name)
                else:
                    labels.append(str(label_id))

            email_data_list.append(
                EmailData(
                    id=email.id,
                    sender=email.sender,
                    recipient=email.recipient,
                    subject=email.subject,
                    date=email.date,
                    snippet=email.snippet,
                    thread_id=email.thread_id,
                    labels=labels,
                )
            )

        # Create structured output using Pydantic model
        collection_output = EmailCollectionOutput(
            count=len(emails),
            emails=email_data_list,
        )

        # Store the Message objects in agent_states for accessing full email body
        # Also store the structured output for type-safe access
        ctx.agent_states[self.name] = {
            "emails": emails,  # Preserve the original Message objects for accessing full body
            "collection_output": collection_output,  # Structured Pydantic model
        }

        # Also store collection_output in session.state for callback access
        # (callbacks only have access to session.state, not agent_states)
        ctx.session.state["collector_output"] = collection_output.model_dump()

        # Create an event with the structured output as JSON
        # The Message objects are preserved in ctx.agent_states[self.name]["emails"]
        # for programmatic access by other agents or code
        event = Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(
                parts=[types.Part(text=collection_output.model_dump_json(indent=2))]
            ),
        )

        yield event

def create_email_collector_agent(
    config: EmailCollectorConfig | None = None,
    name: str = "EmailCollectorAgent",
    description: str | None = None,
) -> EmailCollectorAgent:
    """Factory function for EmailCollectorAgent."""
    return EmailCollectorAgent(
        config=config or EmailCollectorConfig(),
        name=name,
        description=description,
    )
