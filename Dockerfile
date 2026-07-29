# Production image for the furniture-buyer FastAPI app.
# Multi-stage: build the locked venv with uv, then copy it into a slim runtime.

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# Install only runtime deps (no dev group), using the lockfile for reproducibility.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DATABASE_URL="sqlite:////data/app.db"
# Prebuilt virtualenv from the builder stage.
COPY --from=builder /app/.venv /app/.venv
# Application code (templates travel with the package).
COPY app ./app
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
