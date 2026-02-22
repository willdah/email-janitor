# --- Stage 1: Builder ---
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

# Set the working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Install dependencies first (leverage Docker caching)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Copy source and install the project itself
COPY README.md README.md
COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev

# --- Stage 2: Final Image ---
FROM python:3.12-slim-bookworm

WORKDIR /app

# Copy the venv from the builder (includes installed project)
COPY --from=builder /app/.venv /app/.venv

# Place the venv at the front of the PATH
ENV PATH="/app/.venv/bin:$PATH"
