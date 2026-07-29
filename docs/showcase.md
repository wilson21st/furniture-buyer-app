# Showcase checklist & demo script (Step 7)

## Pre-demo smoke test
Run these right before the showcase, on the **public** URL if you have one:

```bash
# 1. Automated smoke test against the public URL
uv run python -m scripts.smoke_test https://<your-id>.ngrok-free.app

# 2. (optional) full browser flow locally
uv run playwright install chromium   # first time only
uv run pytest -m e2e
```

Manual pass, in order (mirrors `scripts/smoke_test.py` + the e2e test):
- [ ] Open the app fresh at its public address.
- [ ] Log in as `u001` / `demo1234`.
- [ ] Catalogue shows real products; balance looks right.
- [ ] Ask the assistant "find me a chair under $500" → sensible real response.
- [ ] Ask it to buy something → it **confirms before spending**, then the order goes
      through and the balance updates.
- [ ] Try one thing that should fail (overspend / unknown item) → clear message, no crash.
- [ ] ngrok tunnel + app both still running in terminals you won't close.

## What to say (≈2 minutes)
1. **Problem, one sentence:** "I built an app that lets someone shop a furniture
   catalogue just by describing what they want."
2. **Show, don't tell:** type a real request live and let the agent respond.
3. **One honest limitation:** what you'd improve with another hour.

## Observability angle (our differentiator)
Open the local Langfuse UI (`http://localhost:3000`) during the demo and show a trace:
the `agent.respond` span, each `tool.*` call, the generation, and — for a purchase —
the `agent.confirm_order` span. This makes the agent's decisions auditable, which is
the point of wiring observability through from day one.

## After today
The GitHub repo is the record of the day: commits + `step-1`…`step-9` tags tell the
story, and CI shows every step stayed green at ≥90% coverage.
