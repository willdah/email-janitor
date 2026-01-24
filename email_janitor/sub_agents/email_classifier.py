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
        
        # Create an LLM sub-agent for classification
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

        Format: Respond ONLY with valid JSON.

        Example output:
        {
            "category": "CATEGORY_NAME",
            "reasoning": "A 1-sentence explanation citing the specific keywords found."
        }
"""
        )
    
    # TODO: Use Pydantic models for outputs.
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
        for i, email in enumerate[Message](emails, 1):
            # Prepare email content for classification
            # Include Subject and Body as requested by the instruction
            email_text = (
                "--- BEGIN EMAIL DATA ---\n"
                f"SENDER: {email.sender}\n"
                f"SUBJECT: {email.subject}\n"
            )
            
            # Include body if available (prefer plain text, fallback to snippet)
            if email.plain:
                # Truncate body if too long (keep first 2000 chars for classification)
                body = email.plain[:2000] + "..." if len(email.plain) > 2000 else email.plain
                email_text += f"BODY: {body}\n"
            elif email.snippet:
                email_text += f"SNIPPET: {email.snippet}\n"
            email_text += "--- END EMAIL DATA ---"
            
            # Create a context for the LLM sub-agent with the email as user content
            # Use model_copy to create a new context with updated user_content
            classification_ctx = ctx.model_copy(update={
                'user_content': types.Content(
                    parts=[types.Part(text=f"Classify this email:\n\n{email_text}")]
                ),
            })
            
            # Get classification from LLM sub-agent
            classification_result = None
            reasoning = None
            async for event in self._classifier_llm.run_async(classification_ctx):
                # Extract the classification from the final response
                if event.is_final_response() and event.content:
                    parts = event.content.parts if event.content.parts else []
                    if parts and parts[0].text:
                        response_text = parts[0].text.strip()
                        
                        # Try to parse JSON response
                        try:
                            # Extract JSON from response (might be wrapped in markdown code blocks)
                            json_text = response_text
                            if "```json" in json_text:
                                json_text = json_text.split("```json")[1].split("```")[0].strip()
                            elif "```" in json_text:
                                json_text = json_text.split("```")[1].split("```")[0].strip()
                            
                            classification_data = json.loads(json_text)
                            classification_result = classification_data.get("category", "").upper()
                            reasoning = classification_data.get("reasoning", "")
                        except (json.JSONDecodeError, KeyError, AttributeError):
                            # Fallback: try to extract category from plain text
                            response_upper = response_text.upper()
                            if "ACTIONABLE" in response_upper:
                                classification_result = "ACTIONABLE"
                            elif "INFORMATIONAL" in response_upper:
                                classification_result = "INFORMATIONAL"
                            elif "PROMOTIONAL" in response_upper:
                                classification_result = "PROMOTIONAL"
                            elif "NOISE" in response_upper:
                                classification_result = "NOISE"
                            else:
                                # Default fallback
                                classification_result = "NOISE"
                                reasoning = "Unable to parse classification response"
            
            # Normalize category to one of the expected values
            valid_categories = {"ACTIONABLE", "INFORMATIONAL", "PROMOTIONAL", "NOISE"}
            if classification_result not in valid_categories:
                classification_result = "NOISE"
                if not reasoning:
                    reasoning = f"Invalid category '{classification_result}', defaulting to NOISE"
            
            # Store classification result
            classifications.append({
                "email_id": email.id,
                "sender": email.sender,
                "subject": email.subject,
                "classification": classification_result or "NOISE",
                "reasoning": reasoning or "No reasoning provided",
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