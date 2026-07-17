#!/usr/bin/env bash
# Run the full test suite with safe local defaults (no Turso, dev secret).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export SECRET_KEY="${SECRET_KEY:-local-test-secret-key}"
unset TURSO_DATABASE_URL TURSO_AUTH_TOKEN TURSO_LOCAL_PATH RENDER

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m pytest tests/ "$@"
