# Connect OpenClaw (Step 9, optional)

OpenClaw is a separate, open-source personal AI agent that runs on **your** laptop and
can act through apps you already use — here, WhatsApp — via a skill system. This wires
the furniture-shop tools in as one skill.

> ⚠️ **Safety.** OpenClaw takes real actions on your real machine and your real WhatsApp.
> It is *not* sandboxed like the in-app agent. Grant it **only** this one skill, and
> remember that anything it does is really happening.

## 1. Install OpenClaw
Follow OpenClaw's own quickstart. Ask Claude Code to walk you through it if a step is
unclear.

## 2. Connect WhatsApp
Follow OpenClaw's WhatsApp setup to link your own account. Review what it asks to connect
before approving.

## 3. Register this skill
The skill reuses the exact four tools (and descriptions) from Step 6, so behaviour matches
the in-app agent. The descriptor is produced by `app/openclaw.py`:

```python
from app import openclaw
openclaw.manifest()      # → {name, description, permissions, confirm_before, tools}
openclaw.handle("search_catalogue", {"category": "Chairs"})
openclaw.handle("place_order", {"item_id": "CHR-001", "quantity": 1})  # returns pending
openclaw.confirm_order("CHR-001", 1)                                    # spends (after "yes")
```

Point OpenClaw's skill loader at `manifest()` for the tool schemas and route tool calls to
`handle(...)`. Set `USE_REAL_API=true` and your `.env` credentials so it hits the real shop.

## 4. Confirm-before-spend still applies
`handle("place_order", …)` returns a `pending_order` and does **not** spend. Your OpenClaw
flow must ask for confirmation in WhatsApp, then call `confirm_order(...)` — mirroring the
`confirm_before: ["place_order"]` field in the manifest.

## 5. Try it
Message OpenClaw from WhatsApp: "find me a chair under $500" → it should answer from your
real catalogue and balance.

## Checklist
- [ ] OpenClaw installed and running on your laptop.
- [ ] Connected to your own WhatsApp.
- [ ] Only the furniture-shop skill is granted (least privilege).
- [ ] A real WhatsApp message gets a real, correct response.
