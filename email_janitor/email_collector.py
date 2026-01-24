"""
EmailCollector - A Custom Agent for fetching unread emails.

This agent is designed to fetch unread emails using email client tools.
Currently uses Gmail client, but can be extended to support other email providers.

This implementation follows Google ADK Custom Agent pattern:
https://google.github.io/adk-docs/agents/custom-agents/#part-1-simplified-custom-agent-initialization

This is a deterministic agent that always fetches unread emails when called,
without using an LLM for decision-making.
"""

from typing import AsyncGenerator
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.genai import types
from .gmail_client import get_unread_emails


class EmailCollector(BaseAgent):
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
        name: str = "EmailCollector",
        description: str | None = None,
    ):
        """
        Initialize the EmailCollector agent.
        
        Args:
            name: The name of the agent (default: "EmailCollector")
            description: Optional description of the agent
        """
        default_description = "An agent specialized in fetching and collecting unread emails from your inbox."
        super().__init__(
            name=name,
            description=description or default_description,
        )
    
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """
        Custom execution logic for the EmailCollector agent.
        
        This method deterministically fetches unread emails by directly calling
        the email client function and formats the results as an event.
        
        Args:
            ctx: The invocation context containing session state and user input
            
        Yields:
            Event containing the fetched unread emails
        """
        # Directly fetch unread emails (deterministic, no LLM)
        emails = get_unread_emails()
        
        # Format the email results as text
        if not emails:
            email_text = "No unread emails found."
        else:
            email_lines = [f"Found {len(emails)} unread email(s):\n"]
            for i, email in enumerate(emails, 1):
                email_lines.append(f"{i}. From: {email.sender}")
                email_lines.append(f"   Subject: {email.subject}")
                email_lines.append(f"   Date: {email.date}")
                if email.snippet:
                    email_lines.append(f"   Snippet: {email.snippet[:100]}...")
                email_lines.append("")
            email_text = "\n".join(email_lines)
        
        # Create an event with the email results
        event = Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(
                parts=[types.Part(text=email_text)]
            ),
        )
        
        yield event
    
    def fetch_emails(self):
        """
        Direct method to fetch unread emails using the email client tools.
        
        This is a convenience method that bypasses the agent orchestration
        for direct programmatic access to email fetching.
        
        Returns:
            A list of unread email messages.
        """
        return get_unread_emails()


# Create a default instance
email_collector = EmailCollector()
