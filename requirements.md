# requirements.md — what the app must do

Plain-English requirements, ordered by the lab's levels. Each maps to acceptance tests.

## Level 1 — a normal web app (Step 2)
- **Entity model**: `Customer`, `Product`, `Order` (see `architecture.md`).
- **Web UI**: browsable pages (home/catalogue, login, order history).
- **Login**: distinguish one user from another; session-based.
- **Persistence**: users and orders survive a restart (SQLite).
- **Workflow rule**: a user cannot place an order that costs more than their remaining
  balance — show a clear message, never crash.
- **Report**: a logged-in user can see their own past orders and total spent.
- **Reachable via the internet**: runnable behind an ngrok tunnel.

## Level 2 — talk to the external furniture API (Steps 3–5)
- Browse the **real catalogue** via `GET /catalogue/search-index` (never the slow
  `/catalogue`).
- Show the user's **real balance** from `GET /users/{id}`.
- Place **real orders** via `POST /orders`, then show confirmation + updated balance.
- Handle every error gracefully: 401/403 (auth), 404 (unknown), 402 (insufficient
  balance), 429 (rate limit → back off using `Retry-After`).
- The API key lives only in `.env`.

## Level 3 — an agent (Step 6)
- A text box takes a plain-English request.
- Four tools: `search_catalogue`, `get_product`, `check_balance`, `place_order`.
- The agent does the fuzzy reasoning ("cheap", colour) the API cannot.
- **Confirm before spending**: never call `place_order` without user confirmation.
- Failures come back as a normal conversational reply, not a raw error.

## Level 4 — vector RAG Q&A (Step 8, optional)
- Answer open-ended catalogue questions by embedding + cosine-similarity retrieval over
  per-product chunks, then generating an answer grounded in retrieved products.

## Cross-cutting (all steps)
- **Version control**: every step committed and pushed to a public GitHub repo, tagged.
- **Process observability**: Claude Code telemetry + hooks + standing rules (`CLAUDE.md`).
- **Runtime observability**: Langfuse traces for all model/tool/retrieval activity.
- **Test coverage**: hard 90% gate, never regressing.
