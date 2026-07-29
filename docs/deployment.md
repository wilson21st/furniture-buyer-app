# Deployment

The app is a standard FastAPI (ASGI) service, packaged as a container (`Dockerfile`,
verified building + serving locally). Primary target: **Fly.io** with a persistent volume
for SQLite. GitHub hosts the code, image build, CI, and the deploy trigger.

## What can / can't host it
| Target | Works? | Notes |
|---|---|---|
| GitHub **Pages** | ❌ | static only — cannot run a Python server/DB/agent |
| GitHub **Codespaces** | ✅ (demo) | run + forward a public port; not durable |
| GitHub **Actions + GHCR** | ✅ | build/test/publish image + trigger deploy (host is external) |
| **Fly.io** | ✅ (recommended) | Docker + persistent volume for SQLite |
| Render / Railway | ✅ | PaaS; add a persistent disk for SQLite |
| Google Cloud Run | ✅ | serverless; use Postgres (filesystem is ephemeral) |
| **ngrok** | ✅ (temporary) | tunnels your laptop — best for the hackathon showcase (see `ngrok.md`) |

## Deploy to Fly.io (manual, first time)
```bash
# 1. Install + log in
brew install flyctl          # or: curl -L https://fly.io/install.sh | sh
fly auth login

# 2. Create the app (pick a globally-unique name; update `app` in fly.toml to match)
fly apps create furniture-buyer-app     # or: fly launch --no-deploy --copy-config

# 3. Persistent disk for the SQLite database (mounted at /data via fly.toml)
fly volumes create data --region syd --size 1

# 4. Secrets (never put these in fly.toml or git)
fly secrets set APP_SECRET_KEY="$(openssl rand -hex 32)"
# optional — enable the real API + agent + RAG + tracing:
fly secrets set USE_REAL_API=true FURNITURE_API_KEY=... FURNITURE_USER_ID=u001
fly secrets set ANTHROPIC_API_KEY=... VOYAGE_API_KEY=...
fly secrets set LANGFUSE_ENABLED=true LANGFUSE_HOST=... \
                LANGFUSE_PUBLIC_KEY=... LANGFUSE_SECRET_KEY=...

# 5. Ship it
fly deploy
fly open        # opens the public https URL
```

## Continuous deploy (GitHub Actions)
`.github/workflows/deploy.yml` deploys **only after the CI workflow passes on `main`**.
Enable it once:
```bash
fly tokens create deploy -x 999999h     # prints a token
gh secret set FLY_API_TOKEN --body "<that token>"
```
After that, every green push to `main` auto-deploys.

## Notes on state
- **SQLite** lives on the Fly volume at `/data/app.db` and survives redeploys. Fine for a
  single machine. If you scale to multiple machines, move to Postgres and set `DATABASE_URL`.
- The **chat history** store is in-memory per process (fine for a demo; would move to
  Redis/DB for multi-instance).
- **Langfuse**: point the app at Langfuse Cloud, or deploy the `docker-compose.langfuse.yml`
  stack on a VPS and set the `LANGFUSE_*` secrets.

## Local container (any host / Codespaces)
```bash
docker build -t furniture-buyer .
docker run -p 8080:8080 -e APP_SECRET_KEY=dev -v $(pwd)/data:/data furniture-buyer
# http://localhost:8080
```
