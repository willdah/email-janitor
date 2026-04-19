"""Run the classifier against a labeled dataset and score the results.

The harness reuses the production prompt-building path (``build_instruction``
+ ``select_relevant_corrections``) and the production parse path (regex
extraction + ``EmailClassificationOutput.model_validate_json``), so a passing
eval reflects the behavior users would get in production.

LLM invocation goes through ``litellm.completion`` directly rather than through
ADK's ``Runner`` + ``LlmAgent``. This avoids the per-case overhead of setting
up a full ADK session for what is effectively a stateless classification call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..config import EmailClassifierConfig
from ..corrections.db import get_corrections_for_few_shot
from ..corrections.relevance import select_relevant_corrections
from ..instructions.email_classifier_agent import build_instruction
from ..schemas.schemas import (
    EmailCategory,
    EmailClassificationInput,
    EmailClassificationOutput,
)
from .dataset import GoldenCase
from .metrics import EvalReport, compute_report


@dataclass
class CaseResult:
    case_id: str
    expected: EmailCategory
    predicted: EmailCategory
    confidence: float
    reasoning: str
    parse_failed: bool
    prompt_len: int
    raw_response: str


class Completer(Protocol):
    """Minimal contract for LLM completion. Matches ``litellm.completion`` surface."""

    def __call__(self, *, model: str, messages: list[dict], **kwargs: Any) -> Any: ...


def _default_completer() -> Completer:
    """Import litellm lazily so the eval module can be imported without live deps."""
    import litellm

    return litellm.completion  # type: ignore[return-value]


def _extract_text(response: Any) -> str:
    """Pull the assistant text out of a litellm completion response."""
    try:
        return response["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


def _parse_output(raw_text: str) -> tuple[EmailClassificationOutput, bool]:
    """Mirror the parse path in ``EmailClassifierAgent._run_async_impl``.

    Returns (output, parse_failed). On failure returns NOISE + conf 1.0 so the
    eval treats unparseable responses the same way production does.
    """
    try:
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        return EmailClassificationOutput.model_validate_json(
            match.group(0) if match else raw_text
        ), False
    except Exception:
        return EmailClassificationOutput(
            category=EmailCategory.NOISE,
            reasoning="Parsing error",
            confidence=1.0,
        ), True


def run_case(
    case: GoldenCase,
    *,
    completer: Completer,
    model: str,
    corrections_pool: list[dict],
    include_few_shot: bool = True,
    temperature: float = 0.4,
    top_k: int = 10,
    timeout: float | int = 30,
) -> CaseResult:
    """Classify a single golden case and return the outcome."""
    if include_few_shot and corrections_pool:
        # Exclude any correction this case was seeded from (data-leakage guard).
        # Identity matching is best-effort: we have an id tag, but the few-shot
        # dicts don't carry ids. Callers should pre-filter the pool.
        relevant = select_relevant_corrections(corrections_pool, case.sender)
    else:
        relevant = []

    prompt = build_instruction(
        EmailClassificationInput(
            sender=case.sender,
            subject=case.subject,
            body=case.body[:2000] if case.body else None,
            snippet=case.snippet[:500] if case.snippet else None,
        ),
        corrections=relevant,
    )

    response = completer(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        top_k=top_k,
        timeout=timeout,
    )
    raw_text = _extract_text(response)
    output, parse_failed = _parse_output(raw_text)

    return CaseResult(
        case_id=case.id,
        expected=case.expected_category,
        predicted=output.category,
        confidence=output.confidence,
        reasoning=output.reasoning,
        parse_failed=parse_failed,
        prompt_len=len(prompt),
        raw_response=raw_text,
    )


def _filter_pool(
    pool: list[dict], exclude_correction_ids: set[int]
) -> list[dict]:
    """Drop corrections whose id is in the exclusion set.

    The few-shot pool from ``get_corrections_for_few_shot`` does not carry
    correction ids, so this is a noop unless callers have enriched the pool
    with an ``_id`` key.
    """
    if not exclude_correction_ids:
        return pool
    return [c for c in pool if c.get("_id") not in exclude_correction_ids]


def run_dataset(
    cases: list[GoldenCase],
    *,
    completer: Completer | None = None,
    config: EmailClassifierConfig | None = None,
    corrections_pool: list[dict] | None = None,
    corrections_db_path: Path | None = None,
    include_few_shot: bool = True,
    progress: bool = False,
) -> tuple[list[CaseResult], EvalReport]:
    """Run the whole dataset and return per-case results plus an aggregate report.

    ``corrections_pool`` wins over ``corrections_db_path``. If neither is given
    and ``include_few_shot`` is true, the pool is an empty list.
    """
    cfg = config or EmailClassifierConfig()
    complete = completer or _default_completer()

    pool: list[dict] = []
    if include_few_shot:
        if corrections_pool is not None:
            pool = corrections_pool
        elif corrections_db_path is not None and corrections_db_path.exists():
            pool = get_corrections_for_few_shot(corrections_db_path)

    results: list[CaseResult] = []
    for i, case in enumerate(cases):
        # Data-leakage guard per-case.
        case_pool = (
            _filter_pool(pool, {case.source_correction_id})
            if case.source_correction_id is not None
            else pool
        )
        result = run_case(
            case,
            completer=complete,
            model=cfg.model,
            corrections_pool=case_pool,
            include_few_shot=include_few_shot,
        )
        results.append(result)
        if progress:
            status = "OK" if result.expected == result.predicted else "MISS"
            print(
                f"[{i + 1:3d}/{len(cases)}] {case.id} "
                f"expected={case.expected_category.value} "
                f"predicted={result.predicted.value} "
                f"conf={result.confidence:.1f} [{status}]"
            )

    report = compute_report(
        expected=[r.expected for r in results],
        predicted=[r.predicted for r in results],
        confidences=[r.confidence for r in results],
        parse_failures=sum(1 for r in results if r.parse_failed),
    )
    return results, report
