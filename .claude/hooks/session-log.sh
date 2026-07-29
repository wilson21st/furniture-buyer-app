#!/usr/bin/env bash
# Stop hook — lightweight process observability (Foundation B).
# Appends a timestamped line to .claude/session.log so we have a local record of
# each Claude Code session boundary, complementing the OpenTelemetry metrics.
set -euo pipefail
log="$(dirname "$0")/../session.log"
printf '%s\tsession-stop\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$log"
exit 0
