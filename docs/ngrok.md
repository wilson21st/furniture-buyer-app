# Making the app reachable from the internet (ngrok)

Level 1 requires the app to be reachable by someone on another network. ngrok gives
your local server a temporary public HTTPS address.

## One-time setup
1. Create a free account at https://ngrok.com and copy your authtoken.
2. Install: `brew install ngrok` (macOS) or see ngrok's docs for Linux/WSL.
3. `ngrok config add-authtoken <your-token>`

## Each session
```bash
# terminal 1 — run the app
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# terminal 2 — expose it
ngrok http 8000
```
ngrok prints a public URL like `https://<random>.ngrok-free.app`. Open it on your phone
over **mobile data** (not Wi-Fi) to prove it's genuinely public, not just localhost.

## Notes
- Keep both terminals open during a demo — closing either drops the tunnel.
- The free URL changes every restart; that's fine for the showcase.
- You'll reuse this same tunnel in Step 6 so the agent-backed app is reachable too.
