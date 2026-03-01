from __future__ import annotations


def build_instruction(
    classification_input,
    corrections: list[dict] | None = None,
) -> str:
    few_shot_section = _format_few_shot_examples(corrections) if corrections else ""

    return f"""
  Role: You are an expert email classifier that classifies emails into one of the following categories:
    1. ACTIONABLE: Security alerts, invoices, bills, or direct messages from individuals.
    2. INFORMATIONAL: Newsletters, shipping updates, or trusted industry news.
    3. PROMOTIONAL: Sales, coupons, or marketing offers.
    4. NOISE: Spam or irrelevant content.

{few_shot_section}
  Task: Classify ONLY the email provided below.

  --- EMAIL TO CLASSIFY ---
  {classification_input.model_dump_json()}
  -------------------------

  CONFIDENCE SCORING GUIDELINES:
  Your confidence score (1-5) indicates how certain you are about the classification:

  1. Confidence Calibration:
    - 5: Extremely confident - clear, unambiguous evidence, no edge cases
    - 4: Very confident - strong evidence, minor ambiguity possible
    - 3: Moderately confident - some evidence, but ambiguity exists
    - 2: Low confidence - weak evidence, significant ambiguity
    - 1: Unsure - minimal evidence, high ambiguity
  """


def _format_few_shot_examples(corrections: list[dict]) -> str:
    """Format correction dicts into a labeled examples section for the prompt."""
    if not corrections:
        return ""

    lines = [
        "  EXAMPLES FROM PREVIOUS CORRECTIONS:",
        "  The following are real emails that were previously misclassified and then",
        "  corrected by a human reviewer. Use these as reference for your classification.",
        "",
    ]

    for i, c in enumerate(corrections, 1):
        sender = c.get("sender", "unknown")
        subject = c.get("subject", "unknown")
        original = c.get("original_classification", "?")
        corrected = c.get("corrected_classification", "?")
        notes = c.get("notes", "")

        lines.append(f"  Example {i}:")
        lines.append(f"    Sender: {sender}")
        lines.append(f"    Subject: {subject}")
        lines.append(f"    Incorrect classification: {original}")
        lines.append(f"    Correct classification: {corrected}")
        if notes:
            lines.append(f"    Reviewer note: {notes}")
        lines.append("")

    return "\n".join(lines)
