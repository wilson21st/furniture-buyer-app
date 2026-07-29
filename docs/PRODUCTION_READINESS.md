# Production-Readiness & Repo Cleanup Plan

> Status: **partially implemented** on branch `refactor/production-readiness`. This
> documents what it takes to move the Day-1 hackathon repo from "demo-complete" to
> "production-ready", plus a repo tidy-up pass. Ordered by priority.
>
> Legend: **P0** = do before any real deployment · **P1** = important, soon after ·
> **P2** = nice-to-have / polish.

## Implementation status (this branch)

**Done ✅**
- Audit fixes: shared `app/llm.py` (R1/R2), `shop._to_view` (R3), dropped dead coverage
  `omit` (R4), pinned `langfuse>=4,<5` (S4), added `USE_REAL_API` + hardening vars to
  `.env.example` (C1), renamed `LocalInsufficientBalanceError` (C2), reconciled entity
  diagram (S1) and PLAN layout note (S2).
- Security: prod fail-fast config validation (2.1/2.3/5.1), secure session cookies (2.2),
  `TrustedHostMiddleware` + optional HTTPS redirect (2.4), in-process rate limiter on
  spend routes (2.6), flag-gated demo seeding (2.3), `SECURITY.md` (2.8).
- Ops: structured JSON request logging (4.2), `/ready` DB probe (4.4), Docker non-root
  user + `HEALTHCHECK` (4.5).
- CI/hygiene: `ruff format --check`, `pip-audit`, `bandit` (5.3/5.4), Dependabot (5.2),
  `LICENSE`/`CONTRIBUTING.md`/`CODEOWNERS` (7.1/7.2), `.gitignore` additions (1.4).
- Tests: full coverage of all new code; suite at **100%**, gate ratcheted **90 → 95%**.

**Deferred (documented, not done) ⏭️**
- **Postgres + Alembic (§3.1/3.2)** — infra decision; SQLite single-instance constraint
  is documented instead. Do this only when it becomes a real multi-user service.
- **Sentry / error tracking (§4.3)** — external service; wire when a hosting target exists.
- **Test dir reorg + services/shop dedup (§6.1/6.2)** — cosmetic; deferred to avoid churn.
- **Moving `requirements.md`/`architecture.md` under `docs/` (§1.5/1.6)** — high link-churn,
  low value; PLAN now documents the as-built root location instead.
- **GitHub branch protection (§7.4)** — a repo setting, not code; enable in repo settings.
- Root demo-PNG duplicates + `.capture/` (§1.1/1.2) are now git-ignored; delete at will.

---

## 0. Snapshot of current state

- ✅ App works end-to-end across L1–L4; 125 tests, 99.5% coverage, hard 90% CI gate.
- ✅ Secret hygiene: `.env` git-ignored, pre-commit secret-scan hook, keys via typed config.
- ✅ Containerised (`Dockerfile`), Fly.io config, CI + deploy workflows, self-host Langfuse.
- ⚠️ Root is cluttered with demo artifacts; tests are flat; several prod hardening gaps.

---

## 1. Repo hygiene / cleanup (fast wins)

| # | Item | Prio | Action |
|---|------|------|--------|
| 1.1 | Stray demo PNGs at repo root (`review-1..5-*.png`, `lf-traces.png`, `lf-trace-detail.png`) | P1 | Canonical copies already live in `docs/screenshots/`. Delete the root duplicates; keep only `docs/screenshots/`. |
| 1.2 | Untracked `.capture/` dir | P1 | Confirm throwaway, then delete and add to `.gitignore`. |
| 1.3 | `docs/observability-report.json` modified & uncommitted, and it's a generated data artifact living under `docs/` | P1 | Decide: commit final version, or move generated reports to a git-ignored `artifacts/` dir and keep only a narrative in docs. |
| 1.4 | `.gitignore` misses `.capture/`, `.playwright-mcp/`, `.claude/session.log` | P2 | Add them so `git status` stays clean. |
| 1.5 | Doc-location inconsistency: `requirements.md` + `architecture.md` at root, but `PLAN.md §2.1` says they belong under `docs/` | P2 | Pick one. Recommend moving both under `docs/` and fixing links in `README.md` / `CLAUDE.md`. |
| 1.6 | Hackathon-only docs mixed with product docs (`WORK_SUMMARY.md`, `showcase.md`, `PLAN.md`, `ngrok.md`, `openclaw.md`) | P2 | Move Day-1 narrative docs into `docs/hackathon/` (archive) so `docs/` reads as product documentation. |

---

## 2. Security & auth hardening (P0 — required for real deployment)

