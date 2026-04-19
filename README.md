# Email Janitor

[![CI](https://github.com/willdah/email-janitor/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/willdah/email-janitor/actions/workflows/docker-publish.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://docs.astral.sh/uv/)

> A local-LLM agent that classifies, labels, and archives your Gmail inbox — automatically.

Email Janitor is an agentic pipeline built on [Google ADK](https://github.com/google/adk) that
collects unread Gmail messages, classifies each one (URGENT, PERSONAL, INFORMATIONAL, PROMOTIONAL,
or NOISE) using a local LLM via [LiteLLM](https://docs.litellm.ai/) + Ollama, then applies Gmail
labels and archives messages accordingly. Everything runs on your machine — no email bodies leave
it unless you point the model at a hosted provider.

<!-- Screenshot: docs/images/corrections-ui.png
     To capture: run `make corrections`, open http://localhost:8501,
     screenshot the default view, and save as docs/images/corrections-ui.png. -->

## Table of Contents

- [Why Email Janitor](#why-email-janitor)
- [Features](#features)
- [Quickstart](#quickstart)
  - [Docker (recommended)](#docker-recommended)
  - [Local with uv](#local-with-uv)
- [Configuration](#configuration)
- [Usage](#usage)
- [Architecture](#architecture)
- [Database](#database)
- [Corrections UI](#corrections-ui)
- [Evaluation](#evaluation)
- [Observability](#observability)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

## Why Email Janitor

Most inbox-zero tools either require a cloud LLM (your email bodies go to OpenAI, Anthropic, etc.)
or rely on rigid keyword rules that need constant tuning. Email Janitor runs a small local model via
Ollama, keeping email content on your machine, and learns from your corrections: fix
a misclassification once in the Streamlit UI and the change feeds back into the prompt as a few-shot
example on the next run.

## Features

- **Fully local by default**: Ollama + `llama3.1:8b`; no email content leaves your machine.
- **5-category classification**: URGENT, PERSONAL, INFORMATIONAL, PROMOTIONAL, NOISE with
  configurable confidence thresholds.
- **Human-in-the-loop corrections**: Streamlit UI for reviewing and correcting classifications;
  corrections become few-shot examples automatically.
- **Prompt-injection defenses**: email bodies wrapped in `<untrusted_email>` tags; HTML stripped
  before reaching the model.
- **Low-confidence review routing**: uncertain classifications go to `janitor/review` and stay in
  the inbox for triage instead of being silently archived.
- **Offline eval harness**: precision/recall/F1 per category, confusion matrix, and confidence
  calibration against a golden JSONL dataset.
- **Structured observability**: JSON logs with `jq`-friendly fields and optional OpenTelemetry
  tracing.
- **Resilience**: exponential backoff on Gmail 429/5xx errors; LLM timeouts and retries; poll-loop
  backoff on repeated failures.
- **Docker Compose**: one command to run the pipeline and corrections UI against a persistent
  volume.

## Quickstart

You need:
- Gmail OAuth credentials (`client_secret.json` + `gmail_token.json`); see [Gmail credentials](#gmail-credentials)
- Ollama running with `llama3.1:8b` pulled, or another [LiteLLM-compatible provider](https://docs.litellm.ai/docs/providers)

### Docker (recommended)

```bash
# Clone
git clone https://github.com/willdah/email-janitor.git
cd email-janitor

# Run Gmail OAuth once to generate gmail_token.json
make auth

# Start pipeline + corrections UI
docker compose up
```

The pipeline starts immediately; the corrections UI is at `http://localhost:8501`.

What you should see in the logs:

```json
{"ts":"2026-04-18T10:00:01Z","level":"INFO","msg":"run_start","run_id":"...","poll_interval":10}
{"ts":"2026-04-18T10:00:03Z","level":"INFO","msg":"email_classified","email_id":"...","category":"PROMOTIONAL","confidence":4.8}
{"ts":"2026-04-18T10:00:04Z","level":"INFO","msg":"run_complete","emails_collected":3,"emails_classified":3,"emails_labelled":3}
```

### Local with uv

```bash
git clone https://github.com/willdah/email-janitor.git
cd email-janitor
make install   # uv sync --group dev
make auth      # Gmail OAuth flow
make run       # starts the polling loop
```

## Configuration

All settings are optional; defaults work out-of-the-box with a local Ollama instance.

### Gmail credentials

Place `client_secret.json` and `gmail_token.json` in the project root. For Docker, they are mounted
into the container (see [compose.yml](compose.yml)).

Run the OAuth flow once to generate `gmail_token.json`:

```bash
make auth
```

### Environment variables

Copy `.env.example` to `.env` and adjust as needed.

#### App (`EMAIL_JANITOR_` prefix)

| Variable                      | Description                                                        | Default              |
| ----------------------------- | ------------------------------------------------------------------ | -------------------- |
| `EMAIL_JANITOR_POLL_INTERVAL` | Seconds between processing runs                                    | `10`                 |
| `EMAIL_JANITOR_USER_ID`       | User ID for ADK session management                                 | `email-janitor-user` |
| `EMAIL_JANITOR_APP_NAME`      | Application name passed to ADK runner (must be a valid identifier) | `EmailJanitor`       |

#### Classifier (`EMAIL_CLASSIFIER_` prefix)

| Variable                                | Description                                                                                                                | Default                   |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| `EMAIL_CLASSIFIER_MODEL`                | LiteLLM model ID                                                                                                           | `ollama_chat/llama3.1:8b` |
| `EMAIL_CLASSIFIER_CONFIDENCE_THRESHOLD` | Minimum confidence to trust a classification (1–5). Below this, emails go to `janitor/review` instead of being archived.  | `4.0`                     |
| `EMAIL_CLASSIFIER_LLM_TIMEOUT_SECONDS`  | Hard per-call LLM timeout. Exceeding it counts as a retryable failure.                                                     | `30.0`                    |
| `EMAIL_CLASSIFIER_LLM_NUM_RETRIES`      | LiteLLM's built-in retry count for transient LLM errors (timeouts, 5xx, connection).                                       | `3`                       |

#### Gmail (`GMAIL_` prefix)

| Variable                    | Description                                                        | Default              |
| --------------------------- | ------------------------------------------------------------------ | -------------------- |
| `GMAIL_PROCESSED_LABEL`     | Label applied to every processed email                             | `janitor/done`       |
| `GMAIL_URGENT_LABEL`        | Label applied to URGENT emails (kept in inbox)                     | `janitor/urgent`     |
| `GMAIL_PERSONAL_LABEL`      | Label applied to PERSONAL emails (kept in inbox)                   | `janitor/personal`   |
| `GMAIL_NOISE_LABEL`         | Label applied to NOISE emails                                      | `janitor/noise`      |
| `GMAIL_PROMOTIONAL_LABEL`   | Label applied to PROMOTIONAL emails                                | `janitor/promotions` |
| `GMAIL_INFORMATIONAL_LABEL` | Label applied to INFORMATIONAL emails                              | `janitor/newsletters`|
| `GMAIL_REVIEW_LABEL`        | Label applied to low-confidence classifications (kept in inbox)    | `janitor/review`     |
| `GMAIL_INBOX_QUERY`         | Base Gmail search query for fetching emails                        | `in:inbox -in:sent`  |

Labels are created automatically if they don't exist. The `janitor/*` hierarchy appears as a
collapsible `janitor` parent in the Gmail sidebar.

#### Database (`DATABASE_` prefix)

| Variable        | Description                       | Default            |
| --------------- | --------------------------------- | ------------------ |
| `DATABASE_PATH` | Path to the SQLite database file  | `email_janitor.db` |

In Docker, this is set to `/data/email_janitor.db` and backed by a named volume (see [compose.yml](compose.yml)).

#### Observability

| Variable      | Description                                                               | Default |
| ------------- | ------------------------------------------------------------------------- | ------- |
| `LOG_LEVEL`   | Root log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)                      | `INFO`  |
| `OTEL_EXPORT` | OpenTelemetry span exporter: `off`, `console` (stdout), or `otlp` (gRPC)  | `off`   |

`OTEL_EXPORT=otlp` requires standard OTLP env vars (`OTEL_EXPORTER_OTLP_ENDPOINT`, etc.).

## Usage

### Local

```bash
make run
# or: uv run email-janitor
```

The agent runs in a loop (default 10 seconds between runs). Press `Ctrl+C` to stop.

### Docker

Build and run with Docker Compose:

```bash
docker compose up
```

Or build the image directly:

```bash
make docker-build                                        # image=email-janitor:latest
make docker-build IMAGE=ghcr.io/you/email-janitor TAG=1.0.0
```

Push to a registry:

```bash
make docker-push IMAGE=ghcr.io/you/email-janitor TAG=1.0.0
```

## Architecture

The root agent is a **SequentialAgent** pipeline:

1. **EmailCollectorAgent**: fetches unread emails from Gmail (inbox, excluding sent and already
   processed) and stores results in session state.
2. **EmailClassifierLoopAgent**: a `LoopAgent` that classifies emails one-by-one. On each
   iteration, `EmailClassifierAgent`:
   - Checks whether all emails have been classified; escalates to end the loop if so.
   - Delegates to a pre-built `LlmAgent` sub-agent with a dynamic per-email prompt.
   - Accumulates results into session state.
3. **EmailLabelerAgent**: reads all accumulated classifications and applies Gmail labels:
   - `URGENT` → `janitor/urgent`, kept in inbox
   - `PERSONAL` → `janitor/personal`, kept in inbox
   - `INFORMATIONAL` → `janitor/newsletters`, archived
   - `PROMOTIONAL` → `janitor/promotions`, archived
   - `NOISE` → `janitor/noise`, archived
   - Confidence below `EMAIL_CLASSIFIER_CONFIDENCE_THRESHOLD` → `janitor/review`, kept in inbox,
     `status=needs_review` in the database (regardless of predicted category).
   - All emails receive `janitor/done` to prevent reprocessing.
   - Persists run metadata and per-email classifications to SQLite.

```mermaid
flowchart LR
    A[EmailCollectorAgent] --> Loop
    Loop --> C[EmailLabelerAgent]
    subgraph Loop[EmailClassifierLoopAgent]
        D[EmailClassifierAgent] -->|next email| D
    end
```

Configuration lives in [`src/email_janitor/config/`](src/email_janitor/config/) as Pydantic
Settings classes. Agents are defined in [`src/email_janitor/agents/`](src/email_janitor/agents/)
and created via factory functions. The database layer lives in
[`src/email_janitor/database/`](src/email_janitor/database/).

## Database

Each pipeline run is recorded in a local SQLite database (`email_janitor.db` by default) using
[aiosqlite](https://github.com/omnilib/aiosqlite) for non-blocking writes. Three tables are created
automatically:

| Table             | Purpose                                                               |
| ----------------- | --------------------------------------------------------------------- |
| `runs`            | One row per pipeline run (timing, counts, status)                     |
| `classifications` | One row per email processed (classification, reasoning, confidence)   |
| `corrections`     | User-submitted corrections used as few-shot examples                  |

Browse the data with [sqlite-utils](https://sqlite-utils.datasette.io/):

```bash
sqlite-utils tables email_janitor.db
sqlite-utils rows email_janitor.db runs
sqlite-utils rows email_janitor.db classifications --limit 10
```

## Corrections UI

A Streamlit app surfaces classifications from the database for human review and captures
corrections. Corrections are injected into the classifier prompt as few-shot examples on subsequent
runs, so fixing a misclassification once improves future runs.

```bash
make corrections
# or: uv run streamlit run src/email_janitor/corrections/app.py
```

Filters in the sidebar: run selector, category, max confidence, "Hide already corrected", and
"Needs review only" (shows only low-confidence classifications flagged `status=needs_review`).

In Docker, the UI runs as a separate `corrections` service (port 8501) sharing the same SQLite
volume.

## Evaluation

An offline harness scores the classifier against a labeled JSONL dataset. Use it to establish a
baseline before tweaking the prompt or swapping models, then re-run to measure the delta.

```bash
# Seed the dataset from the corrections table (handcrafted cases are preserved)
make eval-seed

# Run the eval (requires Ollama reachable at the configured endpoint)
make eval
# or with options:
uv run python -m email_janitor.eval \
  --dataset tests/eval/golden_emails.jsonl \
  --report-json /tmp/eval.json \
  --progress
```

Output includes per-category precision/recall/F1, a confusion matrix, and a bucketed confidence
calibration table. Pass `--no-few-shot` to disable correction injection (useful for clean baselines)
or `--limit N` for quick smoke checks.

The dataset at [`tests/eval/golden_emails.jsonl`](tests/eval/golden_emails.jsonl) ships with
handcrafted sanity cases and adversarial cases covering prompt injection, instruction-bearing
subjects, fake JSON payloads, spoofed senders, and HTML-only bodies. Correction-seeded cases are
automatically excluded from their own few-shot pool to prevent data leakage during scoring.

## Observability

Logs are emitted as one JSON object per line on stdout. Every line carries at least `ts`, `level`,
`logger`, and `msg`, plus any context the call site attached (`run_id`, `email_id`, `category`,
`confidence`, etc.). Filter with `jq`:

```bash
uv run email-janitor 2>&1 | jq 'select(.msg == "email_classified")'
```

Set `OTEL_EXPORT=console` to also emit OpenTelemetry spans to stdout. Google ADK emits its own
`invoke_agent` and `call_llm` spans automatically once a tracer provider is configured; the
classifier additionally wraps per-email work in a `classify_email` span with `email.id`,
`predicted_category`, `confidence`, and `parse_failed` attributes.

For production, set `OTEL_EXPORT=otlp` and point the standard OTLP environment variables at your
collector.

## Development

```bash
make lint         # ruff check
make format       # ruff format
make test         # pytest
make corrections  # launch the Streamlit corrections UI
make eval         # run the classifier eval harness (requires Ollama)
make eval-seed    # rebuild tests/eval/golden_emails.jsonl from corrections
make clean        # remove .venv, caches
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for a full guide including the classifier-change workflow.

## Troubleshooting

- **Gmail OAuth:** Ensure `client_secret.json` and `gmail_token.json` are valid and not expired.
  Re-run `make auth` if needed.
- **Ollama:** Confirm Ollama is running and the model is available (`ollama pull llama3.1:8b`). If
  classification consistently times out, raise `EMAIL_CLASSIFIER_LLM_TIMEOUT_SECONDS`.
- **Labels:** Labels are created automatically; ensure the Gmail account has permission to manage
  labels.
- **Everything in `janitor/review`:** `EMAIL_CLASSIFIER_CONFIDENCE_THRESHOLD` is too high for your
  model; lower it, or iterate on the prompt with the eval harness.
- **Transient 429 / connection errors:** Gmail calls auto-retry three times with exponential
  backoff. Repeated failures back off the outer poll loop; watch `consecutive_failures` in the
  logs.
- **Debugging a misclassification:** Grep the JSON logs for the email's `email_id`, or set
  `OTEL_EXPORT=console` to see the full span tree including the LLM request/response.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions,
the classifier-change workflow, commit conventions, and PR guidelines.

Bug reports and feature requests go through [GitHub Issues](https://github.com/willdah/email-janitor/issues).

## Security

To report a vulnerability, use GitHub's private vulnerability reporting:
<https://github.com/willdah/email-janitor/security/advisories/new>.

See [SECURITY.md](SECURITY.md) for the full policy and threat model.

## License

MIT. See [LICENSE](LICENSE) for details.
