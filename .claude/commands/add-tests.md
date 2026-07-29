---
description: Add or strengthen tests to keep coverage ≥ 90%
---

Add tests for: $ARGUMENTS

1. Run `uv run pytest --cov=app --cov-report=term-missing` and read the "Missing" lines
   to see exactly which statements are uncovered.
2. Write focused tests following the pyramid: unit for pure logic, integration (with
   `respx` for the external API and `TestClient` for the web) for wiring. Never hit real
   external services in the default suite — use the `live` marker for that.
3. Prefer testing behaviour and edge cases (each API error code, the overspend rule,
   confirm-before-spend) over line-chasing.
4. Re-run the suite and confirm the 90% gate passes before finishing.
