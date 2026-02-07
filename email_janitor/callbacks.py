"""
ADK Callbacks for Email Janitor.

This module contains callback functions that handle deterministic logic
previously embedded in custom agents:
- State initialization (replaces EmailLoopAgent)
- LLM response JSON cleanup
- Classification accumulation
"""

import re
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
from google.genai import types

from .models.schemas import (
    ClassificationCollectionOutput,
    EmailCollectionOutput,
)


def initialize_loop_state_callback(
    callback_context: CallbackContext,
) -> Optional[types.Content]:
    """
    Before-agent callback that initializes loop state for email processing.

    This replaces the EmailLoopAgent by performing state initialization
    before the EmailClassifierLoopAgent runs.

    Args:
        callback_context: ADK callback context with access to session state

    Returns:
        Content to skip the agent if no emails to process, None to proceed
    """
    # Retrieve collection output from session state (stored by EmailCollectorAgent)
    collector_output_data = callback_context.state.get("collector_output")
    if not collector_output_data:
        return types.Content(
            parts=[
                types.Part(
                    text="No emails found. EmailCollectorAgent must run first."
                )
            ]
        )

    # Parse the collection output from serialized dict
    try:
        collection_output = EmailCollectionOutput.model_validate(collector_output_data)
    except Exception:
        return types.Content(
            parts=[
                types.Part(
                    text="Invalid email collection output format."
                )
            ]
        )

    email_count = len(collection_output.emails)

    if email_count == 0:
        return types.Content(
            parts=[types.Part(text="No emails to process. Skipping loop.")]
        )

    # Check if state is already initialized (avoid re-initialization on loop iterations)
    if callback_context.state.get("current_email_index") is None:
        callback_context.state["current_email_index"] = 0
        callback_context.state["total_emails"] = email_count
        callback_context.state["user"] = "email-janitor-user"

    # Proceed with agent execution
    return None


def cleanup_llm_json_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """
    After-model callback that cleans up JSON from LLM responses.

    Local LLMs often wrap JSON in markdown code blocks. This callback
    extracts the raw JSON for proper parsing.

    Args:
        callback_context: ADK callback context
        llm_response: The raw LLM response

    Returns:
        Modified LlmResponse with cleaned JSON, or None to use as-is
    """
    if not llm_response.content or not llm_response.content.parts:
        return None

    # Get the text content from the response
    text_parts = [p for p in llm_response.content.parts if hasattr(p, "text") and p.text]
    if not text_parts:
        return None

    original_text = text_parts[0].text
    if not original_text:
        return None

    # Extract JSON from markdown code blocks if present
    # Pattern: ```json ... ``` or ``` ... ```
    cleaned_text = original_text.strip()

    # Remove leading ```json or ```
    cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text)
    # Remove trailing ```
    cleaned_text = re.sub(r"\s*```$", "", cleaned_text)

    # If the text changed, create a new response with cleaned content
    if cleaned_text != original_text:
        # Extract just the JSON object if there's extra text
        match = re.search(r"\{.*\}", cleaned_text, re.DOTALL)
        if match:
            cleaned_text = match.group(0)

        new_parts = [types.Part(text=cleaned_text)]
        # Preserve any non-text parts
        new_parts.extend(p for p in llm_response.content.parts if not (hasattr(p, "text") and p.text))

        return LlmResponse(
            content=types.Content(parts=new_parts),
            usage_metadata=llm_response.usage_metadata,
            error_message=llm_response.error_message,
        )

    return None


def accumulate_classifications_callback(
    callback_context: CallbackContext,
) -> Optional[types.Content]:
    """
    After-agent callback that accumulates classification results.

    This callback runs after each EmailClassifierAgent iteration to:
    1. Retrieve the current classification result from session state
    2. Merge it with existing classifications
    3. Store the accumulated results in session state

    Note: The EmailClassifierAgent must store 'current_classification' in session.state
    for this callback to work.

    Args:
        callback_context: ADK callback context

    Returns:
        None to preserve the agent's original output
    """
    # Get the current classification from session state
    # (EmailClassifierAgent stores this after each classification)
    current_classification_data = callback_context.state.get("current_classification")

    if not current_classification_data:
        return None

    # Get existing accumulated classifications
    existing_data = callback_context.state.get("final_classifications")
    existing_classifications = []

    if existing_data:
        try:
            existing_collection = ClassificationCollectionOutput.model_validate(
                existing_data
            )
            existing_classifications = [
                c.model_dump() if hasattr(c, "model_dump") else c
                for c in existing_collection.classifications
            ]
        except Exception:
            pass

    # Accumulate classifications (ensure we have dicts for serialization)
    classification_dict = (
        current_classification_data.model_dump()
        if hasattr(current_classification_data, "model_dump")
        else current_classification_data
    )
    all_classifications = existing_classifications + [classification_dict]

    # Create updated collection and store in session state
    collection_data = {
        "count": len(all_classifications),
        "classifications": all_classifications,
    }
    callback_context.state["final_classifications"] = collection_data

    # Increment email index for next iteration
    current_index = callback_context.state.get("current_email_index", 0)
    callback_context.state["current_email_index"] = current_index + 1

    return None
