"""
EmailProcessor - A Custom Agent for processing emails based on classifications.

This agent retrieves classifications from EmailClassifier's agent_states and
applies appropriate Gmail labels to each email based on the classification category.
All emails remain unread after processing.
"""

import json
from typing import AsyncGenerator
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.genai import types
from simplegmail.message import Message
from ..tools.gmail_client import apply_label_to_message


class EmailProcessor(BaseAgent):
    """
    A Custom Agent that processes emails based on classifications.
    
    This agent retrieves classifications from EmailClassifier's agent_states and
    applies Gmail labels to emails based on their classification:
    - NOISE -> "Noise" label (removes from inbox)
    - PROMOTIONAL -> "Promotions" label (removes from inbox)
    - INFORMATIONAL -> "Newsletters" label (removes from inbox)
    - ACTIONABLE -> No action (leave in inbox)
    
    All emails remain unread after processing.
    """
    
    def __init__(
        self,
        name: str = "EmailProcessor",
        description: str | None = None,
    ):
        """
        Initialize the EmailProcessor agent.
        
        Args:
            name: The name of the agent (default: "EmailProcessor")
            description: Optional description of the agent
        """
        default_description = "An agent that processes emails based on classifications and applies appropriate Gmail labels."
        super().__init__(
            name=name,
            description=description or default_description,
        )
    
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """
        Custom execution logic for the EmailProcessor agent.
        
        This method retrieves classifications from EmailClassifier's agent_states,
        maps them to Message objects from EmailCollector's agent_states, and
        applies appropriate labels based on the classification.
        
        Args:
            ctx: The invocation context containing session state and user input
            
        Yields:
            Events containing processing results
        """
        # Retrieve classifications from EmailClassifier's agent_states
        classifier_state = ctx.agent_states.get("EmailClassifier")
        if not classifier_state or "classifications" not in classifier_state:
            # No classifications found
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(
                    parts=[types.Part(text="No classifications found. EmailClassifier must run first.")]
                ),
            )
            yield event
            return
        
        classifications = classifier_state["classifications"]
        
        if not classifications:
            # Empty classification list
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(
                    parts=[types.Part(text="No classifications to process.")]
                ),
            )
            yield event
            return
        
        # Retrieve emails from EmailCollector's agent_states
        collector_state = ctx.agent_states.get("EmailCollector")
        if not collector_state or "emails" not in collector_state:
            # No emails found
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
        
        emails: list[Message] = collector_state["emails"]
        
        # Create a mapping from email_id to Message object
        email_map: dict[str, Message] = {email.id: email for email in emails}
        
        # Process each classification
        processing_results = []
        label_counts = {
            "Noise": 0,
            "Promotions": 0,
            "Newsletters": 0,
            "ACTIONABLE": 0,  # No action taken
        }
        errors = []
        
        for classification in classifications:
            email_id = classification.get("email_id")
            classification_category = classification.get("classification", "").upper()
            
            if not email_id:
                errors.append(f"Classification missing email_id: {classification}")
                continue
            
            # Find the corresponding Message object
            message = email_map.get(email_id)
            if not message:
                errors.append(f"Message not found for email_id: {email_id}")
                continue
            
            # Apply label based on classification
            try:
                if classification_category == "NOISE":
                    apply_label_to_message(message, "Noise", remove_inbox=True)
                    label_counts["Noise"] += 1
                    processing_results.append({
                        "email_id": email_id,
                        "sender": classification.get("sender", ""),
                        "subject": classification.get("subject", ""),
                        "classification": classification_category,
                        "action": "Applied 'Noise' label and removed from inbox",
                        "status": "success",
                    })
                elif classification_category == "PROMOTIONAL":
                    apply_label_to_message(message, "Promotions", remove_inbox=True)
                    label_counts["Promotions"] += 1
                    processing_results.append({
                        "email_id": email_id,
                        "sender": classification.get("sender", ""),
                        "subject": classification.get("subject", ""),
                        "classification": classification_category,
                        "action": "Applied 'Promotions' label and removed from inbox",
                        "status": "success",
                    })
                elif classification_category == "INFORMATIONAL":
                    apply_label_to_message(message, "Newsletters", remove_inbox=True)
                    label_counts["Newsletters"] += 1
                    processing_results.append({
                        "email_id": email_id,
                        "sender": classification.get("sender", ""),
                        "subject": classification.get("subject", ""),
                        "classification": classification_category,
                        "action": "Applied 'Newsletters' label and removed from inbox",
                        "status": "success",
                    })
                elif classification_category == "ACTIONABLE":
                    # No action required - leave in inbox
                    label_counts["ACTIONABLE"] += 1
                    processing_results.append({
                        "email_id": email_id,
                        "sender": classification.get("sender", ""),
                        "subject": classification.get("subject", ""),
                        "classification": classification_category,
                        "action": "No action - left in inbox",
                        "status": "success",
                    })
                else:
                    errors.append(f"Unknown classification category: {classification_category} for email_id: {email_id}")
                    processing_results.append({
                        "email_id": email_id,
                        "sender": classification.get("sender", ""),
                        "subject": classification.get("subject", ""),
                        "classification": classification_category,
                        "action": "Unknown classification - no action taken",
                        "status": "error",
                    })
            except Exception as e:
                error_msg = f"Error processing email_id {email_id}: {str(e)}"
                errors.append(error_msg)
                processing_results.append({
                    "email_id": email_id,
                    "sender": classification.get("sender", ""),
                    "subject": classification.get("subject", ""),
                    "classification": classification_category,
                    "action": f"Error: {str(e)}",
                    "status": "error",
                })
        
        # Store processing results in agent_states
        ctx.agent_states[self.name] = {
            "processing_results": processing_results,
            "label_counts": label_counts,
            "total_processed": len(processing_results),
            "errors": errors,
        }
        
        # Create summary event
        summary = {
            "total_processed": len(processing_results),
            "label_counts": label_counts,
            "errors_count": len(errors),
            "errors": errors if errors else None,
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
email_processor = EmailProcessor()
