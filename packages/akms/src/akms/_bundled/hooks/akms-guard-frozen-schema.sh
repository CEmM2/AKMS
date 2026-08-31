#!/bin/bash
# PreToolUse hook: Warn when editing frozen AKMS schema models.
# Schema is frozen at v2 — breaking changes require version bump + migration script.
set -euo pipefail

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // .tool_input.file // empty')

if [[ -z "$file_path" ]]; then
  exit 0
fi

# Only warn for the frozen schema models file
if echo "$file_path" | grep -q 'Packages/AKMS/src/akms/schema/models\.py'; then
  cat <<'EOF'
{"systemMessage": "WARNING: schema/models.py contains FROZEN v2 schemas (spec §9 of 03_AKMS_schema_specification.md).\n\nBREAKING changes (require version bump v2→v3 + migration script):\n  - Adding/removing REQUIRED fields\n  - Changing field types or valid enum values\n  - Renaming any existing field\n  - Changing LocalStateOverlay or PCD structure\n\nSAFE changes (no version bump needed):\n  - Adding new OPTIONAL fields to node frontmatter\n  - Adding new tag values (open list)\n  - Fixing bugs in validators that don't change the schema contract\n\nIf your change is breaking: create migrations/v2_to_v3.py, bump akms_schema to v3, update 03_AKMS_schema_specification.md."}
EOF
fi
