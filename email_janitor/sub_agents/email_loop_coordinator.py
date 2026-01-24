"""
EmailLoopCoordinator - A Custom Agent that coordinates the email processing loop.

This agent initializes the state for the loop (current_email_index) and ensures
EmailCollector has run successfully before the loop begins.
"""

from typing import AsyncGenerator
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.genai import types
from ..models.schemas import EmailCollectionOutput


class EmailLoopCoordinator(BaseAgent):
    """
    A Custom Agent that coordinates the email processing loop.
    
    This agent initializes the current_email_index in session.state to 0,
    ensuring the loop starts from the first email. It also validates that
    EmailCollector has run successfully.
    """
    
    def __init__(
        self,
        name: str = "EmailLoopCoordinator",
        description: str | None = None,
    ):
        """
        Initialize the EmailLoopCoordinator agent.
        
        Args:
            name: The name of the agent (default: "EmailLoopCoordinator")
            description: Optional description of the agent
        """
        default_description = "An agent that initializes state for the email processing loop."
        super().__init__(
            name=name,
            description=description or default_description,
        )
    
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """
        Custom execution logic for the EmailLoopCoordinator agent.
        
        This method initializes current_email_index to 0 in session.state
        and validates that EmailCollector has collected emails.
        
        Args:
            ctx: The invocation context containing session state and user input
            
        Yields:
            Event confirming initialization
        """
        # Retrieve emails from EmailCollector's agent_states
        collector_state = ctx.agent_states.get("EmailCollector")
        if not collector_state:
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(
                    parts=[types.Part(text="No emails found. EmailCollector must run first.")]
                ),
            )
            yield event
            return
        
        # Get structured output from EmailCollector
        collection_output: EmailCollectionOutput | None = collector_state.get("collection_output")
        if not collection_output:
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(
                    parts=[types.Part(text="No email collection output found. EmailCollector must provide structured output.")]
                ),
            )
            yield event
            return
        
        email_count = len(collection_output.emails)
        
        if email_count == 0:
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(
                    parts=[types.Part(text="No emails to process. Skipping loop.")]
                ),
            )
            yield event
            return
        
        # Initialize current_email_index to 0 for the loop
        ctx.session.state["current_email_index"] = 0
        ctx.session.state["total_emails"] = email_count
        
        # Store email count in agent_states for reference
        ctx.agent_states[self.name] = {
            "email_count": email_count,
        }
        
        # Create event confirming initialization
        event = Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(
                parts=[types.Part(text=f"Initialized email processing loop. {email_count} emails to process.")]
            ),
        )
        
        yield event


# Create a default instance
email_loop_coordinator = EmailLoopCoordinator()
