"""
EmailClassifier - A Custom Agent for classifying emails.

This agent retrieves emails from EmailCollector's agent_states and classifies
each email into categories: ACTIONABLE, INFORMATIONAL, PROMOTIONAL, or NOISE.
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
        
        # Create an LLM sub-agent for classification with structured input/output schemas
        # TODO: Move instruction to a separate file and load it from there.
        self._classifier_llm = Agent(
            model=model or LiteLlm(model="ollama_chat/llama3.1:8b"),
            name="EmailClassificationLLM",
            description="Classifies a single email into a category.",
            instruction="""
Role: You are a Context-Aware Email Triage Agent. You categorize emails the user provides.

    Task: Classify the provided email into one of four categories.

    1. ACTIONABLE (Primary Concern)

        Financials/Home: Anything from "Town of Weymouth," "National Grid," "Xfinity," "Rocket Mortgage," or contractors (e.g., "BDL Heating").

        Security: "New login," "Verify device," or "Password reset" alerts.

        Personal: Direct messages from "Lindsay Buckle" or specific humans (e.g., "Andy" or "Richard").

    2. INFORMATIONAL (Secondary Concern)

        Updates: "Shipment delivered," "Order confirmed," or "Industry updates."

        Reading: Newsletters you actually subscribed to (e.g., "Tandem Coffee," "Apple Cash updates").

    3. PROMOTIONAL (Marketing)

        Sales: Subjects containing "Sale," "Off," "Savings," or "Gift for you."

        Retailers: AAA Travel, Chewy, or fashion brands.

    4. NOISE (Filter Out)

        True Junk: Random spam or emails with absolutely zero recognizable content.

    Strict Instructions:

        Never claim "No Input": If a Subject exists, you must classify it. A subject line is enough data.

        Stay Grounded: Only use the names and themes present in the text.

        You must respond with a JSON object matching the output schema with "category" and "reasoning" fields.
        The category must be one of: ACTIONABLE, INFORMATIONAL, PROMOTIONAL, or NOISE.
        The reasoning must be a 1-sentence explanation citing the specific keywords found.
""",
            input_schema=EmailClassificationInput,
            output_schema=EmailClassificationOutput,
            output_key="email_classification",
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
        
        # Create a mapping from email_id to Message object for accessing full body
        emails: list[Message] = collector_state.get("emails", [])
        email_map: dict[str, Message] = {email.id: email for email in emails} if emails else {}
        
        # Classify each email
        classification_results = []
        for email_data in email_data_list:
            # Prepare structured input for LLM sub-agent
            # Try to get full body from Message object if available
            body = None
            message = email_map.get(email_data.id)
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
            
            # Create a context for the LLM sub-agent with structured JSON input
            # The input_schema requires JSON string conforming to EmailClassificationInput
            # The output_schema ensures the response conforms to EmailClassificationOutput
            # The output_key="email_classification" automatically stores the result in session.state["email_classification"]
            classification_ctx = ctx.model_copy(update={
                'user_content': types.Content(
                    parts=[types.Part(text=classification_input.model_dump_json())]
                ),
            })
            
            # Get classification from LLM sub-agent
            # Note: The result is also automatically stored in session.state["email_classification"] 
            # due to output_key being set, but we read from events here for immediate processing
            classification_output: EmailClassificationOutput | None = None
            async for event in self._classifier_llm.run_async(classification_ctx):
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
            classification_results.append(classification_result)
        
        # Create structured output collection
        collection_output = ClassificationCollectionOutput(
            count=len(classification_results),
            classifications=classification_results,
        )
        
        # Store classifications in agent_states
        ctx.agent_states[self.name] = {
            "collection_output": collection_output,
        }
        
        # Create event with structured output
        event = Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(
                parts=[types.Part(text=collection_output.model_dump_json(indent=2))]
            ),
        )
        
        yield event


# Create a default instance
email_classifier = EmailClassifier()