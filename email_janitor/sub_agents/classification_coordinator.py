"""
ClassificationCoordinator - Orchestrates ClassifierAgent and CriticAgent.

This coordinator implements the Critic-in-the-Loop pattern with:
- Fast path: Skip critic for high-confidence classifications
- Full review: Critic reviews low-confidence classifications
- Refinement loops: Re-classify when critic rejects
- Consensus logic: Weighted confidence scoring
- Deadlock handling: Escalation after max refinements
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
from simplegmail.message import Message

from ..config import ClassificationConfig
from ..models.schemas import (
    ClassificationCollectionOutput,
    ClassificationResult,
    CriticReview,
    EmailCategory,
    EmailClassificationInput,
    EmailClassificationOutput,
    EmailCollectionOutput,
    EmailData,
)
from .critic_agent import CriticAgent


class ClassificationCoordinator(BaseAgent):
    """
    Coordinates email classification with critic review and refinement loops.
    """

    def __init__(
        self,
        name: str = "ClassificationCoordinator",
        description: str | None = None,
        classifier_model: LiteLlm | None = None,
        critic_model: LiteLlm | None = None,
        config: ClassificationConfig | None = None,
    ):
        super().__init__(
            name=name,
            description=description
            or "Coordinates email classification with critic review and refinement.",
        )
        self._classifier_model = classifier_model or LiteLlm(
            model="ollama_chat/llama3.1:8b"
        )
        # self._critic_model = critic_model or LiteLlm(model="ollama_chat/llama3.1:8b")
        self._critic_model = critic_model or LiteLlm(
            model="ollama_chat/mistral-nemo:latest"
        )
        self._config = config or ClassificationConfig()
        self._critic_agent = CriticAgent(model=self._critic_model)

    def _extract_clean_json(self, text: str) -> str:
        """Regex helper to handle local LLM markdown 'chatter'."""
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return match.group(0) if match else text.strip()

    def _should_skip_critic(self, confidence: float) -> bool:
        """Check if critic should be skipped based on confidence threshold."""
        return confidence >= self._config.confidence_threshold

    def _calculate_consensus(
        self,
        classifier_output: EmailClassificationOutput,
        critic_review: CriticReview,
    ) -> float:
        """
        Calculate weighted consensus confidence.

        If critic approved: weighted average of both confidences
        If critic rejected: use critic's confidence with penalty
        """
        weights = self._config.get_consensus_weights()

        if critic_review.approved:
            return (
                classifier_output.confidence * weights["classifier"]
                + critic_review.confidence * weights["critic"]
            )
        else:
            # Critic rejected - use critic's confidence for alternative category
            # Apply penalty for disagreement
            return critic_review.confidence * 0.8  # 20% penalty for disagreement

    def _select_final_category(
        self,
        classifier_output: EmailClassificationOutput,
        critic_review: CriticReview,
    ) -> EmailCategory:
        """Select final category based on critic review."""
        if critic_review.approved:
            return classifier_output.category
        elif critic_review.alternative_category:
            return critic_review.alternative_category
        else:
            # Critic rejected but no alternative - use classifier with low confidence
            return classifier_output.category  # Will be marked as escalated

    def _should_refine(self, refinement_count: int) -> bool:
        """Check if refinement should be attempted."""
        return refinement_count < self._config.max_refinements

    def _handle_escalation(
        self, email_data: EmailData, refinement_count: int
    ) -> ClassificationResult:
        """Handle escalation when max refinements reached."""
        return ClassificationResult(
            email_id=email_data.id,
            sender=email_data.sender,
            subject=email_data.subject,
            classification=self._config.escalation_category,
            reasoning=f"Escalated after {refinement_count} refinement attempts. Requires human review.",
            confidence=0.5,  # Low confidence for escalated items
            critic_status="escalated",
            refinement_count=refinement_count,
            escalation_reason=f"Max refinements ({self._config.max_refinements}) reached without consensus",
        )

    async def _classify_email(
        self,
        ctx: InvocationContext,
        email_data: EmailData,
        email_body: str | None = None,
        critique: str | None = None,
    ) -> EmailClassificationOutput:
        """
        Classify an email using the ClassifierAgent.

        Args:
            ctx: Invocation context
            email_data: Email data to classify
            email_body: Full email body if available
            critique: Optional critique from previous rejection

        Returns:
            EmailClassificationOutput with classification
        """
        classification_input = EmailClassificationInput(
            sender=email_data.sender,
            subject=email_data.subject,
            snippet=email_data.snippet[:500] if email_data.snippet else None,
            body=email_body[:2000] if email_body else None,  # Cap body length
        )

        unique_agent_id = f"Triage_{uuid.uuid4().hex[:8]}"

        # Get consensus weights for instruction context
        weights = self._config.get_consensus_weights()
        classifier_weight_pct = int(weights["classifier"] * 100)
        critic_weight_pct = int(weights["critic"] * 100)

        # Build instruction with optional critique
        base_instruction = f"""
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

