# Change history

This page records durable capability changes that matter to users. It is not a
second release database and it deliberately avoids test totals, source-line
counts, and version claims that can disagree with package metadata. Those
numbers are useful in CI logs and remarkably poor at remaining true in prose.

For exact commit history, use the repository's Git history. For compatibility
contracts, use the checked-in release pins and package-specific changelog files
next to the source packages.

## Documentation baseline: 2026-08-16

The current `main` branch includes these public surfaces:

- **Deterministic graph and loadout core.** AKMS compiles global nodes, local
  nodes, code-mirror markers, and repository-local experiential state into a
  directed graph; it supports role-aware ranked queries and routing/full
  loadouts.
- **Exact task-context resolution.** Route indexes, path and symbol matching,
  required/coactivated/advisory selection, resolution manifests, reviewer
  context, and the `akms resolve-task` CLI are part of the core package.
- **Pluggable code-mirror projection.** The legacy Python provider and the
  pinned `repo2md` subprocess provider share a validated provider boundary,
  with `mirror-status` and `generate-mirror` CLI commands.
- **Optional failure memory.** `akms-failure-memory` is a separately installable
  sidecar for project-owned lesson registries, deterministic compilation,
  refresh, provider resolution, and CI checks. AKMS core does not depend on it.
- **Learning and executable companions.** `akms-learn` consumes graph slices
  read-only to produce Learning Source Packets; `compmech-reference-pack`
  optionally bridges mechanics excerpts to MechDSL.
- **Multiple runtime integrations.** The optional staged runner can dispatch
  through Claude SDK/CLI, Codex SDK/CLI, a local OpenAI-compatible endpoint, or
  a project-defined `AKMSAgent` subclass. These integrations are not required
  for graph, task-context, or failure-memory workflows.

## Documentation policy

Public pages should describe contracts and workflows that can be verified from
source. Avoid copying transient test counts or presenting the optional pipeline
runner as the identity of AKMS. When a capability changes, update the relevant
user guide and the repository-derived checks in `tools/check_docs_contract.py`
in the same change.

The previous generated-looking changelog, including its March 2026 test totals,
remains available in Git history. It is intentionally replaced here rather than
continued as if those totals were timeless facts carved into basalt.
