#!/usr/bin/env bash
# Re-run tests whenever app code or tests change.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

pip install -q -r requirements-dev.txt

exec ptw tests/ \
  --runner "./scripts/run_tests.sh -q" \
  --patterns "app/* tests/* *.py" \
  --ignore-patterns ".venv/*;__pycache__/*;*.db;app/static/uploads/*"
