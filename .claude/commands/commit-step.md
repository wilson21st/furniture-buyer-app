---
description: Run the gate, then commit and tag the current lab step
---

Commit the current lab step following our standing rules in CLAUDE.md.

Step number / message: $ARGUMENTS

Do this in order and stop if any step fails:
1. `git status` — show what will be committed; confirm no `.env` or secrets appear.
2. `uv run ruff check .` and `uv run pytest` — both must pass (coverage ≥ 90%).
3. Stage the relevant files and commit with a Conventional Commit message that starts
   with the step, e.g. `feat(step-2): level 1 app with login, catalogue, orders`.
4. Create an annotated tag `step-N` pointing at the commit.
5. `git push && git push --tags`.

If tests or coverage fail, do NOT commit — fix them first and report what failed.