| # | Item | Action |
|---|------|--------|
| 2.1 | **Insecure default secret** — `app_secret_key` defaults to `"dev-insecure-secret-change-me"` (`config.py:20`); session cookies are signed with it | Fail fast: in a `prod`/live env, raise at startup if `APP_SECRET_KEY` is unset or equals the default. Add a `Settings` validator. |
| 2.2 | **Session cookie flags** — `SessionMiddleware` (`main.py:95`) is added with no `https_only`/`same_site` | Set `https_only=True, same_site="lax"` (or `strict`) in non-dev environments. |
| 2.3 | **Seeded demo user with known password** (`services.py` `DEMO_USER_ID`/`DEMO_PASSWORD`) | Gate demo seeding behind a `SEED_DEMO_USER` flag that defaults **off** outside dev. Never seed a known-credential user in prod. |
| 2.4 | **No host allow-listing / HTTPS redirect** | Add Starlette `TrustedHostMiddleware` (allowed hosts from env) and `HTTPSRedirectMiddleware` behind the proxy. |
| 2.5 | **No CORS policy** | If any browser client is cross-origin, add an explicit `CORSMiddleware` allow-list; otherwise document that same-origin is intended. |
| 2.6 | **No rate limiting** — the `/chat` agent endpoint can drive real LLM spend and real orders | Add per-session/IP rate limiting (e.g. `slowapi`) on `/chat` and `/orders`. |
| 2.7 | **`.claude/settings.json` uses `bypassPermissions`** | Dev-harness setting, not shipped — but note it so it isn't copied into any shared/CI Claude config. |
| 2.8 | Add a **`SECURITY.md`** (how to report vulns) — the repo is public | Standard OSS hygiene. |

---

## 3. Data & persistence (P0/P1)

| # | Item | Prio | Action |
|---|------|------|--------|
| 3.1 | **SQLite on a single Fly volume** — no horizontal scaling, locking under concurrency, backup story is "copy the file" | P1 | For real prod, move to **Postgres** (managed). Keep SQLite as the local/dev default via `DATABASE_URL`. SQLModel already abstracts this. |
| 3.2 | **No migrations** — schema created via `SQLModel.create_all()` | P0-if-Postgres | Add **Alembic**. `create_all` silently ignores column changes; you'll lose/corrupt data on the first model change in prod. |
| 3.3 | **No backup/restore doc** | P2 | Document backups (Postgres automated snapshots, or Fly volume snapshot cadence if staying on SQLite). |
| 3.4 | **In-memory chat history per process** (noted in `deployment.md`) | P1 | Fine for single instance; move to Redis/DB if scaling to >1 instance. |

---

## 4. Observability & operations (P1)

| # | Item | Action |
|---|------|--------|
| 4.1 | **`langfuse>=2.53` floor allows v2, but code targets v4** (`observability.py` branches on v4 APIs) | Pin to a tested major range (e.g. `langfuse>=3,<5` or exact v4 range). Loose floors risk an untested SDK at deploy. |
| 4.2 | **No structured application logging** — only `/health` and Langfuse (LLM-only) | Add structured JSON logging (request id, user, latency, status) via `logging`/`structlog`. Langfuse traces LLM calls, not ordinary errors/requests. |
| 4.3 | **No general error tracking** | Consider Sentry (or equivalent) for unhandled exceptions — Langfuse won't catch non-LLM 500s. |
| 4.4 | **Health check is liveness-only** | Add a `/ready` that checks DB connectivity (and optionally the shop API) so orchestrators don't route to a broken instance. |
| 4.5 | **Dockerfile has no `HEALTHCHECK`, runs as root** | Add `HEALTHCHECK` hitting `/health`; add a non-root `USER`. |

---

## 5. Config & dependency management (P1/P2)

| # | Item | Prio | Action |
|---|------|------|--------|
| 5.1 | **Required-secret validation** — app boots with empty keys (great for tests, risky for prod) | P1 | When `USE_REAL_API=true` or `env=prod`, validate that the corresponding keys are present at startup; fail fast with a clear message. |
| 5.2 | Dependency **floors (`>=`) not pinned** — `uv.lock` gives reproducibility, but floors invite drift | P2 | Keep floors; rely on `uv.lock` in CI/Docker (already `--frozen`). Add **Dependabot/Renovate** for controlled bumps. |
| 5.3 | **Security scanning** absent | P2 | Add `pip-audit` (deps) and `bandit`/`ruff` security rules to CI. |
| 5.4 | **`ruff format` not enforced** — only `ruff check` in CI | P2 | Add `ruff format --check` to CI for consistent style. |

---

## 6. Testing structure (P2 — quality, not correctness)

| # | Item | Action |
|---|------|--------|
| 6.1 | Tests are **flat** in `tests/`; `PLAN.md §2.1` promised `unit/ integration/ e2e/` split | Reorganise into `tests/unit`, `tests/integration`, `tests/e2e` (e2e dir already exists). Cosmetic; helps navigation and selective runs. |
| 6.2 | **Two overlapping domain layers** — `services.py` (L1) and `shop.py` (unified) | Review for duplication; consider `shop.py` as the single façade and `services.py` as pure L1 internals, with clear boundaries documented. |
| 6.3 | Coverage config omits only `__main__.py` | Fine. Keep the 90% gate; consider raising the ratchet toward the current 99% to prevent silent erosion. |

---

## 7. Standard OSS / repo files (P1)

