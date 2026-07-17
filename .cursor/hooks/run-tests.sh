#!/usr/bin/env bash
# Run tests after the agent finishes a turn (Cursor stop hook).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/scripts/run_tests.sh" ]]; then
  exit 0
fi

LOG="$ROOT/.cursor/hooks/last-test-run.log"
if "$ROOT/scripts/run_tests.sh" -q >"$LOG" 2>&1; then
  echo "Tests passed ($(wc -l < "$LOG" | tr -d ' ') lines). See .cursor/hooks/last-test-run.log"
  exit 0
fi

echo "Tests failed — see .cursor/hooks/last-test-run.log"
cat "$LOG"
exit 1
