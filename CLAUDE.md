# CLAUDE.md — standing instructions for this project

This file is read automatically at the start of every Claude Code session. It is the
project's contract. Keep it short and update it whenever we agree a new standing rule.

## What this project is
A **buyer's web app for a furniture shop**, built for Day 1 of the AI Training Hackathon.
A user logs in, browses a real catalogue, sees their balance, and places orders against a
budget. Later levels add an AI agent that fulfils plain-English requests, and an optional
RAG Q&A bot. See `requirements.md` (what) and `architecture.md` (how).

## Non-negotiable rules
1. **Secrets never get committed.** All keys live in `.env` (git-ignored). The repo is
   public. Never hardcode a key, and run `git status` before every commit. A pre-commit
   hook blocks staged secrets — do not bypass it.
2. **Every new LLM call must be traced with Langfuse.** Wrap agent turns, tool calls,
   embeddings, and generations via `app/observability.py`. No un-observed model calls.
3. **Tests + coverage must pass before every commit.** Hard gate: `--cov-fail-under=90`.
   Coverage may never regress. New code ships with its tests in the same commit.
4. **Plan before building.** For any non-trivial change, state the plan in plain English
   first, then implement. Keep instructions small — one clear change at a time.
5. **Conventional commits, one commit + annotated tag per lab step** (`step-1` … `step-9`).

## How we work
- Python + FastAPI + SQLModel/SQLite, managed with `uv`. Anthropic SDK for the agent,
  Langfuse for runtime observability, `pytest`/`respx`/`pytest-playwright` for tests.
- Describe goals, not implementations. Check results by actually running the app.
- The external furniture API does **exact, case-insensitive category matching only** — any
  "cheap"/colour/vibe reasoning happens in our code, never assumed of the API.
- `POST /orders` spends a real event balance. The agent must confirm before spending.

## Commands
- `uv run pytest` — unit + integration, with the 90% gate.
- `uv run pytest -m e2e` — Playwright end-to-end (needs a running server).
- `uv run pytest -m live` — tests that hit real external services (needs creds).
- `uv run uvicorn app.main:app --reload` — run the app.
- `docker compose -f docker-compose.langfuse.yml up -d` — start local Langfuse.