CONFIDENCE SCORING GUIDELINES:
Your confidence score (0.0-1.0) is critical for the classification workflow:

1. High Confidence (≥{int(self._config.confidence_threshold * 100)}%): 
   - Your classification will skip critic review (fast path)
   - Use this ONLY when you are extremely certain based on clear, unambiguous evidence
   - Examples: Obvious spam with multiple red flags, clear invoice from known sender

2. Medium/Low Confidence (<{int(self._config.confidence_threshold * 100)}%):
   - Your classification will be reviewed by a critic agent
   - The final consensus confidence will be calculated as:
     - If critic approves: ({classifier_weight_pct}% × your_confidence) + ({critic_weight_pct}% × critic_confidence)
     - If critic rejects: critic's alternative classification will be used with adjusted confidence

3. Confidence Calibration:
   - 0.9-1.0: Extremely certain - clear, unambiguous evidence, no edge cases
   - 0.7-0.89: Very confident - strong evidence, minor ambiguity possible
   - 0.5-0.69: Moderately confident - some evidence, but ambiguity exists
   - 0.3-0.49: Low confidence - weak evidence, significant ambiguity
   - 0.0-0.29: Very uncertain - minimal evidence, high ambiguity

4. Be Honest: Overconfident scores (high confidence on ambiguous emails) will be caught by the critic and require refinement.
   Underconfident scores (low confidence on clear emails) are safer but may slow down processing.

Rule: Base reasoning ONLY on the data provided above. Do not invent keywords.
Extract and list the key terms/keywords that influenced your decision.
"""

        if critique:
            instruction = f"""{base_instruction}

PREVIOUS ATTEMPT REJECTED:
The critic reviewed your previous classification and provided this critique:
"{critique}"

