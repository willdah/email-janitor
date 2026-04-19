# Contributing

Thanks for your interest in Email Janitor! This guide covers how to set up a
development environment, run tests, and submit changes.

## Prerequisites

- **Python** ≥ 3.12
- **uv** — [install here](https://docs.astral.sh/uv/)
- **Ollama** (optional, required only to run the classifier or eval harness)

## Local setup

Clone the repository:

```bash
git clone https://github.com/willdah/email-janitor.git
cd email-janitor
```

Install dependencies with `uv`:

```bash
make install
# or: uv sync --group dev
```

Set up Gmail credentials (one-time):

```bash
make auth
```

This runs the OAuth flow and generates `gmail_token.json`.

## Running the pipeline

```bash
make run
# or: uv run email-janitor
```

The agent runs in a loop (default 10 seconds between runs). Press `Ctrl+C` to stop.

## Running the corrections UI

```bash
make corrections
# or: uv run streamlit run src/email_janitor/corrections/app.py
```

Opens a Streamlit app on `localhost:8501` where you can review and correct
classifications.

## Testing

Run the test suite:

```bash
make test
# or: uv run pytest
```

Tests live in [`tests/`](tests/). Use `pytest -v` for verbose output,
`pytest -k "pattern"` to run a subset.

## Code quality

Check code with Ruff:

```bash
make lint
# or: uv run ruff check .
```

Auto-format code:

```bash
make format
# or: uv run ruff format .
```

Email Janitor uses Ruff's E/F/I/UP rules at 120-char line length (see
[`pyproject.toml`](pyproject.toml)).

## Evaluating the classifier

The offline eval harness lets you measure classifier accuracy before and after
changes. It runs against a golden JSONL dataset and produces per-category
metrics, a confusion matrix, and confidence calibration.

### First run

Seed the golden dataset from the corrections table (handcrafted cases are
preserved):

```bash
make eval-seed
# or: uv run python -m email_janitor.eval.seed_golden --db email_janitor.db
```

This populates [`tests/eval/golden_emails.jsonl`](tests/eval/golden_emails.jsonl).

### Run eval

```bash
make eval
# or: uv run python -m email_janitor.eval --progress
```

Pass `--dataset` to use a custom file, `--report-json /tmp/eval.json` to save
detailed metrics, `--no-few-shot` to disable correction injection, or `--limit N`
for quick smoke checks.

The output includes precision/recall/F1 per category, a confusion matrix, and
a bucketed confidence-calibration table.

### Classifier changes

If you modify the prompt or swap the model:

1. Run the eval harness before your change: `make eval --report-json /tmp/before.json`
2. Make your change.
3. Run the eval harness after: `make eval --report-json /tmp/after.json`
4. Include the metrics diff (or both JSON files) in your PR description.

This helps reviewers understand the impact on classification quality.

## Commits & pull requests

### Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add low-confidence review routing
fix: handle HTML email bodies correctly
docs: clarify Gmail credentials setup
test: add adversarial cases for prompt injection
ci: publish Docker image to GHCR
```

This helps maintainers track changes and generate release notes.

### Pull requests

1. Fork the repository.
2. Create a branch: `git checkout -b fix/my-fix` or `git checkout -b feat/my-feature`.
3. Make your changes.
4. Commit and push: `git push origin fix/my-fix`.
5. Open a pull request and fill out the template.

**What a good PR includes:**

- A clear summary of what changed and why.
- Evidence that you tested it:
  - `make lint` and `make test` both pass.
  - For classifier changes, include eval metrics (`--report-json`).
  - For UI changes, describe what you tested manually.
- Links to related issues (if any).
- A checklist confirming that tests pass, code is clean, and docs are updated.

## Project structure

```
src/email_janitor/
├── agents/           # ADK agents (collector, classifier, labeler)
├── config/           # Pydantic Settings (app, classifier, gmail, database)
├── database/         # SQLite layer (aiosqlite)
├── corrections/      # Streamlit UI
├── eval/             # Offline eval harness and dataset seeder
├── instructions/     # Prompt templates
├── observability/    # Logging and tracing
├── utils/            # Helpers (HTML stripping, retry logic)
└── main.py           # Entry point
```

## Troubleshooting

**Tests fail with import errors.** Run `make install` to ensure all dependencies
are present.

**Classifier times out.** Ensure Ollama is running and the model is pulled:
`ollama pull llama3.1:8b`. If it's consistently slow, raise
`EMAIL_CLASSIFIER_LLM_TIMEOUT_SECONDS`.

**Eval harness fails.** Same as above — Ollama must be running. For quick checks,
use `--limit 5` to test only five cases.

## Questions?

Open an issue or start a discussion in [GitHub Discussions](https://github.com/willdah/email-janitor/discussions).
