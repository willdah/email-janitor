"""
EmailClassifier - A Custom Agent for classifying emails.

This agent retrieves emails from EmailCollector's agent_states and classifies
each email into categories: spam, important, or not important.
"""

import json
from typing import AsyncGenerator
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import Agent
from google.adk.events.event import Event
from google.adk.models.lite_llm import LiteLlm
from google.genai import types
from simplegmail.message import Message


class EmailClassifier(BaseAgent):
    """
    A Custom Agent that classifies emails into categories.
    
    This agent retrieves emails from EmailCollector's agent_states and uses
    an LLM sub-agent to classify each email into one of three categories:
    spam, important, or not important.
    """
    
    def __init__(
        self,
        name: str = "EmailClassifier",
        description: str | None = None,
        model: LiteLlm | None = None,
    ):
        """
        Initialize the EmailClassifier agent.
        
        Args:
            name: The name of the agent (default: "EmailClassifier")
            description: Optional description of the agent
            model: Optional LLM model to use (default: LiteLlm with llama3.1:8b)
        """
        default_description = "An agent that classifies emails into categories: spam, important, or not important."
        super().__init__(
            name=name,
            description=description or default_description,
        )
        
        # Create an LLM sub-agent for classification
        self._classifier_llm = Agent(
            model=model or LiteLlm(model="ollama_chat/llama3.1:8b"),
            name="EmailClassificationLLM",
            description="Classifies a single email into a category.",
            instruction=(
                "You are an email classifier. You are given an email and you need to classify it "
                "into one of these categories: 'spam', 'important', or 'not important'. "
                "Respond with only the category name (one word)."
            ),
        )
    
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """
        Custom execution logic for the EmailClassifier agent.
        
        This method retrieves emails from EmailCollector's agent_states,
        classifies each email using the LLM sub-agent, and stores the results.
        
        Args:
            ctx: The invocation context containing session state and user input
            
        Yields:
            Events containing classification results
        """
        # Retrieve emails from EmailCollector's agent_states
        collector_state = ctx.agent_states.get("EmailCollector")
        if not collector_state or "emails" not in collector_state:
            # No emails to classify
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(
                    parts=[types.Part(text="No emails found to classify. EmailCollector must run first.")]
                ),
            )
            yield event
            return
        
        emails: list[Message] = collector_state["emails"]
        
        if not emails:
            # Empty email list
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(
                    parts=[types.Part(text="No emails to classify.")]
                ),
            )
            yield event
            return
        
        # Classify each email
        classifications = []
        for i, email in enumerate(emails, 1):
            # Prepare email content for classification
            email_text = f"From: {email.sender}\nSubject: {email.subject}\n"
            if email.snippet:
                email_text += f"Snippet: {email.snippet}\n"
            
            # Create a context for the LLM sub-agent with the email as user content
            # Use model_copy to create a new context with updated user_content
            classification_ctx = ctx.model_copy(update={
                'user_content': types.Content(
                    parts=[types.Part(text=f"Classify this email:\n\n{email_text}")]
                ),
            })
            
            # Get classification from LLM sub-agent
            classification_result = None
            async for event in self._classifier_llm.run_async(classification_ctx):
                # Extract the classification from the final response
                if event.is_final_response() and event.content:
                    parts = event.content.parts if event.content.parts else []
                    if parts and parts[0].text:
                        classification_result = parts[0].text.strip().lower()
                        # Normalize to one of the expected categories
                        if "spam" in classification_result:
                            classification_result = "spam"
                        elif "important" in classification_result:
                            classification_result = "important"
                        else:
                            classification_result = "not important"
            
            # Store classification result
            classifications.append({
                "email_id": email.id,
                "sender": email.sender,
                "subject": email.subject,
                "classification": classification_result or "not important",
            })
        
        # Store classifications in agent_states
        ctx.agent_states[self.name] = {
            "classifications": classifications,
            "count": len(classifications),
        }
        
        # Create summary event
        summary = {
            "count": len(classifications),
            "classifications": classifications,
        }
        
        event = Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(
                parts=[types.Part(text=json.dumps(summary, indent=2))]
            ),
        )
        
        yield event


# Create a default instance
email_classifier = EmailClassifier()