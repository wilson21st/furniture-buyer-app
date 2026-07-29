#!/usr/bin/env bash
# PreToolUse(Bash) hook — process-observability guardrail (Foundation B).
#
# Blocks any `git commit` / `git add` that would actually stage a secret. Reads
# the tool input JSON from stdin, extracts the command, and inspects what git has
# staged (and any explicit `.env` add-target), NOT arbitrary command text.
# Exit 2 = block the tool call (Claude sees the reason on stderr).
set -euo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)"

# Only police git commit/add commands.
case "$cmd" in
  *"git commit"*|*"git add"*) ;;
  *) exit 0 ;;
esac

# What git will actually record.
staged="$(git diff --cached --name-only 2>/dev/null || true)"

blocked=""
# 1) A real .env staged (only .env.example is allowed).
if printf '%s\n' "$staged" | grep -Eq '(^|/)\.env($|\.[^/]*$)' \
   && ! printf '%s\n' "$staged" | grep -q '\.env\.example'; then
  blocked="a .env file"
fi
# 2) An explicit `git add .env` / `git add -f .env` even if .gitignore would skip it.
if printf '%s' "$cmd" | grep -Eq 'git add( -f| --force)?[^&|;]*(^| )\.env( |$)'; then
  blocked="${blocked:+$blocked, }an explicit .env add"
fi
# 3) Obvious key material staged by name.
if printf '%s\n' "$staged" | grep -Eq '\.(pem|key|p12)$|(^|/)secrets?/'; then
  blocked="${blocked:+$blocked, }a key/secret file"
fi
# 4) Key-looking content in the staged diff.
if git diff --cached 2>/dev/null | grep -Eq 'sk-ant-[A-Za-z0-9_-]{8,}|X-Api-Key:[[:space:]]*[A-Za-z0-9]'; then
  blocked="${blocked:+$blocked, }an API key in the diff"
fi

if [ -n "$blocked" ]; then
  echo "BLOCKED: refusing to stage/commit $blocked. Secrets belong in .env (git-ignored)." >&2
  echo "Run 'git restore --staged <file>' and put the value in .env instead." >&2
  exit 2
fi
exit 0