Please re-classify with the critique in mind:
- Address the specific issues raised by the critic
- Be more careful and cite specific evidence from the email
- Recalibrate your confidence score based on the critique
- If the critique suggests ambiguity, lower your confidence accordingly
"""
        else:
            instruction = base_instruction

        classifier_llm = Agent(
            model=self._classifier_model,
            name=unique_agent_id,
            instruction=instruction,
            output_schema=EmailClassificationOutput,
            generate_content_config=types.GenerateContentConfig(
                temperature=0.4, top_k=10
            ),
        )

        classification_output = None
        async for event in classifier_llm.run_async(ctx):
            if event.is_final_response() and event.content:
                raw_text = event.content.parts[0].text or ""
                try:
                    clean_json = self._extract_clean_json(raw_text)
                    classification_output = (
                        EmailClassificationOutput.model_validate_json(clean_json)
                    )
                except Exception as e:
                    classification_output = EmailClassificationOutput(
                        category=EmailCategory.NOISE,
                        reasoning=f"Parsing error: {str(e)}",
                        confidence=0.3,
                    )

        if not classification_output:
            classification_output = EmailClassificationOutput(
                category=EmailCategory.NOISE, reasoning="No response.", confidence=0.3
            )

        return classification_output

    async def _process_email(
        self, ctx: InvocationContext, email_data: EmailData, email_body: str | None
    ) -> ClassificationResult:
        """
        Process a single email through the classification pipeline.

        Returns:
            ClassificationResult with final classification
        """
        refinement_count = 0
        last_critique = None

        while True:
            # Step 1: Classify email
            classifier_output = await self._classify_email(
                ctx, email_data, email_body, critique=last_critique
            )

            # Step 2: Check if we should skip critic (fast path)
            if (
                self._should_skip_critic(classifier_output.confidence)
                and refinement_count == 0
            ):
                # Fast path: high confidence, no previous rejections
                return ClassificationResult(
                    email_id=email_data.id,
                    sender=email_data.sender,
                    subject=email_data.subject,
                    classification=classifier_output.category,
                    reasoning=classifier_output.reasoning,
                    confidence=classifier_output.confidence,
                    critic_status="skipped",
                    refinement_count=0,
                    consensus_confidence=classifier_output.confidence,
                )

            # Step 3: Get critic review
            critic_review = await self._critic_agent.review_classification(
                ctx,
                EmailClassificationInput(
                    sender=email_data.sender,
                    subject=email_data.subject,
                    snippet=email_data.snippet[:500] if email_data.snippet else None,
                    body=email_body[:2000] if email_body else None,
                ),
                classifier_output,
                email_body=email_body,
            )

            # Step 4: Handle critic response
            if critic_review.approved:
                # Critic approved - use consensus
                final_category = self._select_final_category(
                    classifier_output, critic_review
                )
                consensus_conf = self._calculate_consensus(
                    classifier_output, critic_review
                )

                return ClassificationResult(
                    email_id=email_data.id,
                    sender=email_data.sender,
                    subject=email_data.subject,
                    classification=final_category,
                    reasoning=critic_review.suggested_reasoning
                    or classifier_output.reasoning,
                    confidence=classifier_output.confidence,
                    critic_status="approved",
                    refinement_count=refinement_count,
                    consensus_confidence=consensus_conf,
                )
            else:
                # Critic rejected - check if we should refine
                if not self._should_refine(refinement_count):
                    # Max refinements reached - escalate
                    return self._handle_escalation(email_data, refinement_count)

                # Attempt refinement
                refinement_count += 1
                last_critique = critic_review.critique
                # Loop continues with refinement

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """Main execution logic for the coordinator."""
        # 1. State Retrieval
        collector_state = ctx.agent_states.get("EmailCollector")
        if not collector_state or "collection_output" not in collector_state:
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(
                    parts=[types.Part(text="Error: EmailCollector state missing.")]
                ),
            )
            return

        collection_output: EmailCollectionOutput = collector_state["collection_output"]
        current_index = ctx.session.state.get("current_email_index", 0)

        if current_index >= len(collection_output.emails):
            # Ensure final classifications are stored before escalating
            existing_state = ctx.agent_states.get(self.name, {})
            existing_collection = existing_state.get("collection_output")

            if existing_collection:
                ctx.session.state["final_classifications"] = (
                    existing_collection.model_dump()
                )

            # Signal loop completion
            event = Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                branch=ctx.branch,
                content=types.Content(
                    parts=[types.Part(text="All emails classified.")]
                ),
            )
            event.actions.escalate = True
            yield event
            return

        email_data = collection_output.emails[current_index]

        # Get full email body if available
        email_body = None
        emails: list[Message] | None = collector_state.get("emails")
        if emails:
            for msg in emails:
                if msg.id == email_data.id:
                    try:
                        email_body = msg.plain or msg.html or email_data.snippet
                    except Exception:
                        email_body = email_data.snippet
                    break

        # Process email through classification pipeline
        result = await self._process_email(ctx, email_data, email_body)

        # Update State & Yield - Accumulate all classifications
        existing_state = ctx.agent_states.get(self.name, {})
        existing_collection = existing_state.get("collection_output")

        if not existing_collection:
            final_classifications_data = ctx.session.state.get("final_classifications")
            if final_classifications_data:
                try:
                    existing_collection = ClassificationCollectionOutput.model_validate(
                        final_classifications_data
                    )
                except Exception:
                    existing_collection = None

        if existing_collection:
            all_classifications = existing_collection.classifications + [result]
        else:
            all_classifications = [result]

        collection_output = ClassificationCollectionOutput(
            count=len(all_classifications), classifications=all_classifications
        )

        ctx.agent_states[self.name] = {
            "current_classification": result,
            "collection_output": collection_output,
        }

        ctx.session.state["final_classifications"] = collection_output.model_dump()
        ctx.session.state["current_email_index"] = current_index + 1

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            branch=ctx.branch,
            content=types.Content(
                parts=[types.Part(text=result.model_dump_json(indent=2))]
            ),
        )


# Create a default instance
classification_coordinator = ClassificationCoordinator()
