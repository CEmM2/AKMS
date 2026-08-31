#!/usr/bin/env bash
# deepwiki-eval: Run a structured content quality evaluation against DeepWiki MCP
#
# Usage:
#   bash run_queries.sh <question_file.md> [output_file.md]
#
#   $1 — Path to the evaluation question file (markdown, required)
#   $2 — Path to write results (optional; if omitted, results are appended to $1)
#
# Behavior:
#   - If $1 exists  → parse its queries and execute them against DeepWiki MCP
#   - If $1 missing → scaffold a new question file from the template at that path,
#                      then exit so you can fill in topics/queries before running
#
# Options:
#   --repo owner/name   Pre-fill the repo field when scaffolding (only with new files)
#   --dry-run           Parse and show queries without executing them
#
# Prerequisites:
#   - Python 3.10+ (managed via uv)
#   - httpx: uv add httpx

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
EVAL_PY="${SCRIPT_DIR}/deepwiki_query.py"
TEMPLATE="${SKILL_DIR}/references/question_template.md"

# ── Argument parsing ──────────────────────────────────────────────────────────

REPO=""
DRY_RUN=""
POSITIONAL=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo)
            REPO="$2"
            shift 2
            ;;
        --repo=*)
            REPO="${1#*=}"
            shift
            ;;
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        -h|--help)
            echo "Usage: bash run_queries.sh <question_file.md> [output_file.md] [--repo owner/name] [--dry-run]"
            echo ""
            echo "  \$1             Path to the evaluation question file (required)"
            echo "  \$2             Path to write results (optional; defaults to \$1)"
            echo "  --repo NAME    Pre-fill repo when scaffolding a new question file"
            echo "  --dry-run      Parse and display queries without executing them"
            echo ""
            echo "If the question file does not exist, a template is created at that path."
            echo "Edit it to add your topics, queries, and ground truth, then re-run."
            exit 0
            ;;
        *)
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done

if [[ ${#POSITIONAL[@]} -lt 1 ]]; then
    echo "Usage: bash run_queries.sh <question_file.md> [output_file.md] [--repo owner/name] [--dry-run]"
    echo ""
    echo "  If the question file does not exist, a new one is scaffolded from the template."
    echo "  If it exists, its queries are executed against DeepWiki MCP."
    exit 1
fi

QUESTION_FILE="${POSITIONAL[0]}"
OUTPUT_FILE="${POSITIONAL[1]:-}"

# ── Engine check ──────────────────────────────────────────────────────────────

if [[ ! -f "$EVAL_PY" ]]; then
    echo "ERROR: Engine script not found: $EVAL_PY" >&2
    echo "Expected at: $EVAL_PY" >&2
    exit 1
fi

# ── Scaffold if question file doesn't exist ───────────────────────────────────

if [[ ! -f "$QUESTION_FILE" ]]; then
    echo "Question file not found: $QUESTION_FILE"
    echo "Scaffolding a new question file from template..."

    if [[ ! -f "$TEMPLATE" ]]; then
        echo "ERROR: Template not found: $TEMPLATE" >&2
        echo "Expected at: $TEMPLATE" >&2
        exit 1
    fi

    # Ensure parent directory exists
    mkdir -p "$(dirname "$QUESTION_FILE")"

    # Copy template
    cp "$TEMPLATE" "$QUESTION_FILE"

    # Substitute repo if --repo was provided
    if [[ -n "$REPO" ]]; then
        # Replace the placeholder repo in frontmatter
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s|repo: owner/repo-name|repo: ${REPO}|" "$QUESTION_FILE"
        else
            sed -i "s|repo: owner/repo-name|repo: ${REPO}|" "$QUESTION_FILE"
        fi
        echo "  Repo set to: $REPO"
    fi

    echo ""
    echo "Created: $QUESTION_FILE"
    echo ""
    echo "Next steps:"
    echo "  1. Edit $QUESTION_FILE — add your topics, queries, and ground truth"
    echo "  2. Re-run: bash $0 $QUESTION_FILE"
    echo ""
    echo "See references/question_format.md for the full format specification."
    exit 0
fi

# ── Dependency check ──────────────────────────────────────────────────────────

if ! uv run python -c "import httpx" 2>/dev/null; then
    echo "Installing httpx..."
    uv add httpx 2>/dev/null \
        || uv pip install httpx 2>/dev/null \
        || { echo "ERROR: Failed to install httpx. Install manually: uv add httpx" >&2; exit 1; }
fi

# ── Run ───────────────────────────────────────────────────────────────────────

ARGS=("$QUESTION_FILE")
if [[ -n "$OUTPUT_FILE" ]]; then
    ARGS+=("$OUTPUT_FILE")
fi
if [[ -n "$DRY_RUN" ]]; then
    ARGS+=("$DRY_RUN")
fi

uv run python "$EVAL_PY" "${ARGS[@]}"
