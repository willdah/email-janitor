# Security Policy

## Supported versions

Only the latest `0.1.x` release receives security updates while the project is
pre-1.0. Older releases will not be patched; please upgrade before reporting.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Use GitHub's private vulnerability reporting:

1. Go to <https://github.com/willdah/email-janitor/security/advisories/new>.
2. Describe the issue, the affected version, and a reproducer if you have one.
3. A maintainer will acknowledge within **7 days** and aim to ship a fix or a
   mitigation within **30 days**, coordinating a disclosure window with you.

If GitHub's form is unavailable, open a blank issue titled
"Security contact request" (no details) and a maintainer will follow up with a
private channel.

## Threat model & scope

Email Janitor runs on the operator's own machine and talks to two external
services: the Gmail API and an LLM provider. The following are in-scope for
security reports; findings outside this scope are welcome but may be triaged
as hardening suggestions rather than vulnerabilities.

### In scope

- **Credential handling.** `client_secret.json` and `gmail_token.json` live in
  the project root. Any path that logs, transmits, or otherwise exposes their
  contents is a security bug.
- **Prompt injection / instruction hijacking.** Incoming email bodies are
  untrusted. The classifier wraps them in an `<untrusted_email>` boundary and
  strips HTML before they reach the LLM (see
  [`src/email_janitor/instructions/email_classifier_agent.py`](src/email_janitor/instructions/email_classifier_agent.py)
  and [`src/email_janitor/utils/html_strip.py`](src/email_janitor/utils/html_strip.py)).
  Any reproducer that causes the classifier to execute instructions from an
  email body — including exfiltrating other state, changing category labels
  systematically, or crashing the loop — is in scope. See
  [`tests/eval/golden_emails.jsonl`](tests/eval/golden_emails.jsonl) for the
  adversarial corpus we already regress against.
- **SQLite data integrity.** Anything that lets an attacker corrupt
  `runs` / `classifications` / `corrections` or inject arbitrary SQL.
- **Dependency supply chain.** Known CVEs in pinned dependencies (see
  [`pyproject.toml`](pyproject.toml)).

### Out of scope

- The privacy posture of a **remote LLM provider** chosen by the operator. If
  you override `EMAIL_CLASSIFIER_MODEL` to point at a hosted LLM, email
  contents leave your machine. That is an operator decision, not a product
  vulnerability.
- Issues that require an attacker to already have filesystem access to the
  host running Email Janitor.
- Denial of service caused by a user-configured LLM being too slow; see
  `EMAIL_CLASSIFIER_LLM_TIMEOUT_SECONDS` and the outer poll-loop backoff.
- Social engineering of the Gmail account itself (phishing, OAuth consent
  abuse by unrelated apps, etc.).

## Safe harbor

Good-faith research that stays within the scope above will not be met with
legal action. Please do not test against inboxes you do not own.
