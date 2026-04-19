# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-04-18

### Added
- Sequential ADK pipeline — collector, classifier loop, labeler — with
  configurable poll interval.
- Five-category classification: `URGENT`, `PERSONAL`, `INFORMATIONAL`,
  `PROMOTIONAL`, `NOISE`. `URGENT` and `PERSONAL` stay in the inbox; others
  are archived under a `janitor/*` label.
- Local-first classification via Ollama / LiteLLM (`ollama_chat/llama3.1:8b`
  by default) — no email bodies leave the machine unless the operator
  changes the model.
- SQLite persistence (`runs`, `classifications`, `corrections`) with
  `aiosqlite` for non-blocking writes and WAL mode for safe concurrent
  access from the corrections UI.
- Streamlit corrections UI surfacing every classification with filters for
  run, category, confidence, and review status. Submitted corrections feed
  back into the classifier as few-shot examples.
- Offline eval harness (`python -m email_janitor.eval`) producing per-category
  precision/recall/F1, a confusion matrix, and a confidence-calibration
  table, with a seeder that lifts cases out of the corrections table.
- Golden dataset of handcrafted sanity cases plus adversarial cases for
  prompt injection, instruction-bearing subjects, fake JSON payloads,
  spoofed senders, and HTML-only bodies.
- Prompt-injection defenses: email bodies are wrapped in an
  `<untrusted_email>` boundary, the prompt forbids following embedded
  instructions, and HTML is stripped before it reaches the LLM.
- Low-confidence review routing: classifications below
  `EMAIL_CLASSIFIER_CONFIDENCE_THRESHOLD` get `janitor/review`, stay in the
  inbox, and are flagged `status=needs_review` for triage.
- Structured JSON logs and optional OpenTelemetry tracing
  (`OTEL_EXPORT=console|otlp`) with a per-email `classify_email` span.
- Resilience: Gmail calls retry on 429/5xx/connection errors with
  exponential backoff; LLM calls have a per-call timeout plus LiteLLM
  retries; the outer poll loop backs off on repeated pipeline errors.
- Docker image published to GHCR via GitHub Actions
  (`.github/workflows/docker-publish.yml`) on pushes to `main` and tags.
- Docker Compose file running the pipeline and the corrections UI as
  separate services against a shared named volume.

[Unreleased]: https://github.com/willdah/email-janitor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/willdah/email-janitor/releases/tag/v0.1.0
