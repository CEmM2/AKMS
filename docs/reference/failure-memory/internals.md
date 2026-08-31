# Failure-memory internals

`akms-failure-memory` is an optional workflow package.  A project repository
owns its canonical lesson registry and configuration; this package owns
validation, recording, deterministic projection, refresh orchestration, and
the neutral provider protocol.  AKMS continues to own graph, exact-resolution,
and loadout semantics.  repo2md continues to own source projection.

## Dependency direction

```text
project data/config -> akms-failure-memory -> documented AKMS public API
                                          -> repo2md CLI (subprocess argv)
```

AKMS core never imports or depends on this package.  This package never
imports repo2md or a consumer repository, and deterministic compiler/query
paths perform no LLM or network calls.

## Ownership classification

| Artifact | Owner | Policy |
|---|---|---|
| Lesson registry | Project | Canonical, append-only IDs |
| Project configuration | Project | Canonical policy and paths |
| Generated lesson nodes/routes | Project policy | Committed or disposable |
| Compiler/recorder/refresh/provider | This package | Reusable implementation |
| Source mirrors | repo2md product | Invoked through its pinned CLI contract |
| Graph/query/loadouts | AKMS | Invoked through the documented, pinned AKMS public API |
| Compatibility wrappers | Project | Thin CLI forwarding only |
| Promotion to global memory | Human operator | Separate, explicit action only |

The package never promotes project lessons into the global AKMS vault.  The
global vault is an explicit read-only collision/input boundary.

## `failure-memory-project/v1`

The machine contract lives in
`schemas/project-config.schema.json`.  It binds repository identity and node
namespace, canonical and generated paths, generated-file policy, validation
and taxonomy rules, compatibility renderer identifiers, and exact AKMS /
repo2md toolchain pins.  All configured paths are repository-relative POSIX
paths and are resolved component-by-component with symlink containment checks before mutation. Compiler publication of nodes and routes is transactional, deterministic graph publication validates all AKMS inputs before atomically replacing the prior artifact, and compile, record, refresh, and provider operations coordinate through the same project lock. Graph refresh never synthesizes experiential state: an absent `local_state.yaml` remains absent, while pre-existing state and graph bytes survive validation failures unchanged. Explicit refresh timestamps are preserved as graph metadata rather than replaced by wall-clock time.

Repository identity has one authority: `repository_id` in the validated project
configuration. AKMS v2 defines `local_state.yaml` as experiential state and its
`repo_id` as informational. During graph refresh, the package therefore
replaces only the temporary serialized graph metadata with the configured
`repository_id`; an absent state file remains absent, and a pre-existing state
file (including a conflicting informational `repo_id`) remains byte-for-byte
unchanged. Directory basenames and overlay values never override the project
configuration.

Refresh publication and provider `require-current` use the same internal graph
metadata finalizer. The provider rebuilds a raw AKMS candidate, applies the
validated configuration's `repository_id` and the recorded deterministic
timestamp through that shared path, and then compares the complete semantic
payload. It does not remove or rewrite the recorded `repo_id`; a graph recorded
under another configuration identity therefore remains stale.

Consumer-specific values belong only in project configuration or compatibility
fixtures.  Generic code must not branch on repository IDs, namespaces, or
layouts.  The two fixtures deliberately differ in identity, namespace, paths,
taxonomy, and committed/disposable policy.

## Compatibility boundary

The first compatibility profile preserves the originally landed registry records,
IDs, generated-node bytes, adapted route bytes, diagnostic codes/order, and
historical-path warning behavior.  These are configuration-driven renderer
inputs, not generic defaults.  A migration check may report a legacy layout;
it never moves or rewrites canonical data.
