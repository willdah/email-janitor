"""
EmailClassifier - A High-Isolation Agent for Strict Email Triage.
Designed to prevent context leakage in local LLM environments.
"""

import json
import re
import uuid
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
    def __init__(
        self,
        name: str = "EmailClassifier",
        description: str | None = None,
        model: LiteLlm | None = None,
    ):
        super().__init__(
            name=name,
            description=description or "Classifies emails with absolute object-level isolation.",
        )
        # Store the model config but don't create the agent yet
        self._model_config = model or LiteLlm(model="ollama_chat/llama3.1:8b")

    def _extract_clean_json(self, text: str) -> str:
        """Regex helper to handle local LLM markdown 'chatter'."""
        match = re.search(r'\{.*\}', text, re.DOTALL)
        return match.group(0) if match else text.strip()

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # 1. State Retrieval
        collector_state = ctx.agent_states.get("EmailCollector")
        if not collector_state or "collection_output" not in collector_state:
            yield Event(invocation_id=ctx.invocation_id, author=self.name, branch=ctx.branch,
                        content=types.Content(parts=[types.Part(text="Error: EmailCollector state missing.")]))
            return

        collection_output: EmailCollectionOutput = collector_state["collection_output"]
        current_index = ctx.session.state.get("current_email_index", 0)
        
        if current_index >= len(collection_output.emails):
            yield Event(invocation_id=ctx.invocation_id, author=self.name, branch=ctx.branch,
                        content=types.Content(parts=[types.Part(text="Loop complete.")]))
            return

        email_data = collection_output.emails[current_index]

        # 2. Data Preparation
        # We cap the snippet to keep the model focused
        classification_input = EmailClassificationInput(
            sender=email_data.sender,
            subject=email_data.subject,
            snippet=email_data.snippet[:500] 
        )

        # 3. THE ISOLATION FIX: Create a disposable Agent per email
        # We bake the data into the system instruction and use a unique ID
        unique_agent_id = f"Triage_{uuid.uuid4().hex[:8]}"
        
        classifier_llm = Agent(
            model=self._model_config,
            name=unique_agent_id,
            instruction=f"""
            Role: You are a strict Email Triage Assistant. 
            Task: Classify ONLY the email provided below.
            
            Categories:
            1. ACTIONABLE: Security alerts, invoices, bills, or direct messages from individuals.
            2. INFORMATIONAL: Newsletters, shipping updates, or trusted industry news.
            3. PROMOTIONAL: Sales, coupons, or marketing offers.
            4. NOISE: Spam or irrelevant content.

            --- DATA TO CLASSIFY ---
            {classification_input.model_dump_json()}
            -----------------------

            Rule: Base reasoning ONLY on the data provided above. Do not invent keywords.
            """,
            output_schema=EmailClassificationOutput,
            generate_content_config=types.GenerateContentConfig(
                temperature=0.4, # Forces deterministic selection
                top_k=10
            )
        )

        # 4. Execution
        classification_output = None
        async for event in classifier_llm.run_async(ctx):
            if event.is_final_response() and event.content:
                raw_text = event.content.parts[0].text or ""
                try:
                    clean_json = self._extract_clean_json(raw_text)
                    classification_output = EmailClassificationOutput.model_validate_json(clean_json)
                except Exception as e:
                    classification_output = EmailClassificationOutput(
                        category=EmailCategory.NOISE,
                        reasoning=f"Parsing error: {str(e)}"
                    )

        # 5. Final Result Assembly
        if not classification_output:
            classification_output = EmailClassificationOutput(category=EmailCategory.NOISE, reasoning="No response.")

        result = ClassificationResult(
            email_id=email_data.id,
            sender=email_data.sender,
            subject=email_data.subject,
            classification=classification_output.category,
            reasoning=classification_output.reasoning,
        )

        # 6. Update State & Yield
        ctx.agent_states[self.name] = {
            "current_classification": result,
            "collection_output": ClassificationCollectionOutput(count=1, classifications=[result])
        }
        ctx.session.state["current_email_index"] = current_index + 1

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(parts=[types.Part(text=result.model_dump_json(indent=2))])
        )

email_classifier = EmailClassifier()