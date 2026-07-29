# Contributing

Thanks for your interest. This repo follows a small, strict set of conventions
(see `CLAUDE.md` for the full contract).

## Setup

```bash
uv sync --all-extras --dev
cp .env.example .env   # fill in values as needed
```

## Before every commit

1. **Tests + coverage must pass.** The gate is hard: `uv run pytest` enforces
   `--cov-fail-under=95`. New code ships with its tests in the same commit.
2. **Lint + format clean.** `uv run ruff check .` and `uv run ruff format --check .`.
3. **No secrets staged.** `.env` is git-ignored; a pre-commit hook blocks accidental
   secrets. Never bypass it.

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
uv run pytest -m e2e --no-cov   # Playwright end-to-end (needs: uv run playwright install chromium)
```

## Conventions

- **Conventional commits** (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `ci:`).
- Keep changes small and described in plain English first (plan before build).
- Every new LLM/tool/embedding call must be traced via `app/observability.py`.
- External dependencies stay behind `app/config.py` flags and are mocked in tests,
  so the suite is green without live credentials.

## Pull requests

Open a PR against `main`. CI (lint, format, security scan, tests + coverage) must be
green before merge.