| # | Item | Action |
|---|------|--------|
| 7.1 | **No `LICENSE`** on a public repo | Add one (MIT/Apache-2.0). Without it, "public" ≠ "reusable" and contribution rights are ambiguous. |
| 7.2 | No `CONTRIBUTING.md`, `CODEOWNERS` | Add if others will contribute; otherwise P2. |
| 7.3 | No `CHANGELOG.md` | The `step-*` tags + conventional commits already form a log; a generated CHANGELOG is optional polish. |
| 7.4 | **Branch protection** on `main` (PLAN §3.3 intends it) | Verify it's actually enabled on GitHub: require PR + passing CI before merge. |

---

## Suggested sequencing

1. **Cleanup pass** (§1) + **LICENSE/SECURITY.md** (§7.1, 2.8) — low risk, immediate tidiness. One commit.
2. **Security hardening** (§2) + **config fail-fast** (§5.1) — the real blockers for exposing it publicly.
3. **Persistence** (§3: Postgres + Alembic) — only if this becomes a genuinely multi-user/prod service; otherwise document the single-instance SQLite constraint explicitly.
4. **Observability/ops** (§4) and **CI enhancements** (§5.2–5.4).
5. **Test restructure + layer dedup** (§6) — quality polish, no behaviour change.

Each of the above maps cleanly to one PR with its own tests, keeping the 90% gate green.

---

## 8. Audit findings — consistency, redundancy, staleness

> Full read of every `app/` module. **No correctness bugs found** — the app boots (16
> routes), tests are green, and patterns are coherent. The items below are convention
> drift, DRY, and doc-vs-code staleness. Prio as before.

### 8.0 What's already consistent (keep doing this)
- Every module opens with a docstring stating **purpose + design rationale**.
- `from __future__ import annotations` everywhere; consistent snake_case.
- Single cached settings singleton (`get_settings()`); **nothing reads `os.environ` directly**.
- Uniform **factory-injection** for external clients (`set_llm_factory`, `set_embedder_factory`, `set_client`) so tests inject fakes.
- Layered **error taxonomy**: `ApiError` (transport) → `ServiceError` (L1 domain) → `ShopError` (façade), translated in one place (`shop._friendly()`).
- Consistent split: Pydantic `BaseModel` for external API shapes vs dataclasses for internal view models.

### 8.1 Inconsistencies (P1/P2)
| # | Finding | Location | Prio |
|---|---------|----------|------|
| C1 | **`USE_REAL_API` missing from `.env.example`** — yet it is the master L1↔L2 toggle. Every other setting is documented; the most important switch is not. | `.env.example` vs `config.py:30` | P1 |
| C2 | Two classes named `InsufficientBalanceError` (per-layer, intentional, both handled in `_friendly`) — name collision is an import foot-gun. Consider `ApiInsufficientBalanceError` vs `LocalInsufficientBalanceError`. | `services.py:26`, `furniture_api.py:81` | P2 |

### 8.2 Redundancy (P2)
| # | Finding | Location |
|---|---------|----------|
| R1 | `_extract_text()` implemented twice (join text blocks from a Claude response). Extract one shared helper. | `agent.py:78` & `rag.py:151` |
| R2 | `default_llm` ≈ `default_rag_llm` (near-identical Anthropic wrapper); `LLM` Protocol declared twice. Share one Anthropic-client factory. | `agent.py:50` & `rag.py:60` |
| R3 | `ProductView(...)` constructed 4× with identical field order; add a `_to_view(p)` helper. | `shop.py:57,62,82,86` |
| R4 | Dead coverage config: `omit = ["app/__main__.py"]` but the file does not exist. | `pyproject.toml:50` |

### 8.3 Staleness / out-of-date (P1 — these actively mislead a reader)
| # | Finding | Impact |
|---|---------|--------|
| S1 | **Entity diagrams describe fields never built.** `architecture.md` & `PLAN.md §2.3` show `Customer.external_user_id`/`remaining_balance`, `Product.colour_count/link/depth/height/width/image_mime_type`, `Order.order_id/remaining_balance_after`. As-built `models.py` is far slimmer. Reconcile the diagrams to as-built (or note them as target schema). **Highest-value doc fix.** |
| S2 | `PLAN.md §2.1` repo layout is stale: shows `tests/unit\|integration\|e2e` (tests are flat) and `scripts/check_secrets.py` (doesn't exist — the hook is `guard-commit.sh`). |
| S3 | `image_url` is stored (`models.py:34`, `catalogue_seed.py:39`) but **dropped** from `shop.ProductView`, so no UI/agent path uses it. Either wire it into the catalogue view or drop the field. |
| S4 | `langfuse>=2.53` floor vs v4-targeting code (`observability.py`). A fresh install could pull an untested SDK. (Also §4.1.) |
| S5 | `docs/observability-report.json` modified-uncommitted (also §1.3). |

### 8.4 Highest-value fixes from this audit
1. **S1** — reconcile the entity diagrams with the as-built models (most misleading).
2. **C1** — add `USE_REAL_API` to `.env.example`.
3. **S2** — correct the `PLAN.md` layout section (or mark it as target-state).

These are documentation/quality only and can ride along with the §1 cleanup PR.
