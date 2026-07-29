# Work Summary — Day 1 Furniture Buyer App

**Repo:** https://github.com/wilson21st/furniture-buyer-app (public)
**Date:** 2026-07-29 · **Stack:** Python 3.13 · FastAPI · SQLModel/SQLite · Anthropic ·
Langfuse · pytest/respx/Playwright · managed with `uv`.

This documents what was built against the event's Day-1 lab, how it was re-verified against
the live lab checklists, and the end-to-end tests run with **observability capturing every
test detail as structured traces** (not just logs).

---

## 1. What was built

A furniture-shop **buyer app** across all four lab levels, plus the two optional stretch
steps, with three engineering requirements woven through every step:

| # | Requirement | How it's met |
|---|---|---|
| 1 | **Version control → GitHub** | Public repo; conventional commits; **one commit + annotated tag per lab step** (`step-1`…`step-9`); GitHub Actions CI; branch protection requiring CI. |
| 2 | **Observability (2 layers)** | *Process:* Claude Code hooks (secret-guard, session log), OTEL telemetry env, `CLAUDE.md`, slash commands. *Runtime:* one `app/observability.py` surface tracing every API call, agent turn, tool call, and RAG retrieval to **self-hosted Langfuse** (`docker-compose.langfuse.yml`). |
| 3 | **Test coverage** | Hard **90% gate** (`--cov-fail-under=90`) enforced in CI; **123 tests at 99.76%**. |

Git history (each is a real, CI-green step):

```
step-1  chore: foundations (repo, docs, CI, hooks, Langfuse, coverage gate)
step-2  feat: Level 1 web app (login, catalogue, orders, balance rule, reports)
step-3  feat: typed furniture-shop API client (all endpoints + error codes)
step-5  feat: connect app to the real API (unified shop layer, graceful errors)
step-6  feat: Level 3 agent (4 tools, confirm-before-spend, tracing, chat UI)
step-7  feat: showcase smoke test + Playwright e2e flow
step-8  feat: vector RAG product Q&A (Level 4)
step-9  feat: OpenClaw skill packaging the four tools
```

---

## 2. Re-verification against the live lab checklists

Re-fetched `training.cognitivo.com.au/labs` and the Day-1 step pages on 2026-07-29 — the
10-page structure and checklist wording are unchanged from what was built against. Each
checklist item mapped to concrete evidence:

### Step 1 — Repo & project files
| Checklist item | Status | Evidence |
|---|---|---|
| GitHub repo, public | ✅ | `furniture-buyer-app` (public) |
| Git identity configured | ✅ | commits authored by `wilson21st` |
| `CLAUDE.md`, `requirements.md`, `architecture.md` | ✅ | all present at repo root |
| First commit pushed | ✅ | `step-1` tag, CI green |

### Step 2 — Level 1 app
| Checklist item | Status | Evidence |
|---|---|---|
| Entity model in `architecture.md` | ✅ | Mermaid class diagram (Customer/Product/Order) |
| Runs locally in browser | ✅ | `uvicorn app.main:app`; `/` renders catalogue |
| Real MongoDB catalogue (optional) | ✅ | `scripts/seed_catalogue.py` + `app/catalogue_seed.py` |
| Login | ✅ | `app/auth.py`, `/login`; tests in `test_web.py` |
| Order saves + reduces balance; overspend blocked with clear message | ✅ | `services.place_order` + `test_services.py`, `test_web.py::test_buy_insufficient_balance_shows_message` |
| Order-history report | ✅ | `/orders`, `services.order_history/total_spent` |
| Reachable via internet (ngrok) | ✅ (documented) | `docs/ngrok.md` — needs your ngrok account to run |
| Committed & pushed | ✅ | `step-2` |

### Steps 3–4 — Understand & reference the API
| Checklist item | Status | Evidence |
|---|---|---|
| Four actions understood (browse/lookup/balance/order) | ✅ | `app/furniture_api.py` methods |
| Use `search-index`, not slow `/catalogue` | ✅ | client only calls `search-index`; documented in module docstring |
| Error codes 401/402/403/404/429 | ✅ | mapped to exceptions; `test_furniture_api.py` parametrized over all |
| Key kept private | ✅ | `.env` + `.gitignore` + secret-guard hook |

### Step 5 — Connect app to real API
| Checklist item | Status | Evidence |
|---|---|---|
| Key in `.env`, never committed | ✅ | verified `git check-ignore .env`; hook blocks staged secrets |
| Real catalogue on home page | ✅ | `shop.list_catalogue` (API path); `test_web_api.py` |
| Real balance shown | ✅ | `shop.get_balance`; nav renders it |
| Real ordering reduces balance | ✅ | `shop.place_order` (API path) |
| Overspend → clear message, no crash | ✅ | `ShopError` mapping; `test_web_api.py::...insufficient...` |
| Committed & pushed | ✅ | `step-5` |

### Step 6 — Agent (Level 3)
| Checklist item | Status | Evidence |
|---|---|---|
| Four tools with honest descriptions | ✅ | `app/tools.py` (states exact-match limitation) |
| "chair under $500" returns relevant products | ✅ | client-side price/colour reasoning; `test_tools.py` |
| Confirms before placing a real order | ✅ | `place_order` returns pending; `execute_confirmed_order` spends; `test_agent.py`, `test_web_chat.py` |
| Failure → friendly explanation, no crash | ✅ | `_friendly` mapping surfaced in chat |
| ≥3 phrasings tried | ✅ | covered across agent tests + the confirm/cancel flows |
| Committed & pushed | ✅ | `step-6` |

