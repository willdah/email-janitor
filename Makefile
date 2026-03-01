IMAGE ?= willahern/email-janitor
TAG ?= latest

.PHONY: install run corrections lint format test clean auth docker-build docker-push

install:
	uv sync --group dev

run:
	uv run email-janitor

corrections:
	uv run streamlit run src/email_janitor/corrections/app.py

lint:
	uv run ruff check .

format:
	uv run ruff format .

test:
	uv run pytest

clean:
	rm -rf .venv __pycache__ .ruff_cache

auth:
	uv run python gmail_auth.py

docker-build:
	docker build --platform linux/amd64 -t $(IMAGE):$(TAG) .

docker-push:
	docker push $(IMAGE):$(TAG)
