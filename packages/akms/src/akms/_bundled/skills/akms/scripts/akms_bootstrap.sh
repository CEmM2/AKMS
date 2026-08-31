#!/usr/bin/env bash
# Create the AKMS layout in a project and compile a first graph.
#
#   bash skills/akms/scripts/akms_bootstrap.sh [repo-root]
#
# Idempotent: safe to re-run. Never writes to the global vault.

set -euo pipefail

REPO="${1:-.}"
REPO="$(cd "$REPO" && pwd)"

echo "==> AKMS bootstrap in $REPO"

if ! command -v akms >/dev/null 2>&1; then
  echo "!! 'akms' is not on PATH."
  echo "   Install it first:  uv pip install akms   (or: pip install akms)"
  echo "   If it is installed in a project venv, run this through your runner,"
  echo "   e.g.  uv run bash skills/akms/scripts/akms_bootstrap.sh $REPO"
  exit 1
fi

mkdir -p "$REPO/knowledge/local-nodes" "$REPO/knowledge/graph"
echo "  created knowledge/local-nodes/ and knowledge/graph/"

VAULT="${AKMS_GLOBAL_VAULT:-$HOME/.claude/akms/nodes}"
if [ -d "$VAULT" ]; then
  COUNT="$(find "$VAULT" -name '*.md' -type f 2>/dev/null | wc -l | tr -d ' ')"
  echo "  global vault: $VAULT ($COUNT node file(s)) — read-only"
else
  echo "  global vault: $VAULT (absent) — project-local knowledge only"
  echo "    that is fine; AKMS works without a vault."
fi

NODES="$(find "$REPO/knowledge/local-nodes" -name '*.md' -type f 2>/dev/null | wc -l | tr -d ' ')"
echo "  local nodes: $NODES"

echo "==> compiling graph"
akms status --repo "$REPO" || {
  echo "!! 'akms status' failed. The layout exists; fix the error above and re-run."
  exit 1
}

echo
echo "==> done"
if [ "$NODES" -eq 0 ]; then
  echo "The graph is empty because there are no local nodes yet. Add one:"
  echo "  python skills/akms/scripts/new_node.py my-node \\"
  echo "      --domain my-domain --tags tag-a tag-b --repo $REPO"
else
  echo "Query it:"
  echo "  akms query <tags...> --repo $REPO --role implementer"
fi
