"""
CriticAgent - A Review Agent for Email Classifications.

This agent reviews the ClassifierAgent's output and provides critique,
alternative classifications, and confidence scores. Designed with anti-rubber-stamp
prompting to ensure it catches errors rather than automatically approving.
"""

import re
import uuid
from typing import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import Agent
from google.adk.events.event import Event
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from ..models.schemas import (
    CriticInput,
    CriticReview,
    EmailClassificationInput,
    EmailClassificationOutput,
)


class CriticAgent(BaseAgent):
    """Agent that reviews email classifications for accuracy."""

    def __init__(
        self,
        name: str = "CriticAgent",
        description: str | None = None,
        model: LiteLlm | None = None,
    ):
        super().__init__(
            name=name,
            description=description
            or "Reviews email classifications for accuracy and provides critique.",
        )
        self._model_config = model or LiteLlm(model="ollama_chat/llama3.1:8b")

    def _extract_clean_json(self, text: str) -> str:
        """Regex helper to handle local LLM markdown 'chatter'."""
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return match.group(0) if match else text.strip()

    def _build_critic_instruction(self, critic_input: CriticInput) -> str:
        """Build the system instruction for the critic agent."""
        email_data = critic_input.original_email
        classification = critic_input.classification_output
        email_body = (
            critic_input.email_body or email_data.snippet or "No body available"
        )

        return f"""
Role: You are a strict Email Classification Reviewer. Your job is to catch errors, not approve everything.

Task: Review the ClassifierAgent's classification of the email below.

CRITICAL RULES:
1. DO NOT automatically approve. Question every classification.
2. Look for misclassification patterns:
   - ACTIONABLE emails mislabeled as NOISE (high cost of false negatives)
   - NOISE emails mislabeled as ACTIONABLE (inbox clutter)
   - PROMOTIONAL vs INFORMATIONAL confusion
3. Verify the reasoning cites SPECIFIC evidence from the email body
4. Check if confidence score matches the ambiguity of the email
5. If uncertain, REJECT and provide alternative classification

Evaluation Criteria:
- Reasoning Quality: Does the reasoning cite specific keywords/phrases from the email?
- Category Fit: Does the category match the email's actual purpose?
- Confidence Calibration: Is the confidence score justified? (High confidence on ambiguous emails = reject)
- Edge Cases: Is this a borderline case that needs human review?

--- ORIGINAL EMAIL ---
Sender: {email_data.sender}
Subject: {email_data.subject}
Body/Snippet: {email_body[:1000] if len(email_body) > 1000 else email_body}
---

--- CLASSIFIER'S OUTPUT ---
Category: {classification.category}
Reasoning: {classification.reasoning}
Confidence: {classification.confidence}
Keywords Found: {", ".join(classification.keywords_found) if classification.keywords_found else "None"}
---

Output Format:
- approved: true ONLY if you are confident the classification is correct
- approved: false if there's ANY doubt, ambiguity, or missing evidence
- alternative_category: Provide your best alternative if rejecting
- critique: Explain SPECIFIC issues (e.g., "Reasoning cites 'invoice' but email is about 'invoice templates', not actual invoice")
- confidence: Your confidence in YOUR review (not the original classification)

Remember: False negatives (missing ACTIONABLE emails) are more costly than false positives (extra reviews).
When in doubt, REJECT and suggest refinement.
"""

    async def review_classification(
        self,
        ctx: InvocationContext,
        original_email: EmailClassificationInput,
        classification_output: EmailClassificationOutput,
        email_body: str | None = None,
    ) -> CriticReview:
        """
        Review a classification and return critique.

        Args:
            ctx: Invocation context
            original_email: Original email input
            classification_output: Classification to review
            email_body: Full email body if available

        Returns:
            CriticReview with approval status and critique
        """
        critic_input = CriticInput(
            original_email=original_email,
            classification_output=classification_output,
            email_body=email_body,
        )

        unique_agent_id = f"Critic_{uuid.uuid4().hex[:8]}"
        instruction = self._build_critic_instruction(critic_input)

        critic_llm = Agent(
            model=self._model_config,
            name=unique_agent_id,
            instruction=instruction,
            output_schema=CriticReview,
            generate_content_config=types.GenerateContentConfig(
                temperature=0.3,  # Lower temperature for more consistent critique
                top_k=10,
            ),
        )

        review_output = None
        async for event in critic_llm.run_async(ctx):
            if event.is_final_response() and event.content:
                raw_text = event.content.parts[0].text or ""
                try:
                    clean_json = self._extract_clean_json(raw_text)
                    review_output = CriticReview.model_validate_json(clean_json)
                except Exception as e:
                    # Default to rejection if parsing fails
                    review_output = CriticReview(
                        approved=False,
                        confidence=0.3,
                        critique=f"Parsing error: {str(e)}. Defaulting to rejection for safety.",
                    )

        if not review_output:
            # Default to rejection if no response
            review_output = CriticReview(
                approved=False,
                confidence=0.3,
                critique="No response from critic. Defaulting to rejection for safety.",
            )

        return review_output

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """
        Default async implementation.

        Note: This agent is typically called programmatically via review_classification(),
        but this method provides a fallback for direct invocation.
        """
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(
                parts=[
                    types.Part(
                        text="CriticAgent should be called via review_classification() method."
                    )
                ]
            ),
        )


# Create a default instance
critic_agent = CriticAgent()
