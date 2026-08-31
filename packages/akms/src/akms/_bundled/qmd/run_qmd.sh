#!/usr/bin/env bash
# run_qmd.sh — Wrapper for executing AKMS qmd scripts.
#
# Usage:
#   run_qmd.sh <script_name> [args...]
#
# Examples:
#   run_qmd.sh search_nodes "plasticity return mapping"
#   run_qmd.sh search_mirror "get_DefGrad"
#   run_qmd.sh graph_status
#   run_qmd.sh node_detail lippmann-schwinger
#
# Available scripts:
#   search_nodes     — Search global + local knowledge nodes
#   search_mirror    — Search code mirror files
#   search_sessions  — Search session files (AgentMemory + PCD)
#   graph_status     — Print compiled graph summary
#   node_detail      — Show detail for a specific node

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SCRIPT_NAME="${1:?Usage: run_qmd.sh <script_name> [args...]}"
shift

QMD_PATH="$SCRIPT_DIR/${SCRIPT_NAME}.qmd"

if [ ! -f "$QMD_PATH" ]; then
    echo "ERROR: Unknown qmd script: $SCRIPT_NAME"
    echo "Available: search_nodes, search_mirror, search_sessions, graph_status, node_detail"
    exit 1
fi

exec bash "$QMD_PATH" "$@"
