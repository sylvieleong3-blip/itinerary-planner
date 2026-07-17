#!/usr/bin/env bash
# Install a pre-push hook that runs tests before code reaches GitHub/Render.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$ROOT/.git/hooks/pre-push"

cat > "$HOOK" << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
"$ROOT/scripts/run_tests.sh" -q
EOF

chmod +x "$HOOK"
echo "Installed pre-push hook → runs scripts/run_tests.sh before every git push"
