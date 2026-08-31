#!/bin/bash
# PreToolUse hook: Block edits to the AKMS global vault directory.
# The global vault is READ-ONLY from all automated processes (FR-O01, NFR-R03).
# Vault path resolved from: AKMS_GLOBAL_VAULT env var > default ~/.claude/akms/nodes
set -euo pipefail

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // .tool_input.file // empty')

if [[ -z "$file_path" ]]; then
  exit 0
fi

# Resolve the global vault path
vault="${AKMS_GLOBAL_VAULT:-$HOME/.claude/akms/nodes}"
# Expand ~ if present
vault="${vault/#\~/$HOME}"
# Normalize: resolve to absolute path (handle trailing slashes, symlinks)
vault=$(cd "$vault" 2>/dev/null && pwd || echo "$vault")

# Normalize the target file path
file_dir=$(dirname "$file_path")
file_dir_resolved=$(cd "$file_dir" 2>/dev/null && pwd || echo "$file_dir")
file_resolved="$file_dir_resolved/$(basename "$file_path")"

# Check if the file lives inside the global vault
if [[ "$file_resolved" == "$vault"* ]]; then
  echo "BLOCKED: Global vault nodes are READ-ONLY from automated processes (FR-O01, NFR-R03)." >&2
  echo "  Vault: $vault" >&2
  echo "  File:  $file_resolved" >&2
  echo "  To modify global nodes, do so manually outside automated processes." >&2
  echo "  To promote a local node to global, manually move the file (FR-O08)." >&2
  exit 1
fi
