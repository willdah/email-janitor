"""
EmailClassifier - A Custom Agent for classifying emails.

This agent retrieves emails from EmailCollector's agent_states and classifies
each email into categories: ACTIONABLE, INFORMATIONAL, PROMOTIONAL, or NOISE.
"""

import json
import uuid
from typing import AsyncGenerator
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import Agent
from google.adk.events.event import Event
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions.session import Session
from google.genai import types
from simplegmail.message import Message
from ..models.schemas import (
    EmailCollectionOutput,
    EmailClassificationInput,
    EmailClassificationOutput,
    ClassificationResult,
    ClassificationCollectionOutput,
    EmailCategory,
)


class EmailClassifier(BaseAgent):
    """
    A Custom Agent that classifies emails into categories.
    
    This agent retrieves emails from EmailCollector's agent_states and uses
    an LLM sub-agent to classify each email into one of four categories:
    ACTIONABLE, INFORMATIONAL, PROMOTIONAL, or NOISE.
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
        default_description = "An agent that classifies emails into categories: ACTIONABLE, INFORMATIONAL, PROMOTIONAL, or NOISE."
        super().__init__(
            name=name,
            description=description or default_description,
        ) 
    
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """
        Custom execution logic for the EmailClassifier agent.
        
        This method retrieves emails from EmailCollector's agent_states,
        classifies a single email (at current_email_index) using the LLM sub-agent,
        and stores the result. This is designed to run in a loop, processing one email per iteration.
        
        Args:
            ctx: The invocation context containing session state and user input
            
        Yields:
            Events containing classification result for a single email
        """
        # Retrieve emails from EmailCollector's agent_states
        collector_state = ctx.agent_states.get("EmailCollector")
        if not collector_state:
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
        
        email_data_list = collection_output.emails
        if not email_data_list:
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
        
        # Get current email index from session state (initialized by loop coordinator)
        current_index = ctx.session.state.get("current_email_index", 0)
        total_emails = ctx.session.state.get("total_emails", len(email_data_list))
        
        # Check if all emails have been processed
        if current_index >= len(email_data_list) or current_index >= total_emails:
            # All emails processed - exit gracefully
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(
                    parts=[types.Part(text=f"All emails processed ({current_index}/{total_emails}). Exiting loop.")]
                ),
            )
            yield event
            return
        
        # Get the email at the current index
        email_data = email_data_list[current_index]
        
        # Get the Message object for this specific email (for accessing full body)
        emails: list[Message] = collector_state.get("emails", [])
        message = None
        # Find the Message object with matching ID
        for email in emails:
            if email.id == email_data.id:
                message = email
                break
        
        # Prepare structured input for LLM sub-agent
        # Try to get full body from Message object if available
        body = None
        if message and hasattr(message, 'plain') and message.plain:
            # Truncate body if too long (keep first 2000 chars for classification)
            body = message.plain[:2000] + "..." if len(message.plain) > 2000 else message.plain
        elif email_data.snippet:
            # Fall back to snippet if full body not available
            body = email_data.snippet
        
        classification_input = EmailClassificationInput(
            sender=email_data.sender,
            subject=email_data.subject,
            body=body,
            snippet=email_data.snippet,
        )
        ctx.session.state["classification_input"] = classification_input

        classifier_llm = Agent(
            model=LiteLlm(model="ollama_chat/llama3.1:8b"),
            name="EmailClassifier",
            description="An agent that classifies emails into categories: ACTIONABLE, INFORMATIONAL, PROMOTIONAL, or NOISE.",
            instruction="""
Role: You are a strict Email Triage Agent. 

Task: Classify the email inside the classification_input.

Categories:
1. ACTIONABLE: Security alerts, invoices, bills, or direct messages from individuals.
2. INFORMATIONAL: Newsletters, shipping updates, or trusted industry news.
3. PROMOTIONAL: Sales, coupons, or marketing offers.
4. NOISE: Spam or irrelevant content.

---
Classification Input:
{classification_input}
""",
            input_schema=EmailClassificationInput,
            output_schema=EmailClassificationOutput,
            output_key="email_classification",
            generate_content_config=types.GenerateContentConfig(
                temperature=0.4,
                top_k=20
            ),
        )
        
        # Get classification from LLM sub-agent
        classification_output: EmailClassificationOutput | None = None
        async for event in classifier_llm.run_async(ctx):
            # Extract the classification from the final response
            if event.is_final_response() and event.content:
                parts = event.content.parts if event.content.parts else []
                if parts and parts[0].text:
                    response_text = parts[0].text.strip()
                    
                    # Parse structured output
                    try:
                        # The output_schema ensures JSON format, but might be wrapped
                        json_text = response_text
                        if "```json" in json_text:
                            json_text = json_text.split("```json")[1].split("```")[0].strip()
                        elif "```" in json_text:
                            json_text = json_text.split("```")[1].split("```")[0].strip()
                        
                        # Parse and validate using Pydantic model
                        classification_output = EmailClassificationOutput.model_validate_json(json_text)
                    except (json.JSONDecodeError, ValueError) as e:
                        # Fallback: try to extract category from plain text
                        response_upper = response_text.upper()
                        category_str = "NOISE"
                        if "ACTIONABLE" in response_upper:
                            category_str = "ACTIONABLE"
                        elif "INFORMATIONAL" in response_upper:
                            category_str = "INFORMATIONAL"
                        elif "PROMOTIONAL" in response_upper:
                            category_str = "PROMOTIONAL"
                        
                        # Create fallback output
                        classification_output = EmailClassificationOutput(
                            category=EmailCategory(category_str),
                            reasoning=f"Unable to parse structured response: {str(e)}"
                        )
        
        # Ensure we have a classification result
        if not classification_output:
            classification_output = EmailClassificationOutput(
                category=EmailCategory.NOISE,
                reasoning="No classification response received"
            )
        
        # Create full classification result with email metadata
        classification_result = ClassificationResult(
            email_id=email_data.id,
            sender=email_data.sender,
            subject=email_data.subject,
            classification=classification_output.category,
            reasoning=classification_output.reasoning,
        )
        
        # Store current classification as a collection output (single item)
        # EmailProcessor expects a ClassificationCollectionOutput
        collection_output = ClassificationCollectionOutput(
            count=1,
            classifications=[classification_result],
        )
        ctx.agent_states[self.name] = {
            "current_classification": classification_result,
            "collection_output": collection_output,
        }
        
        # Increment the index for the next iteration
        ctx.session.state["current_email_index"] = current_index + 1
        
        # Create event with structured output
        event = Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(
                parts=[types.Part(text=classification_result.model_dump_json(indent=2))]
            ),
        )
        
        yield event


# Create a default instance
email_classifier = EmailClassifier()