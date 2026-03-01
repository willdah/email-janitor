"""Select the most relevant corrections for a given email."""

from __future__ import annotations


def select_relevant_corrections(
    corrections: list[dict],
    sender: str,
    *,
    max_examples: int = 10,
) -> list[dict]:
    """Return up to *max_examples* corrections most relevant to *sender*.

    Priority tiers (highest first):
      1. Same sender (exact match, case-insensitive)
      2. Same domain (e.g. @example.com)
      3. Recent corrections (general signal)

    Within each tier the input order is preserved (the DB query returns
    corrections ordered by ``corrected_at DESC``).
    """
    if not corrections or not sender:
        return []

    sender_lower = sender.lower()
    domain = _extract_domain(sender_lower)

    same_sender: list[dict] = []
    same_domain: list[dict] = []
    general: list[dict] = []

    for c in corrections:
        c_sender = (c.get("sender") or "").lower()
        if c_sender == sender_lower:
            same_sender.append(c)
        elif domain and _extract_domain(c_sender) == domain:
            same_domain.append(c)
        else:
            general.append(c)

    ranked = same_sender + same_domain + general
    return ranked[:max_examples]


def _extract_domain(email_addr: str) -> str:
    """Extract the domain from an email address.

    Handles both ``user@domain.com`` and ``Name <user@domain.com>`` formats.
    Returns an empty string when no domain can be parsed.
    """
    if "<" in email_addr and ">" in email_addr:
        email_addr = email_addr.split("<")[1].split(">")[0]
    at_idx = email_addr.rfind("@")
    if at_idx == -1:
        return ""
    return email_addr[at_idx + 1 :].strip()
