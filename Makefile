.PHONY: auth venv

auth:
	python gmail_auth.py

venv:
	uv sync --all-extras