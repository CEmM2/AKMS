# Guard hooks

Two `PreToolUse` hooks that enforce AKMS's non-negotiable invariants at the point
an agent tries to violate them, rather than after the fact.

| Hook | Enforces |
|---|---|
| `akms-guard-global-vault.sh` | **Blocks** any Edit/Write whose target resolves inside the global vault. The vault is read-only to automated processes (FR-O01, NFR-R03). |
| `akms-guard-frozen-schema.sh` | **Warns** when `schema/models.py` is edited, listing which changes are breaking (require v3 + migration) and which are safe. |

The vault guard exits nonzero, which blocks the tool call. The schema guard emits
a `systemMessage` and always exits 0 — it informs, it does not block, because
adding an *optional* field is legitimate.

## Install

Copy them next to your other hooks and register them:

```bash
mkdir -p .claude/hooks
cp /path/to/AKMS/hooks/akms-guard-*.sh .claude/hooks/
chmod +x .claude/hooks/akms-guard-*.sh
```

Then add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/akms-guard-global-vault.sh",
            "timeout": 5
          },
          {
            "type": "command",
            "command": "bash $CLAUDE_PROJECT_DIR/.claude/hooks/akms-guard-frozen-schema.sh",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

Merge into an existing `PreToolUse` block rather than replacing it.

## Requirements

**`jq` must be on `PATH`.** Both hooks parse the tool-call JSON with it. Without
`jq` the hook fails, and a `PreToolUse` hook that fails does not block the write
it was meant to guard — so verify it before relying on the vault guard:

```bash
command -v jq || echo "install jq first: brew install jq"
echo '{"tool_input":{"file_path":"'"$HOME"'/.claude/akms/nodes/x.md"}}' \
  | bash hooks/akms-guard-global-vault.sh; echo "exit=$? (expect 1 = blocked)"
```

If that prints `exit=0`, the guard is not protecting anything.

## Which vault is protected

`akms-guard-global-vault.sh` resolves the vault in this order:

1. `$AKMS_GLOBAL_VAULT`
2. `~/.claude/akms/nodes` (default)

It resolves both the vault and the target to absolute paths before comparing, so
a relative path or a symlink into the vault is still caught.

## Scope note

`akms-guard-frozen-schema.sh` matches the literal path
`Packages/AKMS/src/akms/schema/models.py`. That is AKMS's own layout, so the
warning fires only when you are editing AKMS itself — useful if you vendor the
source, inert otherwise. The vault guard is layout-independent and is the one
that matters for ordinary consumers.

## Provenance

Published copies of `.claude/hooks/akms-guard-*.sh`, byte-identical to the
internal versions. They are copies rather than moves because consumers reference
the internal path; treat the internal copies as the source of truth.