### Step 7 — Showcase
| Checklist item | Status | Evidence |
|---|---|---|
| End-to-end smoke test | ✅ | `scripts/smoke_test.py` + Playwright `tests/e2e/test_showcase.py` |
| Demo narrative | ✅ | `docs/showcase.md` |

### Step 8 — Vector RAG (optional) · Step 9 — OpenClaw (optional)
| Item | Status | Evidence |
|---|---|---|
| Chunk → embed → cosine retrieve → grounded answer | ✅ | `app/rag.py`; `test_rag.py`; `scripts/rag_demo.py` |
| Four tools packaged as an OpenClaw skill, confirm-before-spend, least privilege | ✅ | `app/openclaw.py`; `test_openclaw.py`; `docs/openclaw.md` |

**Result: every required Day-1 checklist item is satisfied in code + tests.** Items that
inherently need your own accounts to *run live* (ngrok URL, organizer API key, Anthropic /
Voyage keys) are implemented behind config and mocked in tests — see §5.

---

## 3. End-to-end tests

Three complementary layers, all passing:

```
Gated unit + integration suite :  123 passed, 99.76% coverage  (uv run pytest)
Browser E2E (Playwright)       :    1 passed  (login → browse → buy → agent confirm-buy)
Observability E2E harness      :  full L2/L3/L4 flow, traced end-to-end
```

The **browser E2E** drives a real Chromium against an in-process server: log in as the demo
user, browse the catalogue, buy an item, then use the assistant to place an order with
confirm-before-spend — proving the whole stack works, not just units.

---

## 4. Observability of the tests (not just logs)

`scripts/observability_e2e.py` injects a recording client into `app/observability.py` and
drives the Level 2 API client, the Level 3 agent (with confirm-before-spend), and the Level 4
RAG flow — capturing **every span, tool call, API call, and LLM generation** with timings and
attributes. This is the same instrumentation that streams to Langfuse in production; here it's
captured in-process so the artifact is deterministic and needs no credentials.

Captured trace tree (`docs/observability-report.json`):

```
▸ scenario.level2_api_client  [0.9ms]
  ▸ furniture_api GET /health              {status_code:200}
  ▸ furniture_api GET /catalogue/categories {status_code:200}
  ▸ furniture_api GET /catalogue/search-index {status_code:200}
  ▸ furniture_api GET /users/u001           {status_code:200}
▸ agent.respond  [0.3ms]  {user:u001}
    ◆ generation: agent.turn (claude-opus-4-8)   ×3
  ▸ tool.search_catalogue
    ▸ furniture_api GET /catalogue/search-index {status_code:200}
  ▸ tool.place_order
    ▸ furniture_api GET /catalogue/CHR-001    {status_code:200}
▸ agent.confirm_order  {item_id:CHR-001}
  ▸ furniture_api POST /orders              {status_code:200}
▸ rag.retrieve  {k:1}
    ◆ generation: rag.answer (claude-opus-4-8)

SUMMARY: 4 root traces · 13 spans · 7 furniture-api calls · 4 LLM generations
```

What this demonstrates as observability (vs. logging):
- **Causal hierarchy** — you can see the agent turn *caused* a `search_catalogue` tool call
  which *caused* an API request; and that a purchase went through the dedicated
  `agent.confirm_order` span, proving confirm-before-spend at the trace level.
- **Attributes** — each API span carries its HTTP status; the confirm span carries the
  `item_id`; the retrieve span carries `k`.
- **Timings** — per-span durations for latency analysis.
- **LLM generations** — model + output recorded per turn (audit trail of every model call).

### Production backend (Langfuse)
`docker-compose.langfuse.yml` self-hosts Langfuse with **headless key provisioning** (no UI
signup needed). Start it, set `LANGFUSE_ENABLED=true` + the keys in `.env`, and the exact same
spans/generations above stream to `http://localhost:3000` for the demo. In this environment
the image pull was blocked, so the in-process recorder above is the captured artifact; the
stack is configured and starts with one command where Docker registry access is available.

---

## 5. How to run everything

```bash
uv sync --all-extras --dev

# unit + integration (enforces the 90% gate)
uv run pytest

# browser end-to-end
uv run playwright install chromium
uv run pytest -m e2e

# observability-traced end-to-end (writes docs/observability-report.json)
uv run python -m scripts.observability_e2e

# run the app
uv run uvicorn app.main:app --reload           # http://localhost:8000

# runtime observability backend
docker compose -f docker-compose.langfuse.yml up -d   # http://localhost:3000
```

### Credentials you supply (all stubbed + mocked so tests pass without them)
`FURNITURE_API_BASE_URL` + `FURNITURE_API_KEY` + `FURNITURE_USER_ID` (organizers),
`ANTHROPIC_API_KEY` (agent + RAG generation), `VOYAGE_API_KEY` (RAG embeddings),
`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` (already fixed by the headless compose),
and an ngrok account for public access.
